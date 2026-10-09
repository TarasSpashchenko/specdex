import unittest

import support


@support.requires_git
class GitRevisionTest(support.ProjectTestCase):
    def setUp(self):
        super().setUp()
        self.commit_all("initial specs")

    def test_revision_index_reads_committed_text_not_worktree_edits(self):
        self.add_fr4()
        committed = self.queries(revision="HEAD", db=self.workspace / "head.sqlite")
        self.assertTrue(committed.resolve("FR-4").status.startswith("not defined"))
        self.assertEqual(self.queries().resolve("FR-4").status, "defined")

    def test_revision_index_is_labelled_with_its_commit(self):
        index = self.open_index(revision="HEAD", db=self.workspace / "head.sqlite")
        self.assertTrue(index.mode.startswith("commit:"))

    def test_one_index_file_reused_for_two_revisions_serves_each_revision(self):
        shared = self.workspace / "shared.sqlite"
        self.queries(revision="HEAD", db=shared)
        self.add_fr4()
        self.commit_all("add FR-4")
        self.assertEqual(self.queries(revision="HEAD", db=shared).resolve("FR-4").status, "defined")


if __name__ == "__main__":
    unittest.main()
