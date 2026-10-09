"""Smoke test for the shipped specdex script: a minimal v7 project, run as a subprocess.

The full suite lives in the specdex repository's tests/ folder; this one ships with the skill.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "specdex.py"
PRD = "_bmad-output/initiative-demo/prd-demo/prd-demo.md"


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SpecdexSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        workdir = tempfile.TemporaryDirectory()
        self.addCleanup(workdir.cleanup)
        self.root = Path(workdir.name) / "project"
        self.cache = Path(workdir.name) / "cache"
        write(self.root, "_bmad/config.toml", '[core]\noutput_folder = "{project-root}/_bmad-output"\n')
        write(self.root, "_bmad/custom/config.user.toml", '[core]\nactive_initiative = "initiative-demo"\n')
        write(self.root, PRD, "# PRD: Demo\n\n## 4. Features\n\n- **FR-1. Sign in.** A user signs in with email.\n\nFR-1 is the entry point.\n")

    def run_specdex(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "XDG_CACHE_HOME": str(self.cache)}
        return subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.root), "--json", *args],
                              capture_output=True, text=True, env=env, check=False)

    def test_status_picks_the_v7_profile(self):
        done = self.run_specdex("status")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["profile"], "bmad-v7")

    def test_resolve_finds_the_definition_in_the_active_initiative(self):
        done = self.run_specdex("resolve", "FR-1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([d["path"] for d in json.loads(done.stdout)["definitions"]], [PRD])

    def test_unknown_id_exits_with_findings(self):
        self.assertEqual(self.run_specdex("resolve", "FR-9").returncode, 1)

    def test_fails_with_one_line(self):
        for setup, args, code in ((lambda: None, ("get", "no-such-file.md:1"), 2),
                                  (lambda: write(self.root, "_bmad/custom/specdex.toml", "[workflow\n"), ("status",), 3)):
            with self.subTest(args=args):
                setup()
                done = self.run_specdex(*args)
                self.assertEqual((done.returncode, done.stderr.count("\n")), (code, 1), done.stderr)

    def test_nothing_is_written_in_the_project(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        self.run_specdex("status")
        self.assertEqual(sorted(p.relative_to(self.root) for p in self.root.rglob("*")), before)


if __name__ == "__main__":
    unittest.main()
