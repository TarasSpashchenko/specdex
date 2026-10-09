"""Regression tests for the engine fixes made after Codex's re-check: the defects the first fixes introduced (N1–N4)
and the findings it left partly resolved (A-02, A-09, A-10, A-18, A-19, A-20, A-22).
See eval/m1-tamagai/results/codex-recheck.md."""
import contextlib
import json
import os
import posixpath
import sqlite3
import tempfile
import unittest
from pathlib import Path

import support
import test_audit_authority as authority_tests
import test_audit_freshness as freshness_tests
import test_audit_safety as safety_tests
import test_audit_tickets as ticket_tests
from specdexlib import config as specdex_config
from specdexlib import coverage, diffing, extract, maintenance, store, tickets
from specdexlib.config import ConfigError
from specdexlib.index import open_index

BUDGET_CHARS = 8000
ABSENT_ID = "FR-9"
CAP_ID = "CAP-1"
CITING_SENTENCE = f"{CAP_ID} is cited here."


def spec_text(rule: str) -> str:
    """A spec defining the document-scoped CAP-1 and citing it once."""
    return f"# Spec\n\n- **{CAP_ID}** — {rule} rule.\n\n{CITING_SENTENCE}\n"


class CurrentSpecsTestCase(support.ProjectTestCase):
    def add_current_specs(self, specs: dict[str, str], extra_overlay: str = "") -> None:
        """Create one spec per name and make them all current records beside the PRD and the spine."""
        for name, path in specs.items():
            self.create(path, spec_text(name))
        records = [support.PRD, support.SPINE, *specs.values()]
        self.use_overlay(f"{extra_overlay}\n[current]\nrecords = {json.dumps(records)}\n")


# N1
class MixedHistoryCoverageTest(authority_tests.AuthorityTestCase):
    PRD_TEXT = "# PRD\n\n### FR-1: Live requirement\n\nMust work.\n\n#### Retired\n\nOld suggestion.\n"

    def setUp(self):
        super().setUp()
        self.use_overlay(authority_tests.RETIRED_SECTION_RULE)
        self.write(support.PRD, self.PRD_TEXT)

    def test_requirement_holding_a_historical_subsection_stays_defined(self):
        resolution = self.queries().resolve("FR-1")
        self.assertEqual(resolution.status, "defined")
        self.assertEqual([hit.temporal for hit in resolution.definitions], ["partly historical"])

    def test_it_stays_in_the_coverage_population(self):
        self.assertEqual([member["id"] for member in coverage.population(self.queries(), ["FR"])], ["FR-1"])

    def test_it_stays_in_the_coverage_rows_as_missing(self):
        rows = coverage.coverage(self.queries(), "tickets", ["FR"])["rows"]
        self.assertEqual([(row["id"], row["state"]) for row in rows], [("FR-1", "missing")])


# N2
class HistoricalPositionalChildTest(authority_tests.AuthorityTestCase):
    CHILD = "FR-99.1"
    CONSEQUENCE = "- Old rule."

    def setUp(self):
        super().setUp()
        self.use_overlay(authority_tests.RETIRED_SECTION_RULE)
        self.append(support.PRD, f"\n## Retired\n\n### FR-99: Old\n\n**Consequences (testable):**\n\n{self.CONSEQUENCE}\n\n"
                                 f"## Current\n\nSee {self.CHILD}.\n")

    def test_resolve_reports_historical_only_not_out_of_bounds(self):
        resolution = self.queries().resolve(self.CHILD)
        self.assertTrue(resolution.status.startswith("historical only"), resolution.status)
        self.assertEqual(len(resolution.historical), 1)

    def test_get_returns_the_historical_unit_with_a_not_current_note(self):
        hits, notes = self.queries().get(self.CHILD, BUDGET_CHARS)
        self.assertEqual([(hit.temporal, hit.text) for hit in hits], [("historical", self.CONSEQUENCE)])
        self.assertTrue(any("not a current requirement" in note for note in notes), notes)


# N3
class CoversLineTest(ticket_tests.TicketTreeTestCase):
    INITIATIVE_TOML = "_bmad-output/initiative-shelf-v1/tickets.toml"
    READING_LIST_TOML = "_bmad-output/initiative-shelf-v1/epic-reading-list/tickets.toml"
    EPIC_ONE = ("[[epic]]\nid = 1\n", 'covers = ["FR-1", "FR-2", "FR-3"]')
    ENTRY_TWO = ("[[entry]]\nid = 2\n", 'covers = ["E3", "E4"]')  # entry 1.2 has no file: its covers line is in tickets.toml
    COVERED_FR = "FR-2"  # covered by epic 1 directly and by entry 1.2 through E3

    def setUp(self):
        super().setUp()
        for path, (block_start, covers_line) in ((self.INITIATIVE_TOML, self.EPIC_ONE), (self.READING_LIST_TOML, self.ENTRY_TWO)):
            self.move_covers_before_id(path, block_start, covers_line)
        self.expected = {
            ("ticket 1", self.INITIATIVE_TOML, support.line_of(self.read(self.INITIATIVE_TOML), self.EPIC_ONE[1])),
            ("ticket 1.2", self.READING_LIST_TOML, support.line_of(self.read(self.READING_LIST_TOML), self.ENTRY_TWO[1])),
        }

    def move_covers_before_id(self, relative: str, block_start: str, covers_line: str) -> None:
        """Move a block's covers line up to directly follow its [[epic]]/[[entry]] header: still valid TOML."""
        self.replace_in(relative, f"{covers_line}\n", "")
        self.replace_in(relative, block_start, block_start.replace("\n", f"\n{covers_line}\n", 1))

    @staticmethod
    def locations(rows: list[dict]) -> set[tuple[str, str, int]]:
        return {(row["src_id"], row["path"], row["line"]) for row in rows if row["kind"] == "covers"}

    def test_covers_rows_point_at_the_covers_line(self):
        self.assertEqual(self.locations(tickets.covers_rows(self.queries(), [self.COVERED_FR])), self.expected)

    def test_refs_kind_covers_points_at_the_covers_line(self):
        _, rows, _ = self.queries().refs(self.COVERED_FR, "record", children=False, kind="covers")
        self.assertEqual(self.locations(rows), self.expected)


# N4
class DocumentScopedChainTest(CurrentSpecsTestCase):
    SPECS = {"alpha": "_bmad-output/specs/spec-alpha/SPEC.md", "beta": "_bmad-output/specs/spec-beta/SPEC.md"}
    INITIATIVE = "_bmad-output/initiative-demo/initiative-demo.md"
    INITIATIVE_TOML = "_bmad-output/initiative-demo/tickets.toml"

    def setUp(self):
        super().setUp()
        self.add_current_specs(self.SPECS)
        self.create(self.INITIATIVE, f"# Demo\n\n## References\n\n- spec — {self.SPECS['alpha']}\n")
        self.create(self.INITIATIVE_TOML, f'[[epic]]\nid = 1\nslug = "epic-demo"\ntitle = "Demo"\ncovers = ["{CAP_ID}"]\n')

    def test_chain_through_a_source_naming_one_spec_resolves(self):
        q = self.queries()
        found = [(chain.ticket, chain.covered_id, chain.state, chain.target) for chain in tickets.chains(q, tickets.load_tree(q))]
        self.assertEqual(found, [("1", CAP_ID, "resolved", CAP_ID)])


# A-02
class LookalikeDatabaseTest(support.ProjectTestCase):
    LOOKALIKE_TABLES = ("meta", "chunks", "files")

    def test_lookalike_database_with_an_extra_table_is_refused_and_keeps_it(self):
        lookalike = self.workspace / "lookalike.sqlite"
        with contextlib.closing(sqlite3.connect(lookalike)) as conn, conn:
            for table in (*self.LOOKALIKE_TABLES, "valuable_notes"):
                conn.execute(f"CREATE TABLE {table}(body TEXT)")
            conn.execute("INSERT INTO valuable_notes VALUES('keep me')")
            conn.execute(f"PRAGMA user_version={store.SCHEMA_VERSION - 1}")
        with self.assertRaises(ConfigError):
            open_index(self.config, None, lookalike)
        with contextlib.closing(sqlite3.connect(lookalike)) as conn:
            self.assertEqual(conn.execute("SELECT body FROM valuable_notes").fetchall(), [("keep me",)])


# A-09
class FieldTypeTest(support.ProjectTestCase):
    COMPANION = "missing.md"

    def parse_gaps(self, q, path: str) -> list[tuple[int, str]]:
        rows = q.conn.execute("SELECT line, detail FROM fdiag WHERE path=? AND code='parse-gap'", (path,))
        return [(row["line"], row["detail"]) for row in rows]

    def give_the_spine_a_string_companion(self) -> int:
        self.replace_in(support.SPINE, "type: architecture-spine\n", f"type: architecture-spine\ncompanions: {self.COMPANION}\n")
        return support.line_of(self.read(support.SPINE), "companions:")

    def test_string_companions_is_a_should_be_a_list_parse_gap(self):
        line = self.give_the_spine_a_string_companion()
        gaps = self.parse_gaps(self.queries(), support.SPINE)
        self.assertEqual([gap_line for gap_line, _ in gaps], [line])
        self.assertIn("should be a list", gaps[0][1])

    def test_string_companions_still_counts_as_one_companion(self):
        line = self.give_the_spine_a_string_companion()
        q = self.queries()
        companions = q.conn.execute("SELECT value, line FROM companions WHERE path=?", (support.SPINE,))
        self.assertEqual([tuple(row) for row in companions], [(self.COMPANION, line)])
        missing = q.conn.execute("SELECT path, line FROM gdiag WHERE code='missing-companion'")
        self.assertEqual([tuple(row) for row in missing], [(support.SPINE, line)])

    def test_list_type_is_a_parse_gap(self):
        self.replace_in(support.PRD, "status: final", "status: final\ntype: [prd]")
        line = support.line_of(self.read(support.PRD), "type:")
        self.assertEqual([gap_line for gap_line, _ in self.parse_gaps(self.queries(), support.PRD)], [line])


# A-10
@unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read a mode-000 directory")
class UnreadableDirectoryTest(support.ProjectTestCase):
    LOCKED_DIR = "_bmad-output/locked-notes"

    def setUp(self):
        super().setUp()
        locked = self.create(f"{self.LOCKED_DIR}/notes.md", "# Notes\n").parent
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)  # runs before the workspace cleanup, which must list the folder

    def test_unreadable_directory_is_reported_as_a_skipped_source(self):
        rows = self.queries().conn.execute("SELECT path, detail FROM gdiag WHERE code='source-skipped'").fetchall()
        self.assertEqual([row["path"] for row in rows], [self.LOCKED_DIR])
        self.assertIn("unreadable directory", rows[0]["detail"])

    def test_negative_answers_become_unknown(self):
        self.assertTrue(self.queries().resolve(ABSENT_ID).status.startswith("not defined: unknown"))


# A-18
class SymlinkGenerationTest(support.ProjectTestCase):
    def point_link_at(self, target: str) -> None:
        link = self.root / freshness_tests.LINK
        link.unlink(missing_ok=True)
        link.symlink_to(Path(target).name)

    def test_retargeting_a_symlink_between_equal_files_changes_the_generation(self):
        for target in (freshness_tests.FIRST_TARGET, freshness_tests.SECOND_TARGET):
            self.create(target, freshness_tests.EQUAL_TEXT)
        self.point_link_at(freshness_tests.FIRST_TARGET)
        before = self.open_index().generation
        self.point_link_at(freshness_tests.SECOND_TARGET)
        self.assertNotEqual(self.open_index().generation, before)


# A-19: the profile's spec glob ({output_folder}/specs/spec-*/SPEC.md) cannot reach two folders sharing a basename,
# so an overlay [[artifact]] rule adds one level of nesting.
class SameBasenameDiffTest(CurrentSpecsTestCase):
    SPECS = {"a": "_bmad-output/specs/a/spec-shared/SPEC.md", "b": "_bmad-output/specs/b/spec-shared/SPEC.md"}
    NESTED_SPEC_RULE = '[[artifact]]\ntype = "spec"\nglob = "{output_folder}/specs/*/spec-*/SPEC.md"\nkind = "owner"\nscope = "document"\n'

    def setUp(self):
        super().setUp()
        self.add_current_specs(self.SPECS, self.NESTED_SPEC_RULE)
        self.old = self.queries(db=self.workspace / "old.sqlite")
        self.replace_in(self.SPECS["a"], spec_text("a"), spec_text("changed a"))
        self.new = self.queries(db=self.workspace / "new.sqlite")

    def key(self, name: str) -> str:
        return f"{CAP_ID}{diffing.SCOPE_MARK}{posixpath.dirname(self.SPECS[name])}"

    def test_editing_one_folder_reports_only_its_key_changed(self):
        self.assertEqual([item["id"] for item in diffing.diff(self.old, self.new)["changed"]], [self.key("a")])

    def test_citations_count_only_those_in_the_keys_folder(self):
        citing_line = support.line_of(spec_text("a"), CITING_SENTENCE)
        for name, path in self.SPECS.items():
            with self.subTest(name):
                self.assertEqual(diffing._citations(self.new, self.key(name)), [f"{path}:{citing_line}"])


# A-20
class MemberBoundTest(unittest.TestCase):
    BOUND = 5
    ALPHA_FAMILY = "[[family]]\nname = \"OPT\"\npattern = 'OPT-(?P<key>[A-Z])'\nkey = \"alpha\"\nowner = [\"prd\"]\n"
    FORMS = {  # form -> members(n): a range of n members, and the IDs it cites when expanded
        "long": lambda n: (f"FR-1–FR-{n}", {f"FR-{k}" for k in range(1, n + 1)}),
        "short": lambda n: (f"FR-1–{n}", {f"FR-{k}" for k in range(1, n + 1)}),
        "positional": lambda n: (f"FR-1.1–FR-1.{n}", {f"FR-1.{k}" for k in range(1, n + 1)}),
        "alphabetic": lambda n: (f"OPT-A–OPT-{chr(ord('A') + n - 1)}", {f"OPT-{chr(ord('A') + k)}" for k in range(n)}),
    }

    @classmethod
    def setUpClass(cls):
        workdir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(workdir.cleanup)
        default_bound = "max_members = 200"
        profile_text = support.PROFILE.read_text(encoding="utf-8")
        assert default_bound in profile_text, "the profile's [ranges] bound moved"
        profile = Path(workdir.name) / "profile.toml"
        profile.write_text(profile_text.replace(default_bound, f"max_members = {cls.BOUND}"), encoding="utf-8")
        overlay = Path(workdir.name) / "overlay.toml"
        overlay.write_text(support.OVERLAY.read_text(encoding="utf-8") + "\n" + cls.ALPHA_FAMILY, encoding="utf-8")
        cls.config = specdex_config.load(support.FIXTURE, profile, overlay)

    def facts(self, text: str) -> extract.FileFacts:
        return extract.extract(self.config, support.PRD, f"{text} ship together.")

    def test_range_of_exactly_the_bound_expands(self):
        for form, members in self.FORMS.items():
            with self.subTest(form):
                text, ids = members(self.BOUND)
                result = self.facts(text)
                self.assertEqual({o.id for o in result.occurrences}, ids)
                self.assertEqual(result.diagnostics, [])

    def test_range_one_past_the_bound_is_not_expanded(self):
        for form, members in self.FORMS.items():
            with self.subTest(form):
                result = self.facts(members(self.BOUND + 1)[0])
                self.assertFalse(any(o.via_range for o in result.occurrences))
                self.assertEqual([code for code, _, _, _ in result.diagnostics], ["bad-range"])


# A-22
class ValidatorContractTest(support.ProjectTestCase):
    FINDINGS_NOT_A_LIST = '{"findings": "none"}'
    FINDING_NOT_AN_OBJECT = '{"findings": ["x"]}'

    def lint(self) -> maintenance.LintReport:
        return maintenance.lint(self.queries(), "record", validators=True)

    def install_trusted_validator(self, stdout: str) -> Path:
        """A stand-in validator plus a profile copy whose [binding] records its hash (see test_audit_safety)."""
        marker = self.workspace / "validator-ran.txt"
        script = self.create(f"{safety_tests.AGENTS_SKILLS}/{safety_tests.VALIDATOR_SCRIPT}", safety_tests.validator_source(marker, stdout, 0))
        recorded = next(entry["sha256"] for entry in self.config.binding["files"] if entry["path"] == safety_tests.VALIDATOR_SCRIPT)
        profile = self.workspace / "profile.toml"
        profile.write_text(support.PROFILE.read_text(encoding="utf-8").replace(recorded, safety_tests.sha256_of(script)), encoding="utf-8")
        self.reload_config(profile=profile)
        return marker

    def test_missing_validator_is_reported_not_run(self):
        not_run = [finding.detail for finding in self.lint().findings if finding.code == "validator-not-run"]
        self.assertEqual(len(not_run), 1)
        self.assertIn("not installed", not_run[0])

    def test_verified_validator_whose_findings_is_not_a_list_is_reported_failed(self):
        marker = self.install_trusted_validator(self.FINDINGS_NOT_A_LIST)
        report = self.lint()
        self.assertTrue(marker.exists(), "the hash-verified validator did not run")
        self.assertIn("validator-failed", safety_tests.finding_codes(report))

    def test_verified_validator_whose_finding_is_not_an_object_is_reported_failed(self):
        self.install_trusted_validator(self.FINDING_NOT_AN_OBJECT)
        self.assertIn("validator-failed", safety_tests.finding_codes(self.lint()))


if __name__ == "__main__":
    unittest.main()
