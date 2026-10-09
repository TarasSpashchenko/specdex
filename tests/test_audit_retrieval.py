"""Regression tests for the audit's extraction and retrieval findings: range bounds and suffixed IDs (A-20),
section numbers (A-21) and document-scoped diff keys (A-19). See eval/m1-tamagai/results/codex-audit.md."""
import json
import unittest

import support
from specdexlib import diffing, extract

CONFIG = support.load_config(support.FIXTURE)
BUDGET_CHARS = 8000
SHORT_RANGE_END = 60  # well past the old hardcoded gap of 50, inside the profile's member bound
BEYOND_MEMBER_BOUND = CONFIG.range_max + 2


def facts(text: str) -> extract.FileFacts:
    return extract.extract(CONFIG, support.PRD, text)


# A-20
class RangeBoundTest(unittest.TestCase):
    def test_short_range_within_the_member_bound_cites_every_member(self):
        ids = {o.id for o in facts(f"FR-1–{SHORT_RANGE_END}.").occurrences}
        self.assertEqual(ids, {f"FR-{n}" for n in range(1, SHORT_RANGE_END + 1)})

    def test_short_range_beyond_the_member_bound_is_a_low_bad_range(self):
        result = facts(f"FR-1–{BEYOND_MEMBER_BOUND} users")
        self.assertEqual([(code, severity) for code, severity, _, _ in result.diagnostics], [("bad-range", "low")])

    def test_positional_range_beyond_the_member_bound_is_not_expanded(self):
        result = facts(f"FR-1.1–FR-1.{BEYOND_MEMBER_BOUND}")
        self.assertFalse(any(o.via_range for o in result.occurrences))
        self.assertEqual([code for code, _, _, _ in result.diagnostics], ["bad-range"])

    def test_invalid_suffix_does_not_fall_back_to_its_parent_id(self):
        self.assertEqual([o.id for o in facts("See FR-1.2foo here.").occurrences], [])


# A-21
class SectionNumberTest(support.ProjectTestCase):
    def test_section_number_prefers_the_exact_section_over_an_earlier_subsection(self):
        self.replace_in(support.PRD, support.RELEASE_SCOPE_HEADING, "## 2.1 Rollout order\n\nStaged.\n\n## 2 Release Scope")
        hits, _ = self.queries().get("prd §2", BUDGET_CHARS)
        self.assertEqual([hit.hpath.split(" › ")[-1] for hit in hits], ["2 Release Scope"])


# A-19
class ScopedDiffTest(support.ProjectTestCase):
    SPECS = {"alpha": "_bmad-output/specs/spec-alpha/SPEC.md", "beta": "_bmad-output/specs/spec-beta/SPEC.md"}

    def setUp(self):
        super().setUp()
        for name, path in self.SPECS.items():
            self.create(path, f"# Spec\n\n- **CAP-1** — {name} rule.\n")
        records = [support.PRD, support.SPINE, *self.SPECS.values()]
        self.use_overlay(f"[current]\nrecords = {json.dumps(records)}\n")

    def test_editing_one_document_scoped_definition_reports_only_that_scope_changed(self):
        old = self.queries(db=self.workspace / "old.sqlite")
        self.replace_in(self.SPECS["alpha"], "alpha rule", "changed alpha rule")
        new = self.queries(db=self.workspace / "new.sqlite")
        self.assertEqual([item["id"] for item in diffing.diff(old, new)["changed"]], [f"CAP-1{diffing.SCOPE_MARK}_bmad-output/specs/spec-alpha"])


if __name__ == "__main__":
    unittest.main()
