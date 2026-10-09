"""Regression tests for the audit's authority findings: mixed sections (A-04), historical definitions (A-05),
ambiguous candidates (A-06), parse gaps (A-09), textual scopes (A-16) and inherited markers (A-26).
See eval/m1-tamagai/results/codex-audit.md."""
import unittest

import support
from specdexlib import maintenance
from specdexlib.queries import Hit

BUDGET_CHARS = 8000
SEARCH_LIMIT = 5
ABSENT_WORD = "zeppelin"
RETIRED_SECTION_RULE = '[[historical]]\nartifact = "prd"\nsection = "Retired"\n'
RISKIEST_SENTENCE = "FR-1.2 is the riskiest consequence."


class AuthorityTestCase(support.ProjectTestCase):
    def insert_before_release_scope(self, text: str) -> None:
        self.replace_in(support.PRD, support.RELEASE_SCOPE_HEADING, f"{text}\n\n{support.RELEASE_SCOPE_HEADING}")

    def append(self, relative: str, text: str) -> None:
        self.write(relative, self.read(relative) + text)

    def get_one(self, ref: str) -> Hit:
        hits, _ = self.queries().get(ref, BUDGET_CHARS)
        self.assertEqual(len(hits), 1)
        return hits[0]

    def citation_statuses(self, ident: str) -> list[str]:
        _, rows, _ = self.queries().refs(ident, "record", children=False)
        return [row["status"] for row in rows]

    def effective(self, ident: str) -> list[str]:
        rows = self.queries().conn.execute("SELECT effective FROM defs WHERE id=?", (ident,))
        return [row["effective"] for row in rows]


# A-04
class PartlyHistoricalSectionTest(AuthorityTestCase):
    def setUp(self):
        super().setUp()
        self.use_overlay(RETIRED_SECTION_RULE)
        self.insert_before_release_scope("### Retired proposals\n\nOffline sign-in was proposed and declined.")

    def test_parent_of_a_historical_subsection_is_partly_historical(self):
        self.assertEqual(self.get_one("prd §1").temporal, "partly historical")

    def test_historical_subsection_itself_stays_historical(self):
        self.assertEqual(self.get_one(f"{support.PRD_SHORT}#Retired proposals").temporal, "historical")


# A-05
class HistoricalDefinitionTest(AuthorityTestCase):
    RETIRED_ID = "FR-99"

    def setUp(self):
        super().setUp()
        self.use_overlay(RETIRED_SECTION_RULE)
        self.insert_before_release_scope(f"## Retired\n\n### {self.RETIRED_ID}: Offline sign-in\n\nDeclined.")
        self.replace_in(support.PRD, RISKIEST_SENTENCE, f"{RISKIEST_SENTENCE} {self.RETIRED_ID} stays out.")

    def test_definition_in_a_historical_section_is_historical(self):
        self.assertEqual(self.effective(self.RETIRED_ID), ["historical"])

    def test_resolve_reports_it_as_historical_only(self):
        self.assertTrue(self.queries().resolve(self.RETIRED_ID).status.startswith("historical only"))

    def test_current_citation_of_it_is_historical(self):
        self.assertEqual(self.citation_statuses(self.RETIRED_ID), ["historical"])

    def test_lint_reports_the_current_citation(self):
        citing_line = support.line_of(self.read(support.PRD), RISKIEST_SENTENCE)
        report = maintenance.lint(self.queries(), "record", validators=False)
        self.assertIn(("citation-historical", support.PRD, citing_line), [(f.code, f.path, f.line) for f in report.findings])


# A-05
class DispositionRowTest(AuthorityTestCase):
    CHANGE_REQUESTS = "_bmad-output/planning-artifacts/architecture/architecture-demo-2026-01-02/CHANGE-REQUESTS.md"
    DECIDED, UNDECIDED = "CR-1", "CR-2"
    OVERLAY = r"""
[frontmatter_types]
change-requests = "change-requests"
[[family]]
name = "CR"
pattern = 'CR-(?P<key>\d+)'
key = "int"
owner = ["change-requests"]
[[define]]
family = "CR"
artifact = "change-requests"
shape = "row-key"
[[historical]]
artifact = "change-requests"
rows = true
disposition_column = "Decision"
"""

    def setUp(self):
        super().setUp()
        self.use_overlay(self.OVERLAY)
        self.create(self.CHANGE_REQUESTS, "---\ntype: change-requests\n---\n\n# Change requests\n\n"
                                          "| ID | Request | Decision |\n|---|---|---|\n"
                                          f"| {self.DECIDED} | Use SSO | Accepted |\n| {self.UNDECIDED} | Drop CSV | |\n")

    def test_row_with_a_decision_still_defines_its_id(self):
        self.assertEqual(self.effective(self.DECIDED), ["definition"])
        self.assertEqual(self.queries().resolve(self.DECIDED).status, "defined")

    def test_row_without_a_decision_is_only_history(self):
        self.assertEqual(self.effective(self.UNDECIDED), ["historical"])


# A-06
class AmbiguousCandidateTest(AuthorityTestCase):
    OTHER_PRD = "_bmad-output/planning-artifacts/prds/prd-other-2026-02-01/prd.md"
    UNIQUE_ID = "FR-99"

    def setUp(self):
        super().setUp()
        self.create(self.OTHER_PRD, f"# Other PRD\n\n### {self.UNIQUE_ID}: Offline mode\n\nWorks offline.\n")
        self.replace_in(support.SPINE, "instead of buffering them.", f"instead of buffering them; see {self.UNIQUE_ID}.")

    def test_id_defined_in_only_one_candidate_prd_is_ambiguous(self):
        self.assertTrue(self.queries().resolve(self.UNIQUE_ID).status.startswith("ambiguous"))

    def test_its_citation_is_ambiguous(self):
        self.assertEqual(self.citation_statuses(self.UNIQUE_ID), ["ambiguous"])


# A-09
class ParseGapTest(AuthorityTestCase):
    def fdiag(self) -> list[tuple[str, str, int]]:
        rows = self.queries().conn.execute("SELECT code, severity, line FROM fdiag WHERE path=?", (support.PRD,))
        return [(row["code"], row["severity"], row["line"]) for row in rows]

    def test_medium_parse_gap_makes_empty_answers_unknown(self):
        self.replace_in(support.PRD, "status: final", "status: final\ncompanions: [missing.md")
        self.assertEqual({severity for code, severity, _ in self.fdiag() if code == "parse-gap"}, {"medium"})
        _, empty = self.queries().search(ABSENT_WORD, "record", SEARCH_LIMIT)
        self.assertTrue(empty.startswith("unknown (parse gaps"))

    def test_unclosed_frontmatter_is_a_parse_gap(self):
        self.replace_in(support.PRD, "  - architect\n---\n", "  - architect\n")
        self.assertIn("parse-gap", [code for code, _, line in self.fdiag() if line == 1])


# A-16
class TextualScopeTest(AuthorityTestCase):
    OVERLAY = r"""
[[family]]
name = "NFR"
pattern = 'NFR-(?P<key>\d+)'
key = "int"
owner = ["prd"]
[[family]]
name = "OQ"
pattern = 'OQ-(?P<key>\d+)'
key = "int"
owner = ["prd"]
[[define]]
family = "NFR"
artifact = "prd"
shape = "heading"
[[define]]
family = "OQ"
artifact = "prd"
shape = "row-key"
"""
    FR_AND_NFR_PHRASE = "all MVP FRs and NFRs"
    FAMILY_FREE_PHRASE = "all requirements"

    def setUp(self):
        super().setUp()
        self.use_overlay(self.OVERLAY)
        self.insert_before_release_scope("### NFR-1: Page load\n\nPages load within two seconds.")
        self.append(support.PRD, "\n## 3. Open Questions\n\n| ID | Question |\n|---|---|\n| OQ-1 | Which identity provider? |\n")

    def bind_by_phrase(self, phrase: str) -> None:
        self.append(support.SPINE, f"\n## AD-3: Release scope\n\n- **Binds:** {phrase}\n")

    def phrases_offered(self, ident: str) -> list[str]:
        _, rows, _ = self.queries().refs(ident, "record", children=False)
        return [row["raw"] for row in rows if row["status"] == "textual"]

    def test_phrase_naming_frs_and_nfrs_is_offered_to_both_families(self):
        self.bind_by_phrase(self.FR_AND_NFR_PHRASE)
        for ident in ("FR-1", "NFR-1"):
            with self.subTest(ident):
                self.assertEqual(self.phrases_offered(ident), [self.FR_AND_NFR_PHRASE])

    def test_phrase_naming_frs_and_nfrs_is_not_offered_to_an_open_question(self):
        self.bind_by_phrase(self.FR_AND_NFR_PHRASE)
        self.assertEqual(self.phrases_offered("OQ-1"), [])

    def test_phrase_naming_no_family_is_offered_to_every_family(self):
        self.bind_by_phrase(self.FAMILY_FREE_PHRASE)
        for ident in ("FR-1", "NFR-1", "OQ-1"):
            with self.subTest(ident):
                self.assertEqual(self.phrases_offered(ident), [self.FAMILY_FREE_PHRASE])


# A-26
class InheritedMarkerTest(AuthorityTestCase):
    def test_row_under_an_assumption_heading_carries_the_assumption_flag(self):
        self.append(support.PRD, "\n## 3. Budgets [ASSUMPTION]\n\n| Budget | Limit |\n|---|---|\n| Bundle size | 5 MB |\n")
        row = self.get_one(f"{support.PRD_SHORT}:{support.line_of(self.read(support.PRD), '| Bundle size')}")
        self.assertEqual(row.kind, "row")
        self.assertIn("assumption", row.flags.split(","))


if __name__ == "__main__":
    unittest.main()
