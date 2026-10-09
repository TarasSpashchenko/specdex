import re
import unittest

import support
from specdexlib.queries import NotFound


class QueriesTestCase(support.ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.q = self.queries()
        self.prd_text = self.read(support.PRD)

    def prd_line(self, needle: str) -> int:
        return support.line_of(self.prd_text, needle)


class ResolveTest(QueriesTestCase):
    def test_heading_id_is_defined_with_its_positional_child_count(self):
        resolution = self.q.resolve("FR-1")
        self.assertEqual(resolution.status, "defined")
        self.assertEqual(resolution.definitions[0].path, support.PRD)
        self.assertEqual(resolution.children, 3)

    def test_positional_id_resolves_to_its_bullet(self):
        definition = self.q.resolve("FR-1.2").definitions[0]
        self.assertEqual((definition.kind, definition.start), ("item", self.prd_line("Sign-in fails")))

    def test_document_scoped_id_resolves_in_the_spine(self):
        self.assertEqual(self.q.resolve("AD-2").definitions[0].path, support.SPINE)

    def test_missing_id_is_not_defined(self):
        self.assertTrue(self.q.resolve("FR-9").status.startswith("not defined"))

    def test_positional_id_past_the_list_end_is_out_of_bounds(self):
        resolution = self.q.resolve("FR-1.4")
        self.assertEqual(resolution.status, "out-of-bounds")
        self.assertIn("FR-1 has 3 positional item(s)", resolution.notes)


class RefsTest(QueriesTestCase):
    def test_citation_inside_a_range_is_found(self):
        _, rows, _ = self.q.refs("FR-2", "record", children=False)
        self.assertEqual([(r["line"], r["raw"], r["via_range"]) for r in rows], [(self.prd_line("FR-1–3 ship"), "FR-1–3", 1)])

    def test_record_scope_excludes_trail_files(self):
        _, rows, empty = self.q.refs("FR-9", "record", children=False)
        self.assertEqual(rows, [])
        self.assertIsNotNone(empty)

    def test_all_scope_reports_the_dangling_trail_citation(self):
        _, rows, _ = self.q.refs("FR-9", "all", children=False)
        self.assertEqual([(r["path"], r["status"]) for r in rows], [(support.TRAIL, "unresolved")])

    def test_children_flag_adds_positional_citations(self):
        _, rows, _ = self.q.refs("FR-1", "record", children=True)
        self.assertIn("FR-1.2", set().union(*(r["ids"] for r in rows)))


class GetTest(QueriesTestCase):
    BUDGET_CHARS = 8000

    def get_one(self, ref: str):
        hits, _ = self.q.get(ref, self.BUDGET_CHARS)
        self.assertEqual(len(hits), 1)
        return hits[0]

    def test_doc_section_number_returns_that_section(self):
        hit = self.get_one("prd §2")
        self.assertEqual(hit.hpath.split(" › ")[-1], "2. Release Scope")
        self.assertTrue(hit.text.startswith("## 2. Release Scope"))

    def test_path_line_returns_the_innermost_unit(self):
        hit = self.get_one(f"{support.PRD_SHORT}:{self.prd_line('the account locks')}")  # a lazy continuation line
        self.assertEqual((hit.kind, hit.start), ("item", self.prd_line("Sign-in fails")))

    def test_path_range_matching_a_unit_returns_that_unit(self):
        start, end = self.prd_line("Sign-in fails"), self.prd_line("lock message")
        hit = self.get_one(f"{support.PRD_SHORT}:{start}-{end}")
        self.assertEqual((hit.kind, hit.start, hit.end), ("item", start, end))

    def test_arbitrary_path_range_returns_exactly_those_lines(self):
        start, end = self.prd_line("A user signs in"), self.prd_line("**Consequences (testable):**")
        hit = self.get_one(f"{support.PRD_SHORT}:{start}-{end}")
        self.assertEqual((hit.kind, hit.text), ("range", "\n".join(self.prd_text.split("\n")[start - 1:end])))

    def test_path_heading_returns_the_matching_section(self):
        hit = self.get_one(f"{support.PRD_SHORT}#Profile editing")
        self.assertEqual(hit.start, self.prd_line("### FR-2"))

    def test_bare_file_name_prefers_the_exact_file_over_a_longer_name(self):
        self.assertEqual(self.get_one(f"prd.md:{self.prd_line('### FR-1')}").path, support.PRD)

    def test_unknown_id_is_not_found(self):
        with self.assertRaises(NotFound):
            self.q.get("FR-9", self.BUDGET_CHARS)


class SearchTest(QueriesTestCase):
    LIMIT = 5

    def test_hits_are_ranked_best_first(self):
        hits, _ = self.q.search("csv export", "record", self.LIMIT)
        self.assertEqual(hits[0].start, self.prd_line("### FR-3"))
        scores = [h.score for h in hits]
        self.assertEqual(scores, sorted(scores))

    def test_camel_case_identifier_is_found_by_its_words(self):
        self.assertIsNone(re.search(r"\b(link|credential)\b", self.prd_text, re.I), "fixture must not contain the plain words")
        hits, _ = self.q.search("link credential", "record", self.LIMIT)
        self.assertEqual(hits[0].start, self.prd_line("### FR-1"))

    def test_exact_id_in_the_query_ranks_its_definition_first(self):
        hits, _ = self.q.search("AD-2 cookie", "record", self.LIMIT)
        self.assertEqual((hits[0].path, hits[0].label), (support.SPINE, "exact ID"))

    def test_query_without_matches_explains_the_empty_answer(self):
        hits, empty = self.q.search("zeppelin", "record", self.LIMIT)
        self.assertEqual(hits, [])
        self.assertEqual(empty, "none in a fully indexed scope")


class StatusTest(QueriesTestCase):
    def test_roles_follow_artifact_kinds(self):
        self.assertEqual(self.q.status()["roles"], {"record": 2, "trail": 1, "memlog": 1})

    def test_outline_lists_record_headings_with_line_ranges(self):
        prd = next(f for f in self.q.outline(None, None) if f["path"] == support.PRD)
        fr2 = next(s for s in prd["sections"] if s["title"].startswith("FR-2"))
        self.assertEqual(fr2["start"], self.prd_line("### FR-2"))


if __name__ == "__main__":
    unittest.main()
