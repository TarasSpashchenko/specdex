import unittest

import support
from specdexlib import maintenance


class LintTest(support.ProjectTestCase):
    def findings(self, scope: str) -> list[tuple[str, str, str]]:
        report = maintenance.lint(self.queries(), scope, validators=False)
        return [(f.code, f.path, f.detail) for f in report.findings]

    def test_all_scope_flags_the_dangling_and_out_of_bounds_trail_citations(self):
        codes = {(code, path) for code, path, _ in self.findings("all")}
        self.assertEqual(codes, {("citation-unresolved", support.TRAIL), ("citation-out-of-bounds", support.TRAIL)})

    def test_record_scope_ignores_trail_citations(self):
        self.assertEqual(self.findings("record"), [])


class ImpactTest(support.ProjectTestCase):
    def test_impact_lists_the_decision_that_binds_the_requirement(self):
        result = maintenance.impact(self.queries(), "FR-3", "record")
        binds = [(e["path"], e["src_id"]) for e in result["ids"][0]["incoming"] if e["kind"] == "binds"]
        self.assertEqual(binds, [(support.SPINE, "AD-2")])


if __name__ == "__main__":
    unittest.main()
