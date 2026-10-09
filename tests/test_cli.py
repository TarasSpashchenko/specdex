import contextlib
import io
import json
import unittest

import support
from specdexlib import cli


class CliTest(support.ProjectTestCase):
    def run_cli(self, *args: str, overlay=support.OVERLAY) -> tuple[int, str]:
        """Exit code and stdout of one specdex invocation against the project copy."""
        argv = ["--project", str(self.root), "--overlay", str(overlay), "--db", str(self.db), *args]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(argv)
        return code, stdout.getvalue()

    def test_resolving_a_defined_id_exits_ok(self):
        self.assertEqual(self.run_cli("resolve", "FR-1")[0], cli.EXIT_OK)

    def test_resolving_an_unknown_id_exits_with_findings(self):
        self.assertEqual(self.run_cli("resolve", "FR-9")[0], cli.EXIT_FINDINGS)

    def test_getting_an_unknown_file_exits_not_found(self):
        self.assertEqual(self.run_cli("get", "missing.md:1")[0], cli.EXIT_USAGE)

    def test_overlay_for_another_profile_exits_with_a_config_error(self):
        overlay = self.workspace / "wrong-overlay.toml"
        overlay.write_text('[overlay]\nprofile = "some-other-profile"\n', encoding="utf-8")
        self.assertEqual(self.run_cli("status", overlay=overlay)[0], cli.EXIT_CONFIG)

    def test_lint_over_all_files_exits_with_findings_for_the_dangling_trail_citation(self):
        self.assertEqual(self.run_cli("lint", "--scope", "all", "--no-validators")[0], cli.EXIT_FINDINGS)

    def test_json_resolution_parses(self):
        code, out = self.run_cli("--json", "resolve", "FR-1")
        resolution = json.loads(out)
        self.assertEqual((code, resolution["status"], resolution["children"]), (cli.EXIT_OK, "defined", 3))

    def test_json_search_parses_and_names_full_paths(self):
        _, out = self.run_cli("--json", "search", "csv", "export")
        self.assertEqual(json.loads(out)["hits"][0]["path"], support.PRD)


if __name__ == "__main__":
    unittest.main()
