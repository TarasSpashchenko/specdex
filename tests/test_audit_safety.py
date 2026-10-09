"""Regression tests for the audit's safety findings: validator execution (A-01, A-22), index location and
ownership (A-02) and source containment (A-10). See eval/m1-tamagai/results/codex-audit.md."""
import contextlib
import hashlib
import io
import os
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

import support
from specdexlib import cli, maintenance
from specdexlib.config import ConfigError
from specdexlib.index import open_index

VALIDATOR_SCRIPT = "bmad-architecture/scripts/lint_spine.py"  # as the profile's [binding] records it
AGENTS_SKILLS, CLAUDE_SKILLS = ".agents/skills", ".claude/skills"
CLEAN_OUTPUT = '{"findings": []}'
FAILING_VALIDATORS = {  # case -> (stdout, exit code)
    "non-zero exit": (CLEAN_OUTPUT, 7),
    "ok false": ('{"ok": false, "error": "spine unreadable"}', 0),
    "bad JSON": ("this is not JSON", 0),
}
NON_OBJECT_JSON = "[]"  # valid JSON that breaks the findings-object contract
SPECDEX_APPLICATION_ID = 0x53445831  # "SDX1": the on-disk marker of a specdex index
SECRET_WORD = "zeppelinsecret"  # appears only in files outside the project


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validator_source(marker: Path, stdout: str, exit_code: int) -> str:
    """A stand-in lint_spine.py that leaves a marker file whenever it is executed."""
    return (f"import sys\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
            f"print({stdout!r})\nsys.exit({exit_code})\n")


def finding_codes(report: maintenance.LintReport) -> list[str]:
    return [finding.code for finding in report.findings]


class ValidatorTest(support.ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.marker = self.workspace / "validator-ran.txt"
        self.recorded_hash = next(entry["sha256"] for entry in self.config.binding["files"] if entry["path"] == VALIDATOR_SCRIPT)

    def install_validator(self, stdout: str = CLEAN_OUTPUT, exit_code: int = 0, skill_root: str = AGENTS_SKILLS) -> Path:
        return self.create(f"{skill_root}/{VALIDATOR_SCRIPT}", validator_source(self.marker, stdout, exit_code))

    def trust(self, script: Path) -> None:
        """Load a profile copy whose [binding] records this script's hash, as if the profile were built against it."""
        profile = self.workspace / "profile.toml"
        profile.write_text(support.PROFILE.read_text(encoding="utf-8").replace(self.recorded_hash, sha256_of(script)), encoding="utf-8")
        self.reload_config(profile=profile)

    def lint(self, revision: str | None = None, db: Path | None = None) -> maintenance.LintReport:
        return maintenance.lint(self.queries(revision, db), "record", validators=True)

    def assert_not_run(self, skill_root: str) -> None:
        self.install_validator(skill_root=skill_root)
        codes = finding_codes(self.lint())
        self.assertFalse(self.marker.exists(), "an unverified validator was executed")
        self.assertIn("validator-not-run", codes)

    # A-01
    def test_unverified_validator_under_agents_skills_is_not_executed(self):
        self.assert_not_run(AGENTS_SKILLS)

    # A-01
    def test_unverified_validator_under_claude_skills_is_not_executed(self):
        self.assert_not_run(CLAUDE_SKILLS)

    # A-22 control: the hash-verified path really executes, so the failure cases below are reachable.
    def test_hash_verified_validator_is_executed(self):
        self.trust(self.install_validator())
        report = self.lint()
        self.assertTrue(self.marker.exists())
        self.assertFalse({"validator-not-run", "validator-failed"} & set(finding_codes(report)))

    # A-22
    def test_failing_hash_verified_validator_is_reported_failed(self):
        for case, (stdout, exit_code) in FAILING_VALIDATORS.items():
            with self.subTest(case):
                self.trust(self.install_validator(stdout, exit_code))
                self.assertIn("validator-failed", finding_codes(self.lint()))

    # A-22
    def test_verified_validator_printing_json_that_is_not_an_object_is_reported_failed(self):
        self.trust(self.install_validator(NON_OBJECT_JSON))
        self.assertIn("validator-failed", finding_codes(self.lint()))

    # A-22
    @support.requires_git
    def test_revision_index_never_runs_validators(self):
        self.trust(self.install_validator())
        self.commit_all("specs and a trusted validator")
        report = self.lint(revision="HEAD", db=self.workspace / "head.sqlite")
        self.assertFalse(self.marker.exists())
        not_run = [f.detail for f in report.findings if f.code == "validator-not-run"]
        self.assertEqual(len(not_run), 1)
        self.assertIn("revision", not_run[0])


class IndexLocationTest(support.ProjectTestCase):
    def test_db_inside_the_project_is_refused(self):
        inside = self.root / "index.sqlite"
        with self.assertRaises(ConfigError):
            open_index(self.config, None, inside)
        self.assertFalse(inside.exists())

    def test_db_reaching_the_project_through_a_symlink_is_refused(self):
        alias = self.workspace / "project-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ConfigError):
            open_index(self.config, None, alias / "index.sqlite")

    def test_cli_exits_with_a_config_error_for_a_db_inside_the_project(self):
        argv = ["--project", str(self.root), "--overlay", str(support.OVERLAY), "--db", str(self.root / "index.sqlite"), "status"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(argv), cli.EXIT_CONFIG)

    def test_xdg_cache_home_inside_the_project_is_refused(self):
        cache = self.root / ".cache"
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(cache)}), self.assertRaises(ConfigError):
            open_index(self.config)
        self.assertFalse(cache.exists())

    def test_foreign_sqlite_file_is_refused_and_keeps_its_data(self):
        foreign = self.workspace / "notes.sqlite"
        with contextlib.closing(sqlite3.connect(foreign)) as conn, conn:
            conn.execute("CREATE TABLE valuable_notes(body TEXT)")
            conn.execute("INSERT INTO valuable_notes VALUES('keep me')")
        with self.assertRaises(ConfigError):
            open_index(self.config, None, foreign)
        with contextlib.closing(sqlite3.connect(foreign)) as conn:
            self.assertEqual(conn.execute("SELECT body FROM valuable_notes").fetchall(), [("keep me",)])

    def test_foreign_sqlite_file_keeps_its_journal_mode(self):
        foreign = self.workspace / "notes.sqlite"
        with contextlib.closing(sqlite3.connect(foreign)) as conn:
            conn.execute("CREATE TABLE valuable_notes(body TEXT)")
            before = conn.execute("PRAGMA journal_mode").fetchone()[0]
        with self.assertRaises(ConfigError):
            open_index(self.config, None, foreign)
        with contextlib.closing(sqlite3.connect(foreign)) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], before)

    def test_index_file_carries_the_specdex_application_id(self):
        index = self.open_index()
        self.assertEqual(index.conn.execute("PRAGMA application_id").fetchone()[0], SPECDEX_APPLICATION_ID)


class SourceContainmentTest(support.ProjectTestCase):
    EXTERNAL_LINK = "_bmad-output/external.md"
    EXTERNAL_DIR_LINK = "_bmad-output/external-notes"
    UNREADABLE = "_bmad-output/locked.md"

    def outside(self, relative: str) -> Path:
        """A file outside the project holding the secret word."""
        path = self.workspace / "outside" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# External\n\n{SECRET_WORD}\n", encoding="utf-8")
        return path

    def link_external_file(self) -> None:
        (self.root / self.EXTERNAL_LINK).symlink_to(self.outside("private.md"))

    def skipped(self, q) -> set[tuple[str, str]]:
        rows = q.conn.execute("SELECT path, severity FROM gdiag WHERE code='source-skipped'")
        return {(row["path"], row["severity"]) for row in rows}

    def test_file_symlink_leading_outside_is_not_indexed_and_is_reported(self):
        self.link_external_file()
        q = self.queries()
        self.assertNotIn(self.EXTERNAL_LINK, q.files)
        self.assertIn((self.EXTERNAL_LINK, "high"), self.skipped(q))
        self.assertEqual(q.search(SECRET_WORD, "all", 5)[0], [])

    def test_directory_symlink_leading_outside_is_not_indexed_and_is_reported(self):
        (self.root / self.EXTERNAL_DIR_LINK).symlink_to(self.outside("notes/private.md").parent, target_is_directory=True)
        q = self.queries()
        self.assertFalse([path for path in q.files if path.startswith(self.EXTERNAL_DIR_LINK + "/")])
        self.assertIn((self.EXTERNAL_DIR_LINK, "high"), self.skipped(q))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read a mode-000 file")
    def test_unreadable_file_is_reported(self):
        locked = self.create(self.UNREADABLE, "# Locked\n")
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        self.assertIn((self.UNREADABLE, "high"), self.skipped(self.queries()))

    def test_skipped_source_turns_negative_answers_unknown(self):
        self.link_external_file()
        self.assertTrue(self.queries().resolve("FR-9").status.startswith("not defined: unknown"))


if __name__ == "__main__":
    unittest.main()
