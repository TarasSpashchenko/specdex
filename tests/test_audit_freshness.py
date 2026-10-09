"""Regression tests for the audit's freshness findings: concurrent generations (A-03), project config in the
fingerprint (A-17) and symlink identity (A-18). See eval/m1-tamagai/results/codex-audit.md."""
import itertools
import unittest
from unittest import mock

import support
from specdexlib.queries import Queries
from specdexlib.sources import WorktreeSource

NEW_WORD = "zebracorn"  # written into the PRD by a concurrent writer; absent from the fixture
SEARCH_LIMIT = 5
USER_CONFIG = "_bmad/custom/config.user.toml"
MOVED_PLANNING_ARTIFACTS = '[modules.bmm]\nplanning_artifacts = "{project-root}/_bmad-output/alternate"\n'
LINK = "_bmad-output/link.md"
FIRST_TARGET, SECOND_TARGET = "_bmad-output/first.md", "_bmad-output/second.md"
EQUAL_TEXT = "Equal text\n"


class ConcurrentGenerationTest(support.ProjectTestCase):
    def write_new_word(self) -> None:
        self.replace_in(support.PRD, "CSV", NEW_WORD)

    def found(self, q: Queries) -> int:
        return len(q.search(NEW_WORD, "record", SEARCH_LIMIT)[0])

    def test_open_queries_keep_their_snapshot_after_a_newer_writer(self):
        reader = self.queries()
        self.write_new_word()
        writer = self.queries()
        self.assertNotEqual(reader.index.generation, writer.index.generation)
        self.assertEqual(self.found(reader), 0)
        self.assertGreater(self.found(writer), 0)

    def test_open_rereads_the_inventory_after_taking_the_write_lock(self):
        self.open_index()
        unpatched_files = WorktreeSource.files
        calls = itertools.count()
        writers = []

        def files_with_a_writer_in_between(source):
            inventory = unpatched_files(source)
            if next(calls) == 0:  # the late opener's pre-lock read: a writer commits a newer generation now
                self.write_new_word()
                writers.append(self.open_index())
            return inventory

        with mock.patch.object(WorktreeSource, "files", files_with_a_writer_in_between):
            late = self.open_index()
        self.assertEqual(late.generation, writers[0].generation)
        self.assertGreater(self.found(Queries(late)), 0)


class ProjectConfigFreshnessTest(support.ProjectTestCase):
    def move_planning_artifacts(self) -> None:
        self.create(USER_CONFIG, MOVED_PLANNING_ARTIFACTS)
        self.reload_config()

    def test_user_config_planning_artifacts_change_the_fingerprint(self):
        before = self.config.fingerprint
        self.move_planning_artifacts()
        self.assertNotEqual(self.config.fingerprint, before)

    def test_index_rebuilt_after_a_user_config_change_matches_a_fresh_one(self):
        self.open_index()
        self.move_planning_artifacts()
        cached = self.queries()
        fresh = self.queries(db=self.workspace / "fresh.sqlite")
        self.assertGreater(cached.index.changed, 0)
        self.assertEqual(cached.files[support.PRD]["role"], fresh.files[support.PRD]["role"])


class SymlinkIdentityTest(support.ProjectTestCase):
    def test_retargeting_a_symlink_between_equal_files_reindexes_it(self):
        for target in (FIRST_TARGET, SECOND_TARGET):
            self.create(target, EQUAL_TEXT)
        link = self.root / LINK
        link.symlink_to((self.root / FIRST_TARGET).name)
        self.open_index()
        link.unlink()
        link.symlink_to((self.root / SECOND_TARGET).name)
        q = self.queries()
        self.assertGreater(q.index.changed, 0)
        self.assertEqual(q.files[LINK]["canonical"], SECOND_TARGET)


if __name__ == "__main__":
    unittest.main()
