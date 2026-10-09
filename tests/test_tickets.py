"""specdex's ticket adapter (`covers`, `coverage --by tickets`) on a synthetic BMAD preview-ticketing tree.

tests/fixtures/preview-tickets follows the layout in bmad-preview-ticketing's references/board.md:
a PRD with FR-1…FR-6 and initiative-shelf-v1 with two epics. Epic 1 mints requirement ids
(`E1 (FR-1)`); epic 2 reuses its parent's ids (`FR-4`), the two forms epic-template.md allows.

  ticket  what it is                                                              case
  1.1     pulled story covering E1, E2 (both map to FR-1); plan from `tickets.py mark`  (a) (f)
  1.2     entry with no file; plan written by bmad-build from its plan template   (f)
  1.3     entry covering E5, which epic 1's Requirements no longer list           (c)
  2.1     pulled story covering FR-4, FR-5 while its entry still says FR-4        (d)
  2.2     entry with no file and no plan                                          (e)
  2.3     spike entry covering nothing
  FR-6    parked in the initiative's Notes: no ticket covers it                   (b)
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "specdex" / "scripts"))

from specdexlib import cli, tickets  # noqa: E402
from specdexlib.index import open_index  # noqa: E402
from specdexlib.queries import Queries  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "preview-tickets"
CSV_EPIC_FOLDER = "_bmad-output/initiative-shelf-v1/epic-csv-transfer"
EPIC_COUNT, ENTRY_COUNT = 2, 6

FULL_CHAIN_STORY = "1.1"
BUILD_PLAN_ENTRY = "1.2"
UNRESOLVED_ENTRY = "1.3"
DRIFTED_STORY = "2.1"
PLANNED_ENTRY = "2.2"
FULLY_COVERED_FR = "FR-1"
REUSED_ID_FR = "FR-4"
MISSING_FR = "FR-6"


def run_specdex(db: Path, *command: str) -> tuple[int, dict]:
    """Run the CLI with --json on the fixture; return its exit code and parsed output."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--project", str(FIXTURE), "--db", str(db), "--json", *command])
    return code, json.loads(out.getvalue())


class PreviewTicketTreeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workdir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(workdir.cleanup)
        db = Path(workdir.name) / "index.sqlite"
        cls.covers_exit, cls.covers = run_specdex(db, "covers")
        _, coverage = run_specdex(db, "coverage", "--by", "tickets")
        cls.coverage_rows = {row["id"]: row for row in coverage["rows"]}
        cls.coverage_scope = coverage["scope"]
        _, cls.gaps = run_specdex(db, "coverage", "--by", "tickets", "--only", "gaps")
        # The CLI never prints a ticket's plan status or its chain list, so read them through the adapter.
        index = open_index(cli.load_config(FIXTURE), db_path=db)
        cls.addClassCleanup(index.conn.close)
        queries = Queries(index)
        tree = tickets.load_tree(queries)
        cls.plan_status = {ticket.ref: ticket.status for ticket in tree.tickets}
        cls.chains = {(chain.ticket, chain.covered_id) for chain in tickets.chains(queries, tree)}

    def problem_tickets(self) -> list[str]:
        return [problem["ticket"] for problem in self.covers["problems"]]

    def test_a_full_chain_resolves_to_its_fr(self):
        self.assertNotIn(FULL_CHAIN_STORY, self.problem_tickets())
        self.assertEqual(self.coverage_rows[FULLY_COVERED_FR], {
            "id": FULLY_COVERED_FR, "state": "declared", "declared": [FULL_CHAIN_STORY], "partial": ["epic 1"], "unknown": []})

    def test_b_fr_without_a_ticket_is_missing(self):
        self.assertEqual(self.coverage_rows[MISSING_FR], {
            "id": MISSING_FR, "state": "missing", "declared": [], "partial": [], "unknown": []})
        self.assertEqual(self.coverage_scope, "fully indexed")

    def test_c_covers_naming_an_absent_requirement_is_the_only_problem(self):
        found = [(p["ticket"], p["covers"], p["state"]) for p in self.covers["problems"]]
        self.assertEqual(found, [(UNRESOLVED_ENTRY, "E5", "unresolved")])
        self.assertEqual(self.covers_exit, cli.EXIT_FINDINGS)

    def test_d_refined_file_covers_drift_from_its_entry_and_win(self):
        self.assertEqual(self.covers["drift"], [{
            "ticket": DRIFTED_STORY, "file": f"{CSV_EPIC_FOLDER}/story-export-the-list-as-csv.md",
            "file_covers": ["FR-4", "FR-5"], "entry_covers": ["FR-4"]}])
        self.assertIn((DRIFTED_STORY, "FR-5"), self.chains)

    def test_e_entry_without_file_or_plan_is_planned_not_a_defect(self):
        self.assertIn(PLANNED_ENTRY, self.covers["planned"])
        self.assertNotIn(PLANNED_ENTRY, self.problem_tickets())

    def test_f_plan_files_are_not_tickets(self):
        self.assertEqual(self.covers["tickets"], EPIC_COUNT + ENTRY_COUNT)

    def test_f_mark_plan_status_joins_its_entry(self):
        self.assertEqual(self.plan_status[FULL_CHAIN_STORY], "done")

    # bmad-build's plan template ends `ticket:` and `status:` with a trailing YAML comment.
    def test_f_build_plan_status_joins_its_entry(self):
        self.assertEqual(self.plan_status[BUILD_PLAN_ENTRY], "in-progress")

    # The skill: planned means no file and no plan yet.
    def test_f_entry_with_a_plan_is_not_planned(self):
        self.assertNotIn(BUILD_PLAN_ENTRY, self.covers["planned"])

    # A Requirements line may reuse the parent's id (`- FR-4: …`) instead of minting `E<n> (R<m>)`.
    def test_reused_parent_id_is_declared_coverage(self):
        self.assertEqual(self.coverage_rows[REUSED_ID_FR]["declared"], [DRIFTED_STORY])

    def test_only_gaps_lists_exactly_the_missing_fr(self):
        self.assertEqual([row["id"] for row in self.gaps["rows"]], [MISSING_FR])


if __name__ == "__main__":
    unittest.main()
