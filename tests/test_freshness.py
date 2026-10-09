import os
import sqlite3
import unittest

import support
from specdexlib import store

OLD_SCHEMA_VERSION = 1
SEARCH_LIMIT = 5


class FreshnessTest(support.ProjectTestCase):
    def search_starts(self, query: str) -> list[int]:
        hits, _ = self.queries().search(query, "record", SEARCH_LIMIT)
        return [h.start for h in hits]

    def test_reopening_an_unchanged_project_reindexes_nothing(self):
        first = self.open_index()
        second = self.open_index()
        self.assertEqual((second.generation, second.changed), (first.generation, 0))

    def test_edit_changes_the_generation_and_the_results(self):
        before = self.open_index().generation
        self.assertEqual(self.search_starts("json"), [])
        self.replace_in(support.PRD, "as a CSV file", "as a JSON file")
        self.assertNotEqual(self.open_index().generation, before)
        self.assertEqual(self.search_starts("json"), [support.line_of(self.read(support.PRD), "### FR-3")])

    def test_same_size_edit_with_restored_mtime_is_detected(self):
        before = self.open_index().generation
        path = self.root / support.PRD
        stat = path.stat()
        self.replace_in(support.PRD, "locks", "halts")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(path.stat().st_size, stat.st_size)
        self.assertNotEqual(self.open_index().generation, before)
        self.assertEqual(self.search_starts("halts"), [support.line_of(self.read(support.PRD), "### FR-1")])

    def test_deleted_file_loses_its_facts(self):
        self.open_index()
        (self.root / support.TRAIL).unlink()
        q = self.queries()
        _, rows, _ = q.refs("FR-9", "all", children=False)
        self.assertEqual(rows, [])
        self.assertNotIn(support.TRAIL, q.files)
        self.assertIsNone(q.conn.execute("SELECT 1 FROM occ WHERE path=?", (support.TRAIL,)).fetchone())

    def test_invalid_frontmatter_is_a_diagnostic_not_a_crash(self):
        self.replace_in(support.PRD, "status: final", "status: final\nthis line is not yaml")
        q = self.queries()
        diagnostics = q.conn.execute("SELECT code, line FROM fdiag WHERE path=?", (support.PRD,)).fetchall()
        self.assertEqual([tuple(d) for d in diagnostics], [("parse-gap", support.line_of(self.read(support.PRD), "not yaml"))])
        self.assertEqual(q.resolve("FR-1").status, "defined")


class SchemaUpgradeTest(support.ProjectTestCase):
    def downgrade_index_file(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE bogus(x)")
        conn.execute(f"PRAGMA user_version={OLD_SCHEMA_VERSION}")
        conn.commit()
        conn.close()

    def test_index_from_another_schema_version_is_rebuilt(self):
        self.open_index().conn.close()
        self.downgrade_index_file()
        q = self.queries()
        tables = {row[0] for row in q.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(q.conn.execute("PRAGMA user_version").fetchone()[0], store.SCHEMA_VERSION)
        self.assertNotIn("bogus", tables)
        self.assertEqual(q.resolve("FR-1").status, "defined")


if __name__ == "__main__":
    unittest.main()
