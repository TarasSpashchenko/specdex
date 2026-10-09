"""Shared test setup: a private copy of the synthetic mini BMAD project and a private index file."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "skills" / "specdex" / "scripts"))

from specdexlib import config as specdex_config  # noqa: E402
from specdexlib.index import Index, open_index  # noqa: E402
from specdexlib.queries import Queries  # noqa: E402

FIXTURE = TESTS_DIR / "fixtures" / "mini-project"
PROFILE = REPO_ROOT / "skills" / "specdex" / "assets" / "profile-bmad-6.13.0-next.toml"
OVERLAY = FIXTURE / "overlay.toml"

PRD = "_bmad-output/planning-artifacts/prds/prd-demo-2026-01-01/prd.md"
PRD_SHORT = "prd-demo-2026-01-01/prd.md"  # the unique path suffix the engine itself prints
TRAIL = "_bmad-output/planning-artifacts/prds/prd-demo-2026-01-01/review-prd.md"
SPINE = "_bmad-output/planning-artifacts/architecture/architecture-demo-2026-01-02/ARCHITECTURE-SPINE.md"
MEMLOG = "_bmad-output/planning-artifacts/architecture/architecture-demo-2026-01-02/.memlog.md"
RELEASE_SCOPE_HEADING = "## 2. Release Scope"

# Commits must not depend on the developer's git configuration (signing, hooks, identity).
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "specdex tests",
    "GIT_AUTHOR_EMAIL": "tests@example.invalid",
    "GIT_COMMITTER_NAME": "specdex tests",
    "GIT_COMMITTER_EMAIL": "tests@example.invalid",
}
requires_git = unittest.skipUnless(shutil.which("git"), "git CLI not installed")


def load_config(project_root: Path) -> specdex_config.Config:
    return specdex_config.load(project_root, PROFILE, OVERLAY)


def fixture_text(relative: str) -> str:
    return (FIXTURE / relative).read_text(encoding="utf-8")


def line_of(text: str, needle: str) -> int:
    """1-based number of the first line containing needle."""
    for number, line in enumerate(text.split("\n"), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found")


class ProjectTestCase(unittest.TestCase):
    """Each test works on its own copy of the fixture project, indexed into its own database file."""

    def setUp(self) -> None:
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.workspace = Path(workspace.name)
        self.root = self.workspace / "project"
        shutil.copytree(FIXTURE, self.root)
        self.config = load_config(self.root)
        self.db = self.workspace / "index.sqlite"

    def open_index(self, revision: str | None = None, db: Path | None = None) -> Index:
        index = open_index(self.config, revision, db or self.db)
        self.addCleanup(index.conn.close)
        return index

    def queries(self, revision: str | None = None, db: Path | None = None) -> Queries:
        return Queries(self.open_index(revision, db))

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        (self.root / relative).write_text(text, encoding="utf-8")

    def create(self, relative: str, text: str) -> Path:
        """Write a new file, creating its folders; returns its absolute path."""
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def reload_config(self, overlay: Path | None = None, profile: Path | None = None) -> None:
        """Reload the configuration (after a project config change), optionally from another overlay or profile."""
        self.config = specdex_config.load(self.root, profile or self.config.profile_path, overlay or self.config.overlay_path)

    def use_overlay(self, extra: str) -> None:
        """Use the fixture overlay plus extra TOML, written outside the project like any overlay under test."""
        overlay = self.workspace / "overlay.toml"
        overlay.write_text(OVERLAY.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
        self.reload_config(overlay=overlay)

    def replace_in(self, relative: str, old: str, new: str) -> None:
        text = self.read(relative)
        self.assertIn(old, text)
        self.write(relative, text.replace(old, new, 1))

    def add_fr4(self) -> None:
        """Insert a new requirement FR-4 just before the PRD's release scope section."""
        self.replace_in(PRD, RELEASE_SCOPE_HEADING, f"### FR-4: Audit log\n\nEvery sign-in is logged.\n\n{RELEASE_SCOPE_HEADING}")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *args], env=GIT_ENV, check=True, capture_output=True)

    def commit_all(self, message: str) -> None:
        if not (self.root / ".git").exists():
            self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
