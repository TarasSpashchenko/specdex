import unittest

import support
from specdexlib import diffing

FR3_LAST_CONSEQUENCE = "- The export contains one row per recorded session.\n"
FR3_APPENDED_CONSEQUENCE = "- The export file name includes the export date.\n"


@support.requires_git
class DiffTest(support.ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.commit_all("initial specs")
        self.replace_in(support.PRD, FR3_LAST_CONSEQUENCE, FR3_LAST_CONSEQUENCE + FR3_APPENDED_CONSEQUENCE)
        self.add_fr4()
        self.commit_all("add FR-4 and an FR-3 consequence")
        old = self.queries(revision="HEAD~1", db=self.workspace / "old.sqlite")
        new = self.queries(revision="HEAD", db=self.workspace / "new.sqlite")
        self.report = diffing.diff(old, new)

    def test_new_heading_id_is_reported_as_added(self):
        self.assertEqual([item["id"] for item in self.report["added"]], ["FR-4"])

    def test_appended_consequence_is_reported_without_shifting_earlier_ids(self):
        fr3 = next(p for p in self.report["positional"] if p["parent"] == "FR-3")
        self.assertEqual((fr3["old_count"], fr3["new_count"], fr3["kind"]), (1, 2, "appended"))

    def test_only_the_grown_requirement_is_changed_and_nothing_is_removed(self):
        self.assertEqual([item["id"] for item in self.report["changed"]], ["FR-3"])
        self.assertEqual(self.report["removed"], [])


if __name__ == "__main__":
    unittest.main()
