"""Regression tests for the audit's ticket-trace findings: covers edges in refs and impact (A-07), ambiguous
sources and container ownership (A-08). See eval/m1-tamagai/results/codex-audit.md."""
import shutil
import unittest

import support
from specdexlib import maintenance, tickets

TICKETS_FIXTURE = support.TESTS_DIR / "fixtures" / "preview-tickets"
TICKETS_OVERLAY = "_bmad/custom/specdex-overlay.toml"
SHELF_PRD = "_bmad-output/planning-artifacts/prds/prd-shelf-2026-09-15/prd.md"
ISBN_STORY = "_bmad-output/initiative-shelf-v1/epic-reading-list/story-add-a-book-by-isbn.md"
ISBN_STORY_REF = "1.1"            # covers E1, E2, which epic 1 maps to FR-1
CSV_EPIC = "_bmad-output/initiative-shelf-v1/epic-csv-transfer/epic-csv-transfer.md"
CSV_STORY = "_bmad-output/initiative-shelf-v1/epic-csv-transfer/story-export-the-list-as-csv.md"
CSV_STORY_REF = "2.1"
LAST_CSV_REQUIREMENT = "nothing is half-imported. (PRD, 4.2)\n"
COVERED_FR = "FR-1"
FR_OUTSIDE_EPIC_ONE = "FR-4"      # epic 1 owns FR-1…FR-3
FR_OUTSIDE_EPIC_TWO = "FR-6"      # epic 2 owns FR-4, FR-5
TICKETS_COVERING_FR1 = {"ticket 1", "ticket 1.1"}


class TicketTreeTestCase(support.ProjectTestCase):
    """A private copy of the preview-ticketing fixture, loaded with its own overlay."""

    def setUp(self):
        super().setUp()
        shutil.rmtree(self.root)
        shutil.copytree(TICKETS_FIXTURE, self.root)
        self.reload_config(overlay=self.root / TICKETS_OVERLAY)

    def chain_states(self, ticket: str) -> list[tuple[str, str]]:
        q = self.queries()
        return [(chain.covered_id, chain.state) for chain in tickets.chains(q, tickets.load_tree(q)) if chain.ticket == ticket]


# A-07
class CoversEdgeTest(TicketTreeTestCase):
    def assert_ticket_covers(self, rows: list[dict]) -> None:
        covers = [row for row in rows if row["kind"] == "covers"]
        self.assertEqual({row["src_id"] for row in covers}, TICKETS_COVERING_FR1)

    def test_refs_kind_covers_lists_the_tickets(self):
        _, rows, empty = self.queries().refs(COVERED_FR, "record", children=False, kind="covers")
        self.assertIsNone(empty)
        self.assertEqual({row["kind"] for row in rows}, {"covers"})
        self.assert_ticket_covers(rows)

    def test_impact_lists_the_tickets(self):
        result = maintenance.impact(self.queries(), COVERED_FR, "record")
        self.assert_ticket_covers(result["ids"][0]["incoming"])


# A-08
class ChainAuthorityTest(TicketTreeTestCase):
    def test_chain_to_an_id_with_several_current_definitions_is_ambiguous_source(self):
        self.write(SHELF_PRD, self.read(SHELF_PRD) + f"\n### {COVERED_FR}: Duplicate\n\nDifferent rule.\n")
        self.assertEqual(self.chain_states(ISBN_STORY_REF), [("E1", "ambiguous-source"), ("E2", "ambiguous-source")])

    def test_story_covering_an_upstream_fr_its_epic_does_not_own_is_flagged(self):
        self.replace_in(ISBN_STORY, "covers: [E1, E2]", f"covers: [{FR_OUTSIDE_EPIC_ONE}]")
        self.assertEqual(self.chain_states(ISBN_STORY_REF), [(FR_OUTSIDE_EPIC_ONE, "not-in-container-covers")])

    def test_story_covering_a_reused_upstream_id_its_epic_does_not_own_is_flagged(self):
        self.replace_in(CSV_EPIC, LAST_CSV_REQUIREMENT, f"{LAST_CSV_REQUIREMENT}- {FR_OUTSIDE_EPIC_TWO}: A reader shares the list. (PRD, 4.3)\n")
        self.replace_in(CSV_STORY, "covers: [FR-4, FR-5]", f"covers: [{FR_OUTSIDE_EPIC_TWO}]")
        self.assertEqual(self.chain_states(CSV_STORY_REF), [(FR_OUTSIDE_EPIC_TWO, "not-in-container-covers")])


if __name__ == "__main__":
    unittest.main()
