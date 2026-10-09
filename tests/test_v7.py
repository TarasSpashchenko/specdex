"""specdex on the BMad v7 initiative layout (tests/fixtures/v7-project).

The fixture is a v7 project: `_bmad/config.toml` with `_bmad/custom/config.user.toml` setting
`core.active_initiative = "initiative-shelf"`, BMad's own resolver scripts in `_bmad/scripts/`, and
project settings in `_bmad/custom/specdex.toml`. Under `_bmad-output/`:

  initiative-shelf/          the active initiative: brief, PRD (FR-1 as a heading, FR-2 and FR-3 as bold
                             list items), UX (router, DESIGN.md, EXPERIENCE.md), spine, two specs (one inside
                             an epic), the preview ticket tree, and trail and rationale files
  initiative-reader-stats/   an inactive initiative whose PRD also defines FR-1 and whose tickets.toml has
                             entries but no epics
  prd-scratch/               a loose PRD written by a headless run
  backlog/, inbox/, archive-v6/, discussion-pricing/   standalone ticket, untriaged notes, the v6 archive,
                             a non-BMad discussion folder
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "skills" / "specdex" / "scripts"))

from specdexlib import cli, config  # noqa: E402
from specdexlib.index import open_index  # noqa: E402
from specdexlib.queries import Queries  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "v7-project"
V6_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "mini-project"
OUT = "_bmad-output"
SHELF = f"{OUT}/initiative-shelf"
PRD = f"{SHELF}/prd-shelf/prd-shelf.md"
STATS_PRD = f"{OUT}/initiative-reader-stats/prd-reader-stats/prd-reader-stats.md"
SPINE = f"{SHELF}/architecture-shelf/architecture-shelf.md"
USER_CONFIG = "_bmad/custom/config.user.toml"
CUSTOMIZATION = "_bmad/custom/specdex.toml"
LEGACY_OVERLAY = "_bmad/custom/specdex-overlay.toml"

EXPECTED = {  # path: (artifact type, role)
    PRD: ("prd", "record"),
    f"{SHELF}/prd-shelf/addendum.md": ("prd-addendum", "record"),
    f"{SHELF}/brief-shelf/brief-shelf.md": ("brief", "record"),
    f"{SHELF}/brief-shelf/addendum.md": ("brief-addendum", "record"),
    f"{SHELF}/ux-shelf/DESIGN.md": ("ux-design", "record"),
    f"{SHELF}/ux-shelf/EXPERIENCE.md": ("ux-experience", "record"),
    f"{SHELF}/ux-shelf/ux-shelf.md": ("ux-router", "rationale"),
    SPINE: ("architecture-spine", "record"),
    f"{SHELF}/spec-import/spec-import.md": ("spec", "record"),
    f"{SHELF}/epic-csv-transfer/spec-csv/spec-csv.md": ("spec", "record"),
    STATS_PRD: ("prd", "noncurrent"),
    f"{OUT}/prd-scratch/prd-scratch.md": ("prd", "noncurrent"),
    f"{SHELF}/prd-shelf/review-rubric.md": ("review", "trail"),
    f"{SHELF}/prd-shelf/reconcile-brief.md": ("reconcile", "trail"),
    f"{SHELF}/prd-shelf/validation-report.md": ("validation-report", "trail"),
    f"{SHELF}/architecture-shelf/reviews/review-adversarial.md": ("review", "trail"),
    f"{SHELF}/ux-shelf/.working/inventory.md": ("working", "trail"),
    f"{SHELF}/ux-shelf/imports/brand-guide.md": ("working", "trail"),
    f"{SHELF}/change-scope-cut/change-scope-cut.md": ("change-proposal", "trail"),
    f"{SHELF}/deferred-work.md": ("deferred-work", "trail"),
    f"{SHELF}/migration-v6-v7/migration-v6-v7.md": ("migration", "trail"),
    f"{SHELF}/research-isbn-providers/research-isbn-providers.md": ("research", "rationale"),
    f"{OUT}/archive-v6/planning-artifacts/prds/prd-shelf-2026-09-15/prd.md": ("archive", "trail"),
    f"{OUT}/inbox/idea-dark-mode.md": ("inbox", "trail"),
    f"{OUT}/discussion-pricing/board.md": ("discussion", "trail"),
    f"{SHELF}/prd-shelf/.memlog.md": ("memlog", "memlog"),
    f"{SHELF}/initiative-shelf.md": ("initiative", "ticket"),
    f"{SHELF}/tickets.toml": ("tickets-toml", "ticket"),
    f"{OUT}/backlog/bug-empty-list-crash.md": ("ticket-leaf", "ticket"),
}


class V7Project(unittest.TestCase):
    """A private copy of the v7 fixture per test, indexed into a private database."""

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

    def diagnostics(self) -> set[str]:
        return {d["code"] for d in self.run_cli("status")[1]["diagnostics"]}

    def defined_at(self, ident: str) -> list[str]:
        code, resolution = self.run_cli("resolve", ident)
        return [d["path"] for d in resolution.get("definitions", [])] if code == cli.EXIT_OK else []


class ProfileSelectionTest(V7Project):
    def test_v7_layout_selects_the_v7_profile_and_says_why(self):
        status = self.run_cli("status")[1]
        self.assertEqual(status["profile"], "bmad-v7")
        self.assertIn("active_initiative", status["profile_reason"])

    def test_v6_dated_layout_still_selects_the_v6_profile(self):
        self.root = V6_FIXTURE
        self.assertEqual(self.run_cli("status")[1]["profile"], "bmad-6.13.0-next")

    def test_v7_layout_is_no_longer_unsupported(self):
        self.assertNotIn("unsupported-layout", self.diagnostics())

    def test_sharded_v6_document_under_a_custom_planning_folder_selects_v6_and_is_unsupported(self):
        (self.root / USER_CONFIG).unlink()
        shutil.rmtree(self.root / OUT)
        self.write("_bmad/config.toml", '[core]\noutput_folder = "{project-root}/_bmad-output"\n\n'
                                        '[modules.bmm]\nplanning_artifacts = "{project-root}/_bmad-output/plans"\n')
        self.write(f"{OUT}/plans/prd/index.md", "# PRD\n\n- [Requirements](./requirements.md)\n")
        self.write(f"{OUT}/plans/prd/requirements.md", "# Requirements\n\n### FR-1: Shelves\n")
        status = self.run_cli("status")[1]
        self.assertEqual(status["profile"], "bmad-6.13.0-next")
        self.assertIn("unsupported-layout", {d["code"] for d in status["diagnostics"]})


class ArtifactTest(V7Project):
    def test_every_v7_artifact_gets_its_type_and_role(self):
        files = self.queries().files
        found = {path: (files[path]["artifact"], files[path]["role"]) for path in EXPECTED if path in files}
        self.assertEqual(found, EXPECTED)

    def test_fr_defined_as_heading_or_as_bold_item_both_resolve_in_the_active_prd(self):
        for ident in ("FR-1", "FR-2", "FR-3"):
            with self.subTest(ident):
                self.assertEqual(self.defined_at(ident), [PRD])

    def test_spine_decisions_resolve(self):
        self.assertEqual(self.defined_at("AD-2"), [SPINE])

    def test_document_scoped_specs_are_records_side_by_side(self):
        code, resolution = self.run_cli("resolve", "CAP-1")
        self.assertEqual(sorted(d["path"] for d in resolution["definitions"]),
                         [f"{SHELF}/epic-csv-transfer/spec-csv/spec-csv.md", f"{SHELF}/spec-import/spec-import.md"])

    def test_doc_section_reference_reaches_the_active_prd(self):
        hits = self.run_cli("get", "prd §4.2")[1]["hits"]
        self.assertEqual([h["path"] for h in hits], [PRD])

    def test_a_bold_lead_whose_title_starts_lowercase_still_defines(self):
        text = (self.root / PRD).read_text(encoding="utf-8")
        self.write(PRD, text.replace("## 5. Non-Goals", "## 4.9 Success\n\n- **SM-7 weekly active readers**: 500 by June.\n\n## 5. Non-Goals", 1))
        self.assertEqual(self.defined_at("SM-7"), [PRD])
        self.assertEqual(self.defined_at("FR-2"), [PRD])  # its "**FR-2 is verified …**" acceptance line stays a citation

    def test_an_archive_inside_an_initiative_is_trail(self):
        archived = f"{SHELF}/archive-v6/ux-shelf-2026-09-01/DESIGN.md"
        self.write(archived, (self.root / f"{SHELF}/ux-shelf/DESIGN.md").read_text(encoding="utf-8"))
        info = self.queries().files[archived]
        self.assertEqual((info["artifact"], info["role"]), ("archive", "trail"))
        self.assertNotIn("ambiguous-current", self.diagnostics())

    def test_frontmatter_type_never_turns_a_trail_file_into_an_owner_or_a_ticket(self):
        draft, story = f"{SHELF}/architecture-shelf/.working/draft.md", f"{OUT}/inbox/story-old.md"
        self.write(draft, "---\ntype: architecture-spine\n---\n# Draft spine\n\n## AD-2: Draft decision\n\nDraft.\n")
        self.write(story, "---\ntype: story\nid: 9\ncovers: [FR-1]\n---\n# Old story\n")
        files = self.queries().files
        self.assertEqual((files[draft]["role"], files[story]["role"]), ("trail", "trail"))
        self.assertEqual(self.defined_at("AD-2"), [SPINE])

    def test_an_epic_spine_stands_beside_the_initiative_spine(self):
        epic_spine = f"{SHELF}/architecture-epic-csv/architecture-epic-csv.md"
        self.write(epic_spine, "---\ntype: architecture-spine\naltitude: epic\n---\n# Spine: CSV epic\n\n## AD-9: Stream rows\n\nRows stream.\n")
        self.assertNotIn("ambiguous-current", self.diagnostics())
        self.assertEqual(self.defined_at("AD-2"), [SPINE])
        self.assertEqual(self.defined_at("AD-9"), [epic_spine])

    def test_intent_and_idea_files_of_an_initiative_are_rationale(self):
        intent, idea = f"{SHELF}/intent.md", f"{SHELF}/idea-offline/idea-offline.md"
        self.write(intent, "# Intent\n\nShelves for every reader.\n")
        self.write(idea, "# Idea: offline\n\nWork offline.\n")
        files = self.queries().files
        self.assertEqual((files[intent]["role"], files[idea]["role"]), ("rationale", "rationale"))

    def test_a_migrated_sharded_document_is_unsupported_and_its_ids_unknown(self):
        self.write(PRD, "---\ntype: prd\n---\n# PRD: Shelf\n\n- [Functional requirements](./functional-requirements.md)\n")
        self.write(f"{SHELF}/prd-shelf/functional-requirements.md", "# Functional requirements\n\n### FR-9: Export shelves\n\nUsers export.\n")
        self.assertIn("unsupported-layout", self.diagnostics())
        self.assertIn("unknown", self.run_cli("resolve", "FR-9")[1]["status"])


class ActiveInitiativeTest(V7Project):
    def test_an_inactive_initiative_does_not_compete_for_ids(self):
        self.assertNotIn("ambiguous-current", self.diagnostics())
        self.assertEqual(self.defined_at("FR-1"), [PRD])

    def test_switching_the_active_initiative_switches_the_records(self):
        self.write(USER_CONFIG, '[core]\nactive_initiative = "initiative-reader-stats"\n')
        self.assertEqual(self.defined_at("FR-1"), [STATS_PRD])
        self.assertEqual(self.defined_at("FR-2"), [])

    def test_no_active_initiative_is_reported_and_candidates_are_ambiguous(self):
        (self.root / USER_CONFIG).unlink()
        self.assertTrue({"no-active-initiative", "ambiguous-current"} <= self.diagnostics())
        self.assertTrue(self.run_cli("resolve", "FR-1")[1]["status"].startswith("ambiguous"))

    def test_two_candidates_inside_the_active_initiative_point_to_the_records_setting(self):
        self.write(f"{SHELF}/prd-shelf-copy/prd-shelf-copy.md", (self.root / PRD).read_text(encoding="utf-8"))
        status = self.run_cli("resolve", "FR-1")[1]["status"]
        self.assertTrue(status.startswith("ambiguous"))
        self.assertIn("inside the active initiative", status)

    def test_records_setting_decides_only_the_types_it_names(self):
        self.write(CUSTOMIZATION, '[workflow]\nrecords = ["{output_folder}/{active_initiative}/prd-shelf/prd-shelf.md"]\n')
        files = self.queries().files
        self.assertEqual([files[p]["role"] for p in (PRD, f"{SHELF}/prd-shelf/addendum.md", SPINE, STATS_PRD)],
                         ["record", "record", "record", "noncurrent"])

    def test_records_setting_decides_without_an_active_initiative(self):
        (self.root / USER_CONFIG).unlink()
        scratch = f"{OUT}/prd-scratch/prd-scratch.md"
        self.write(CUSTOMIZATION, '[workflow]\nrecords = ["{output_folder}/{active_initiative}/prd-scratch/prd-scratch.md"]\n')
        status = self.run_cli("status")[1]
        self.assertFalse({"missing-record", "no-active-initiative"} & {d["code"] for d in status["diagnostics"]})
        self.assertEqual(status["records_setting"], 1)
        self.assertEqual(self.queries().files[scratch]["role"], "record")

    def test_rationale_and_tickets_outside_the_active_initiative_are_noncurrent(self):
        other = f"{OUT}/initiative-reader-stats/research-goodreads/research-goodreads.md"
        loose = f"{OUT}/research-market/research-market.md"
        self.write(other, "# Research: Goodreads\n\nImport formats.\n")
        self.write(loose, "# Research: market\n\nReaders.\n")
        files = self.queries().files
        roles = [files[p]["role"] for p in (other, loose, f"{OUT}/initiative-reader-stats/tickets.toml",
                                           f"{SHELF}/research-isbn-providers/research-isbn-providers.md", f"{OUT}/backlog/bug-empty-list-crash.md")]
        self.assertEqual(roles, ["noncurrent", "noncurrent", "noncurrent", "rationale", "ticket"])

    def test_output_folder_at_the_project_root_keeps_the_initiative_scope(self):
        for child in list((self.root / OUT).iterdir()):
            shutil.move(str(child), str(self.root / child.name))
        self.write("_bmad/config.toml", '[core]\nproject_name = "shelf"\noutput_folder = "{project-root}"\n')
        self.assertNotIn("no-active-initiative", self.diagnostics())
        self.assertEqual(self.defined_at("FR-1"), ["initiative-shelf/prd-shelf/prd-shelf.md"])

    def test_an_active_backlog_folder_leaves_the_records_to_the_type_rule(self):
        self.write(USER_CONFIG, '[core]\nactive_initiative = "backlog"\n')
        status = self.run_cli("status")[1]
        self.assertIsNone(status["current_scope"])
        self.assertNotIn("no-active-initiative", {d["code"] for d in status["diagnostics"]})
        self.assertEqual(self.queries().files[PRD]["role"], "ambiguous")  # three PRDs compete, as with no initiative


class SettingsTest(V7Project):
    NFR = ('[[workflow.family]]\nid = "NFR"\npattern = \'NFR-(?P<key>\\d+)\'\nkey = "int"\nowner = ["prd"]\n\n'
           '[[workflow.define]]\nid = "NFR-in-prd"\nfamily = "NFR"\nartifact = "prd"\nshape = "item-lead"\n')

    def add_nfr_1(self) -> None:
        text = (self.root / PRD).read_text(encoding="utf-8")
        self.write(PRD, text.replace("## 5. Non-Goals", "## 4.9 Quality\n\n- **NFR-1. Fast.** Search answers in 1 s.\n\n## 5. Non-Goals", 1))

    def bmad_resolver(self, script: str, *args: str) -> dict:
        """What BMad's own resolver (the fixture's byte-identical copy) returns; only the test runs it."""
        done = subprocess.run([sys.executable, str(self.root / "_bmad" / "scripts" / script), "--project-root", str(self.root), *args],
                              capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    def test_config_reader_matches_bmads_resolver(self):
        self.assertEqual(config.read_project_config(self.root), self.bmad_resolver("resolve_config.py"))

    def test_customization_reader_matches_bmads_resolver(self):
        self.write(CUSTOMIZATION, self.NFR + '[workflow.coverage]\ntickets = ["FR"]\n')
        self.write("_bmad/custom/specdex.user.toml", '[[workflow.family]]\nid = "NFR"\npattern = \'NFR-(?P<key>\\d+)\'\nkey = "int"\nowner = ["prd-addendum"]\n')
        expected = self.bmad_resolver("resolve_customization.py", "--skill", str(cli.SKILL_ROOT), "--key", "workflow")["workflow"]
        self.assertEqual(config.read_customization(self.root, cli.SKILL_ROOT), expected)

    def test_project_scripts_are_never_executed(self):
        marker = self.root / "executed"
        for script in ("resolve_config.py", "resolve_customization.py", "config_utils.py"):
            self.write(f"_bmad/scripts/{script}", f"open({str(marker)!r}, 'w').write('ran')\n")
        self.assertEqual(self.run_cli("status")[1]["profile"], "bmad-v7")
        self.assertFalse(marker.exists())

    def test_customization_adds_an_id_family(self):
        self.add_nfr_1()
        self.write(CUSTOMIZATION, self.NFR)
        self.assertEqual(self.defined_at("NFR-1"), [PRD])

    def test_role_setting_outranks_the_profiles_default_for_supporting_files(self):
        self.write(CUSTOMIZATION, '[[workflow.role]]\nid = "boards"\nglob = "**/discussion-*/board.md"\nrole = "rationale"\n'
                                  '[[workflow.role]]\nid = "rest"\nglob = "**"\nrole = "trail"\n')
        files = self.queries().files
        self.assertEqual(files[f"{OUT}/discussion-pricing/board.md"]["role"], "rationale")
        self.assertEqual(files[f"{SHELF}/prd-shelf/.memlog.md"]["role"], "memlog")  # memlogs and tickets keep their kind
        self.assertEqual(files[f"{SHELF}/tickets.toml"]["role"], "ticket")

    def test_legacy_overlay_is_still_read_and_flagged_as_deprecated(self):
        self.add_nfr_1()
        (self.root / CUSTOMIZATION).unlink()
        overlay = self.NFR.replace("workflow.", "").replace('id = "NFR"\n', 'name = "NFR"\n').replace('id = "NFR-in-prd"\n', "")
        self.write(LEGACY_OVERLAY, '[overlay]\nprofile = "bmad-v7"\n\n' + overlay)
        self.assertEqual(self.defined_at("NFR-1"), [PRD])
        self.assertIn("deprecated-overlay", self.diagnostics())


class TicketTest(V7Project):
    def test_the_active_initiatives_tree_checks_as_before_with_the_v7_prd(self):
        code, covers = self.run_cli("covers")
        self.assertEqual([(p["ticket"], p["covers"], p["state"]) for p in covers["problems"]], [("1.3", "E5", "unresolved")])
        self.assertEqual(code, cli.EXIT_FINDINGS)

    def test_backlog_leaf_counts_and_inactive_initiatives_are_left_out(self):
        covers = self.run_cli("covers")[1]
        self.assertEqual(covers["tickets"], 2 + 6 + 1)
        rows = {row["id"]: row for row in self.run_cli("coverage", "--by", "tickets")[1]["rows"]}
        self.assertIn("backlog.7", rows["FR-4"]["declared"])

    def test_an_initiative_tickets_toml_without_epics_holds_entries(self):
        self.write(USER_CONFIG, '[core]\nactive_initiative = "initiative-reader-stats"\n')
        covers = self.run_cli("covers")[1]
        self.assertEqual(covers["tickets"], 1 + 1)  # its one entry, and the standalone backlog leaf
        # The backlog leaf covers the shelf PRD's FR-4, which the now-active initiative does not define.
        self.assertEqual([(p["ticket"], p["covers"], p["state"]) for p in covers["problems"]], [("backlog.7", "FR-4", "unresolved")])


class ConfigurationErrorTest(V7Project):
    def status_exit_and_stderr(self) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = cli.main(["--project", str(self.root), "--db", str(self.db), "status"])
        return code, err.getvalue()

    def assert_configuration_error(self) -> None:
        code, err = self.status_exit_and_stderr()
        self.assertEqual((code, err.count("\n")), (cli.EXIT_CONFIG, 1), err)

    def test_a_wrong_typed_setting_is_a_configuration_error(self):
        self.write(CUSTOMIZATION, '[workflow]\nfamily = "NFR"\n')
        self.assert_configuration_error()

    def test_an_incomplete_settings_item_is_a_configuration_error(self):
        self.write(CUSTOMIZATION, '[[workflow.define]]\nid = "fr-rows"\nfamily = "FR"\nartifact = "prd"\n')
        self.assert_configuration_error()

    def test_a_config_layer_that_is_not_utf8_is_a_configuration_error(self):
        (self.root / USER_CONFIG).write_bytes(b'# caf\xe9\n[core]\nactive_initiative = "initiative-shelf"\n')
        self.assert_configuration_error()

    def test_an_unknown_workflow_key_is_reported(self):
        self.write(CUSTOMIZATION, '[workflow.current]\nrecords = ["_bmad-output/prd-scratch/prd-scratch.md"]\n')
        self.assertIn("unknown-setting", self.diagnostics())

    def test_a_legacy_overlay_holding_a_toml_date_loads(self):
        self.write(LEGACY_OVERLAY, '[overlay]\nprofile = "bmad-v7"\nupdated = 2026-09-30\n')
        self.assertIn("deprecated-overlay", self.diagnostics())

    def test_removing_the_legacy_overlay_clears_its_diagnostic(self):
        self.write(LEGACY_OVERLAY, '[coverage]\ntickets = ["FR"]\n')  # the same setting as the customization: no settings change
        self.assertIn("deprecated-overlay", self.diagnostics())
        (self.root / LEGACY_OVERLAY).unlink()
        self.assertNotIn("deprecated-overlay", self.diagnostics())


@unittest.skipUnless(shutil.which("git"), "git CLI not installed")
class RevisionTest(V7Project):
    fixture = V6_FIXTURE
    V6_PRD, V7_PRD = "_bmad-output/planning-artifacts/prds/prd-demo-2026-01-01/prd.md", f"{OUT}/initiative-demo/prd-demo/prd-demo.md"

    def git(self, *args: str) -> None:
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
               "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=env)

    def test_a_revision_before_the_v7_migration_is_read_with_the_v6_profile(self):
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "v6")
        (self.root / self.V7_PRD).parent.mkdir(parents=True)
        self.git("mv", self.V6_PRD, self.V7_PRD)
        self.write(USER_CONFIG, '[core]\nactive_initiative = "initiative-demo"\n')
        self.git("add", "-A")
        self.git("commit", "-qm", "migrate to v7")
        report = self.run_cli("diff", "HEAD~1")[1]
        changed = [item["id"] for item in report["added"] + report["removed"] if item["id"].startswith("FR-")]
        self.assertEqual(changed, [])  # the PRD moved; its requirements did not change
        self.assertEqual(self.run_cli("--rev", "HEAD~1", "resolve", "FR-1")[1]["status"], "defined")


if __name__ == "__main__":
    unittest.main()
