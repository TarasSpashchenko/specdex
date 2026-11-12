"""specdex's ticket model on bmad-ticket trees (tests/fixtures/v7-project, changed per test in a private copy).

The fixture's active initiative, initiative-shelf, lists epic 1 (epic-reading-list: E1–E4 mapped to FR-1…FR-3,
entry 3 covering the retired E5) and epic 2 (epic-csv-transfer: FR-4, FR-5, with spec-csv/ defining CAP-1 inside
it). backlog/bug-empty-list-crash.md is standalone ticket 7 covering FR-4. initiative-shelf/spec-import/ also
defines CAP-1 and CAP-2. Each test adds or edits ticket files the way bmad-ticket, its tickets.py and the v6→v7
migration (bmod-method migration-1.toml) write them.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from support import REPO_ROOT, line_of
from specdexlib import cli, coverage, tickets
from specdexlib.index import open_index
from specdexlib.queries import Queries

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "v7-project"
USER_CONFIG = "_bmad/custom/config.user.toml"
OUT = "_bmad-output"
SHELF = f"{OUT}/initiative-shelf"
SHELF_TOML = f"{SHELF}/tickets.toml"
READING = f"{SHELF}/epic-reading-list"
READING_TOML = f"{READING}/tickets.toml"
ISBN_STORY = f"{READING}/story-add-a-book-by-isbn.md"
CSV = f"{SHELF}/epic-csv-transfer"
CSV_EPIC = f"{CSV}/epic-csv-transfer.md"
CSV_TOML = f"{CSV}/tickets.toml"
CSV_STORY = f"{CSV}/story-export-the-list-as-csv.md"
SPEC_CSV = f"{CSV}/spec-csv/spec-csv.md"
SPEC_IMPORT = f"{SHELF}/spec-import/spec-import.md"
SHARING = f"{SHELF}/epic-sharing"
BACKLOG_BUG = f"{OUT}/backlog/bug-empty-list-crash.md"
REVIEWED_STORY_LINE = "refined: true\n"
ENTRY_2_IMPORT_COVERS = 'covers = ["FR-5"]'
RETIRED_ENTRY_PROBLEM = ("1.3", "E5", "unresolved")


def leaf(title: str, covers: str, ident: str | None = None, kind: str = "story") -> str:
    """A leaf file as bmad-ticket's story template writes it; the migration writes backlog leaves without `id`."""
    id_line = f"id: {ident}\n" if ident else ""
    return f'---\n{id_line}type: {kind}\ntitle: "{title}"\nparent: none\ncovers: [{covers}]\nafter: []\n---\n\n# {title}\n'


class TicketTreeProject(unittest.TestCase):
    """A private copy of a v7 fixture per test, indexed into a private database."""
    fixture = FIXTURE

    def setUp(self) -> None:
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        self.root = Path(workdir.name) / "project"
        shutil.copytree(self.fixture, self.root)
        self.db = Path(workdir.name) / "index.sqlite"

    def run_cli(self, *args: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--project", str(self.root), "--db", str(self.db), "--json", *args])
        return code, json.loads(out.getvalue()) if out.getvalue().strip() else {}

    def queries(self) -> Queries:
        index = open_index(cli.load_config(self.root), db_path=self.db)
        self.addCleanup(index.conn.close)
        return Queries(index)

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def edit(self, relative: str, old: str, new: str) -> None:
        text = self.read(relative)
        self.assertIn(old, text)
        self.write(relative, text.replace(old, new, 1))

    def covers(self) -> dict:
        return self.run_cli("covers")[1]

    @staticmethod
    def problems(covers: dict) -> list[tuple]:
        return [(p["ticket"], p["covers"], p["state"]) for p in covers["problems"]]

    def coverage_rows(self, family: str = "FR") -> dict[str, dict]:
        rows = self.run_cli("coverage", "--by", "tickets", "--family", family)[1]["rows"]
        return {row["id"]: row for row in rows}

    def covers_edges(self, ident: str) -> set[tuple[str, str, int]]:
        rows = self.run_cli("refs", ident, "--kind", "covers")[1]["lines"]
        return {(row["src_id"], row["path"], row["line"]) for row in rows if row["rule"] == "ticket-chain"}

    def add_unlisted_epic(self) -> None:
        """An epic folder the initiative's tickets.toml does not list, whose entry 1 covers FR-6."""
        self.write(f"{SHARING}/epic-sharing.md", '---\ntype: epic\ntitle: "Readers share their list"\nparent: initiative-shelf\n'
                                                 "covers: [FR-6]\n---\n\n# Readers share their list\n\n## References\n\n"
                                                 f"- prd — {SHELF}/prd-shelf/prd-shelf.md, section 4.3\n")
        self.write(f"{SHARING}/tickets.toml", '[[entry]]\nid = 1\ntype = "story"\ntitle = "Share a public list"\ncovers = ["FR-6"]\n')


# tickets-entries-misread-as-epics
class LeafOrEpicTest(TicketTreeProject):
    def test_an_initiatives_own_entries_are_leaves_not_epics(self):
        self.write(USER_CONFIG, '[core]\nactive_initiative = "initiative-reader-stats"\n')
        row = self.coverage_rows()["FR-1"]
        self.assertEqual((row["state"], row["declared"], row["partial"]), ("declared", ["1 (planned)"], []))

    def test_an_unlisted_epic_folders_entry_is_a_leaf_not_the_listed_epic(self):
        self.add_unlisted_epic()
        rows = self.coverage_rows()
        self.assertEqual((rows["FR-6"]["state"], rows["FR-6"]["declared"]), ("declared", ["epic-sharing/1 (planned)"]))
        self.assertEqual(rows["FR-1"]["partial"], ["epic initiative-shelf/1"])


# tickets-ref-collision-misattributes
class TicketKeyTest(TicketTreeProject):
    def test_covers_edges_of_a_repeated_ref_point_at_their_own_ticket(self):
        self.add_unlisted_epic()
        epic_one = ("ticket initiative-shelf/1", SHELF_TOML, line_of(self.read(SHELF_TOML), '"FR-1", "FR-2", "FR-3"'))
        self.assertIn(epic_one, self.covers_edges("FR-1"))
        self.assertEqual(self.covers_edges("FR-6"), {("ticket epic-sharing/1", f"{SHARING}/tickets.toml", line_of(self.read(f"{SHARING}/tickets.toml"), "covers"))})

    def test_two_initiatives_epic_1_get_their_own_keys_and_folder_qualified_refs(self):
        (self.root / USER_CONFIG).unlink()
        self.write(f"{OUT}/initiative-reader-stats/tickets.toml",
                   '[[epic]]\nid = 1\nslug = "epic-monthly-charts"\ntitle = "Monthly charts"\ncovers = ["FR-1"]\n')
        tree = tickets.load_tree(self.queries())
        self.assertEqual(len({t.key for t in tree.tickets}), len(tree.tickets))
        self.assertEqual(sorted(t.ref for t in tree.tickets if not t.leaf), ["2", "initiative-reader-stats/1", "initiative-shelf/1"])


# tickets-dropped-still-declared
class DroppedTicketTest(TicketTreeProject):
    def test_a_plan_with_status_dropped_takes_its_ticket_out_of_the_check(self):
        self.write(f"{READING}/story-show-the-reading-history-plan.md", "---\nticket: 3\nstatus: dropped\n---\n")
        code, covers = self.run_cli("covers")
        self.assertEqual((code, covers["problems"], covers["dropped"]), (cli.EXIT_OK, [], ["1.3"]))

    def test_tracker_status_dropped_in_the_leaf_file_outranks_its_plan(self):
        self.edit(ISBN_STORY, REVIEWED_STORY_LINE, f"{REVIEWED_STORY_LINE}tracker_status: dropped\n")
        self.assertEqual(self.covers()["dropped"], ["1.1"])
        self.assertNotIn("1.1", self.coverage_rows()["FR-1"]["declared"])

    def test_a_leaf_files_own_status_counts_when_it_has_no_plan(self):
        self.edit(CSV_STORY, REVIEWED_STORY_LINE, f"{REVIEWED_STORY_LINE}status: dropped\n")
        covers = self.covers()
        self.assertEqual((covers["dropped"], covers["drift"]), (["2.1"], []))
        self.assertEqual(self.coverage_rows()["FR-5"]["declared"], ["2.2 (planned)"])

    def test_every_ticket_under_a_dropped_container_is_dropped(self):
        self.edit(CSV_EPIC, "risk: medium\n", "status: dropped\nrisk: medium\n")
        self.assertEqual(sorted(self.covers()["dropped"]), ["2", "2.1", "2.2", "2.3"])
        row = self.coverage_rows()["FR-5"]
        self.assertEqual((row["state"], row["declared"], row["partial"]), ("missing", [], []))


# tickets-local-spec-cap-flagged
class EpicLocalSpecTest(TicketTreeProject):
    def setUp(self) -> None:
        super().setUp()
        self.edit(CSV_TOML, ENTRY_2_IMPORT_COVERS, 'covers = ["CAP-1"]')  # spec-csv's CAP-1, inside epic 2's folder

    def test_a_local_spec_id_needs_no_place_in_the_epics_covers(self):
        code, covers = self.run_cli("covers")
        self.assertEqual(self.problems(covers), [RETIRED_ENTRY_PROBLEM])
        self.assertEqual([(item["ticket"], item["covers"]) for item in covers["local"]], [("2.2", "CAP-1")])

    def test_a_local_id_maps_to_the_parent_id_its_spec_line_names(self):
        self.edit(SPEC_CSV, "- **CAP-1** —", "- **CAP-1** (FR-4) —")
        covers = self.covers()
        self.assertEqual((self.problems(covers), covers["local"]), ([RETIRED_ENTRY_PROBLEM], []))
        self.assertIn("2.2 (planned)", self.coverage_rows()["FR-4"]["declared"])

    def test_a_local_id_mapped_to_a_parent_the_epic_does_not_own_is_flagged(self):
        self.edit(SPEC_CSV, "- **CAP-1** —", "- **CAP-1** (FR-6) —")
        self.assertIn(("2.2", "CAP-1", "not-in-container-covers"), self.problems(self.covers()))

    def test_an_unmapped_local_id_leaves_its_epics_parent_ids_unknown_not_missing(self):
        self.edit(CSV_STORY, "covers: [FR-4, FR-5]", "covers: [FR-4]")
        row = self.coverage_rows()["FR-5"]
        self.assertEqual((row["state"], row["declared"]), ("unknown", []))


# tickets-unjoined-leaves-dropped
class UnjoinedLeafTest(TicketTreeProject):
    SHARE = "story-share-a-public-list"

    def test_a_backlog_leaf_without_an_id_is_a_ticket_keyed_by_its_file_stem(self):
        self.write(f"{OUT}/backlog/{self.SHARE}.md", leaf("Share a public list", "FR-6"))
        self.assertEqual(self.coverage_rows()["FR-6"]["declared"], [f"backlog.{self.SHARE}"])

    def test_a_backlog_plan_joins_its_leaf_by_file_stem(self):
        self.write(f"{OUT}/backlog/{self.SHARE}.md", leaf("Share a public list", "FR-6"))
        self.write(f"{OUT}/backlog/{self.SHARE}-plan.md", f"---\nticket: {self.SHARE}\ntype: feature\nstatus: dropped\n---\n")
        self.assertEqual(self.covers()["dropped"], [f"backlog.{self.SHARE}"])

    def test_a_leaf_file_no_entry_lists_is_checked_like_any_leaf(self):
        self.write(f"{CSV}/story-share-the-export.md", leaf("Share the export", "FR-6", ident="4"))
        covers = self.covers()
        self.assertEqual(covers["tickets"], 2 + 6 + 1 + 1)
        self.assertIn(("2.4", "FR-6", "not-in-container-covers"), self.problems(covers))

    def test_a_leaf_file_without_an_id_in_an_epic_is_a_ticket_of_its_own(self):
        self.write(f"{CSV}/bug-quoted-titles-break-the-export.md", leaf("Quoted titles break the export", "FR-4", kind="bug"))
        self.assertIn("bug-quoted-titles-break-the-export", self.coverage_rows()["FR-4"]["declared"])


# tickets-active-backlog-folder, profile-packaging-backlog-scope
class BacklogFolderTest(TicketTreeProject):
    def test_every_backlog_folder_holds_standalone_tickets(self):
        self.write(f"{OUT}/backlog-mobile/story-read-the-list-offline.md", leaf("Read the list offline", "FR-6", ident="1"))
        self.assertEqual(self.coverage_rows()["FR-6"]["declared"], ["backlog-mobile.1"])

    def test_with_no_record_files_covers_says_the_scope_is_incomplete(self):
        self.write(f"{OUT}/initiative-empty/initiative-empty.md", "---\ntype: initiative\ntitle: Empty\n---\n\n# Empty\n")
        self.write(USER_CONFIG, '[core]\nactive_initiative = "initiative-empty"\n')
        code, covers = self.run_cli("covers")
        self.assertEqual((code, [p["state"] for p in covers["problems"]]), (cli.EXIT_FINDINGS, ["scope-incomplete"]))


# tickets-backlog-ambiguous-as-undefined
class AmbiguousBacklogTest(TicketTreeProject):
    def test_a_backlog_leaf_citing_an_id_of_several_specs_is_ambiguous_and_unknown(self):
        self.edit(BACKLOG_BUG, "covers: [FR-4]", "covers: [CAP-1]")
        self.assertIn(("backlog.7", "CAP-1", "ambiguous-source"), self.problems(self.covers()))
        rows = self.run_cli("coverage", "--by", "tickets", "--family", "CAP")[1]["rows"]
        self.assertEqual({(row["path"], row["state"]) for row in rows if row["id"] == "CAP-1"},
                         {(SPEC_CSV, "unknown"), (SPEC_IMPORT, "unknown")})


# tickets-document-scoped-coverage-collision
class DocumentScopedCoverageTest(TicketTreeProject):
    def test_covering_one_specs_cap_1_does_not_declare_another_specs_cap_1(self):
        self.edit(CSV_TOML, ENTRY_2_IMPORT_COVERS, 'covers = ["CAP-1"]')
        rows = self.run_cli("coverage", "--by", "tickets", "--family", "CAP")[1]["rows"]
        self.assertEqual({(row["path"], row["id"]): (row["state"], row["declared"]) for row in rows}, {
            (SPEC_CSV, "CAP-1"): ("declared", ["2.2 (planned)"]),
            (SPEC_IMPORT, "CAP-1"): ("missing", []),
            (SPEC_IMPORT, "CAP-2"): ("missing", []),
        })


# tickets-covers-line-trailing-comment
class CoversLineTest(TicketTreeProject):
    def test_the_covers_line_is_found_when_the_id_line_has_a_trailing_comment(self):
        self.edit(READING_TOML, "id = 2\n", "id = 2   # the rating story\n")
        covers_line = line_of(self.read(READING_TOML), 'covers = ["E3", "E4"]')
        self.assertIn(("ticket 1.2", READING_TOML, covers_line), self.covers_edges("FR-2"))


# tickets-leaf-without-covers
class LeafWithoutCoversTest(TicketTreeProject):
    def test_a_leaf_file_without_covers_takes_its_entrys_and_does_not_drift(self):
        self.edit(ISBN_STORY, "covers: [E1, E2]\n", "")
        self.assertNotIn("1.1", [d["ticket"] for d in self.covers()["drift"]])
        self.assertIn("1.1", self.coverage_rows()["FR-1"]["declared"])


# profile-packaging-coverage-default
class CoverageFamilyTest(TicketTreeProject):
    def test_coverage_with_no_family_is_a_usage_error_naming_the_setting(self):
        q = self.queries()
        q.index.config.coverage.clear()
        args = cli.build_parser().parse_args(["--json", "coverage", "--by", "tickets"])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = coverage.run(args, q)
        lines = err.getvalue().splitlines()
        self.assertEqual((code, out.getvalue(), len(lines)), (cli.EXIT_USAGE, "", 1))
        self.assertIn("coverage.tickets", lines[0])
        self.assertIn("--family", lines[0])


if __name__ == "__main__":
    unittest.main()


# M3 review findings on the October layout
class OctoberReviewFindingTest(TicketTreeProject):
    def test_an_initiatives_own_prd_ids_still_have_to_be_in_its_covers(self):
        self.edit(f"{SHELF}/initiative-shelf.md", "covers: [FR-1, FR-2, FR-3,", "covers: [FR-1, FR-3,")
        self.assertIn(("1", "FR-2", "not-in-container-covers"), self.problems(self.covers()))

    def test_an_october_prd_defines_its_open_questions_and_rules(self):
        self.write(f"{SHELF}/prd-shelf/prd-shelf.md", self.read(f"{SHELF}/prd-shelf/prd-shelf.md")
                   + "\n## 7. Open Questions\n\n- **OQ-1:** Do lists sync across devices?\n- **RULE-1:** One list per reader.\n")
        for ident in ("OQ-1", "RULE-1"):
            with self.subTest(ident):
                self.assertEqual(self.run_cli("resolve", ident)[1]["status"], "defined")

    def test_a_spec_id_the_spec_does_not_define_is_no_folded_alias(self):
        self.edit(CSV_EPIC, "- FR-5:", "- E9 (CAP-7): An extra capability.\n- FR-5:")
        self.edit(CSV_TOML, ENTRY_2_IMPORT_COVERS, 'covers = ["E9"]')
        self.assertIn(("2.2", "E9", "upstream-unresolved"), self.problems(self.covers()))
