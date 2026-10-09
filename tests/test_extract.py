import unittest
from textwrap import dedent

import support
from specdexlib import extract

CONFIG = support.load_config(support.FIXTURE)
PRD_TEXT = support.fixture_text(support.PRD)
SPINE_TEXT = support.fixture_text(support.SPINE)


def facts(text: str, path: str = support.PRD) -> extract.FileFacts:
    return extract.extract(CONFIG, path, dedent(text))


def range_members(text: str) -> set[str]:
    return {o.id for o in facts(text).occurrences if o.via_range}


def occurrence_ids(text: str) -> list[str]:
    return [o.id for o in facts(text).occurrences]


class RangeTest(unittest.TestCase):
    def test_en_dash_range_cites_the_members_between_explicit_ends(self):
        self.assertEqual(range_members("Covers FR-5–FR-8."), {"FR-6", "FR-7"})

    def test_double_dot_separator_also_forms_a_range(self):
        self.assertEqual(range_members("Covers FR-5..FR-7."), {"FR-6"})

    def test_short_form_range_cites_the_members_and_its_end(self):
        self.assertEqual(range_members("Covers FR-20–27 in full"), {f"FR-{n}" for n in range(21, 28)})

    def test_short_form_range_at_the_end_of_a_sentence_is_expanded(self):
        self.assertEqual(range_members("Covers FR-20–22."), {"FR-21", "FR-22"})

    def test_short_form_end_beyond_the_gap_limit_is_a_number_not_a_range(self):
        too_far = 1 + CONFIG.range_max + 1
        self.assertEqual(range_members(f"FR-1–{too_far} users"), set())

    def test_explicit_range_beyond_the_member_limit_is_diagnosed_not_expanded(self):
        result = facts(f"FR-1–FR-{CONFIG.range_max + 2}")
        self.assertFalse(any(o.via_range for o in result.occurrences))
        self.assertEqual([d[0] for d in result.diagnostics], ["bad-range"])


class PositionalTest(unittest.TestCase):
    prd = extract.extract(CONFIG, support.PRD, PRD_TEXT)

    def test_children_count_only_top_level_bullets_after_the_marker(self):
        self.assertEqual(self.prd.positional_counts, {"FR-1": 3, "FR-2": 2, "FR-3": 1})

    def test_positional_child_spans_its_bullet_with_lazy_and_nested_lines(self):
        child = next(c for c in self.prd.definitions if c.id == "FR-1.2")
        span = self.prd.spans[child.span]
        expected = (support.line_of(PRD_TEXT, "Sign-in fails"), support.line_of(PRD_TEXT, "lock message"))
        self.assertEqual((child.parent_id, child.ordinal), ("FR-1", 2))
        self.assertEqual((span.start, span.end), expected)


class CodeTest(unittest.TestCase):
    def test_id_in_inline_code_is_a_mention(self):
        self.assertEqual(occurrence_ids("See `FR-2` for details."), ["FR-2"])

    def test_id_in_fenced_code_is_still_a_mention(self):
        # Mermaid nodes and seed trees in specs name real IDs; impact and refs must see them.
        self.assertEqual(occurrence_ids("""\
            ```
            FR-3 example
            ```
            """), ["FR-3"])

    def test_heading_in_fenced_code_defines_nothing(self):
        result = facts("""\
            ```
            ### FR-4: example heading
            ```
            """)
        self.assertEqual(result.definitions, [])


class EdgeKindTest(unittest.TestCase):
    prd = extract.extract(CONFIG, support.PRD, PRD_TEXT)
    spine = extract.extract(CONFIG, support.SPINE, SPINE_TEXT)

    def kinds(self, result: extract.FileFacts, ident: str) -> set[str]:
        return {o.kind for o in result.occurrences if o.id == ident}

    def test_defining_heading_is_a_definition_and_other_citations_are_mentions(self):
        heading_line = support.line_of(PRD_TEXT, "### FR-2")
        by_line = {o.line: o.kind for o in self.prd.occurrences if o.id == "FR-2"}
        self.assertEqual(by_line.pop(heading_line), "defines")
        self.assertEqual(set(by_line.values()), {"mentions"})

    def test_binds_line_binds_its_ids_from_the_enclosing_decision(self):
        bound = [(o.id, o.src_id) for o in self.spine.occurrences if o.kind == "binds"]
        self.assertEqual(sorted(bound), [("FR-1", "AD-1"), ("FR-1.2", "AD-1"), ("FR-3", "AD-2")])

    def test_spine_headings_define_architecture_decisions(self):
        self.assertEqual(self.kinds(self.spine, "AD-1"), {"defines"})


class UnitTest(unittest.TestCase):
    def test_frontmatter_keys_become_yaml_spans_on_their_lines(self):
        result = extract.extract(CONFIG, support.PRD, PRD_TEXT)
        status = next(s for s in result.spans if s.kind == "yaml" and s.title == "status")
        self.assertEqual(status.start, support.line_of(PRD_TEXT, "status: final"))

    def test_camel_case_identifier_is_split_into_search_terms(self):
        chunk = extract.Chunk(span=0, start=1, end=1, hpath="", body="uses a LinkCredential token")
        self.assertEqual(chunk.terms, "Link Credential")

    def test_path_rules_classify_trail_and_memlog_files(self):
        self.assertEqual(extract.classify(CONFIG, support.TRAIL, None)[:2], ("review", "trail"))
        self.assertEqual(extract.classify(CONFIG, support.MEMLOG, None)[:2], ("memlog", "memlog"))


if __name__ == "__main__":
    unittest.main()
