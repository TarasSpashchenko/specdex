import unittest
from textwrap import dedent

import support  # noqa: F401  (puts specdexlib on sys.path)
from specdexlib import yamlfm

BODY_FIRST_LINE = 2  # the line after the opening "---" fence


def parse(text: str) -> yamlfm.Frontmatter:
    return yamlfm.parse(dedent(text).split("\n"), BODY_FIRST_LINE)


def entry(frontmatter: yamlfm.Frontmatter, path: str) -> yamlfm.Entry:
    return next(e for e in frontmatter.entries if e.path == path)


class FrontmatterTest(unittest.TestCase):
    def test_scalar_keeps_its_document_line(self):
        fm = parse("""\
            title: Demo
            status: final
            """)
        self.assertEqual(entry(fm, "status").line, BODY_FIRST_LINE + 1)
        self.assertEqual(fm.get("status"), "final")

    def test_nested_mapping_uses_dotted_paths_and_spans_its_children(self):
        fm = parse("""\
            colors:
              primary: '#000'
              accent: "#fff"
            """)
        self.assertEqual(fm.get("colors.accent"), "#fff")
        self.assertEqual((entry(fm, "colors").line, entry(fm, "colors").end), (BODY_FIRST_LINE, BODY_FIRST_LINE + 2))

    def test_block_list_collects_its_items(self):
        fm = parse("""\
            owners:
              - pm
              - architect
            """)
        self.assertEqual(fm.get("owners"), ["pm", "architect"])

    def test_inline_list_unquotes_items(self):
        self.assertEqual(parse("tags: [a, 'b, c', \"d\"]").get("tags"), ["a", "b, c", "d"])

    def test_unsupported_line_is_reported_as_a_problem(self):
        fm = parse("""\
            title: Demo
            this line is not yaml
            """)
        self.assertEqual(fm.problems[0][0], BODY_FIRST_LINE + 1)
        self.assertEqual(fm.get("title"), "Demo")


if __name__ == "__main__":
    unittest.main()
