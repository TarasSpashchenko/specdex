import tempfile
import unittest
from pathlib import Path

import support
from specdexlib import config
from specdexlib.config import ConfigError, expand, glob_to_regex


class GlobTest(unittest.TestCase):
    def test_double_star_slash_matches_zero_or_more_directories(self):
        regex = glob_to_regex("**/.memlog.md")
        self.assertRegex(".memlog.md", regex)
        self.assertRegex("a/b/.memlog.md", regex)

    def test_single_star_stays_within_one_directory(self):
        regex = glob_to_regex("prds/prd-*/prd.md")
        self.assertRegex("prds/prd-demo/prd.md", regex)
        self.assertNotRegex("prds/prd-demo/old/prd.md", regex)

    def test_trailing_double_star_matches_any_depth(self):
        self.assertRegex("a/.working/b/c.md", glob_to_regex("**/.working/**"))

    def test_question_mark_matches_one_character_but_not_a_slash(self):
        regex = glob_to_regex("v?.md")
        self.assertRegex("v1.md", regex)
        self.assertNotRegex("v/.md", regex)

    def test_glob_is_anchored_at_both_ends(self):
        self.assertNotRegex("x/prd.md.bak", glob_to_regex("x/prd.md"))


class ExpandTest(unittest.TestCase):
    def test_nested_variables_resolve_relative_to_the_project_root(self):
        variables = {"project-root": "", "out": "{project-root}/_bmad-output"}
        self.assertEqual(expand("{out}/planning", variables), "_bmad-output/planning")

    def test_unknown_variable_is_left_in_place(self):
        self.assertEqual(expand("{missing}/x", {}), "{missing}/x")


class IdRegexTest(unittest.TestCase):
    config = support.load_config(support.FIXTURE)

    def family_of(self, text: str) -> str | None:
        match = self.config.id_regex.search(text)
        if not match:
            return None
        return next(family for group, family in self.config.family_groups.items() if match.group(group))

    def test_positional_suffix_is_captured_separately(self):
        match = self.config.id_regex.search("see FR-12.3.")
        self.assertEqual((match.group(0), match.group("sub")), ("FR-12.3", "3"))

    def test_id_glued_to_a_word_is_not_matched(self):
        self.assertIsNone(self.config.id_regex.search("preFR-1 and FR-1x"))

    def test_longer_family_prefix_is_identified(self):
        self.assertEqual(self.family_of("SM-C3"), "SM-C")


class LoadTest(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_project_config_file_moves_the_scan_root_and_dependent_defaults(self):
        self.write("_bmad/config.toml", '[core]\noutput_folder = "{project-root}/docs/out"\n')
        loaded = config.load(self.root, support.PROFILE, None)
        self.assertEqual(loaded.scan_roots, ["docs/out"])
        self.assertEqual(loaded.variables["planning_artifacts"], "docs/out/planning-artifacts")

    def test_overlay_for_another_profile_is_rejected(self):
        overlay = self.write("overlay.toml", '[overlay]\nprofile = "some-other-profile"\n')
        with self.assertRaises(ConfigError):
            config.load(self.root, support.PROFILE, overlay)

    def test_overlay_artifact_rules_take_precedence_over_profile_rules(self):
        overlay = self.write("overlay.toml", '[[artifact]]\ntype = "custom"\nglob = "**/prd.md"\nkind = "trail"\n')
        loaded = config.load(self.root, support.PROFILE, overlay)
        self.assertEqual(loaded.artifacts[0].type, "custom")

    def test_fixture_overlay_registers_the_positional_rule(self):
        loaded = support.load_config(support.FIXTURE)
        self.assertEqual(loaded.positional["FR"].marker, "**Consequences (testable):**")


if __name__ == "__main__":
    unittest.main()
