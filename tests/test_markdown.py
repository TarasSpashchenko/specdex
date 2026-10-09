import unittest
from textwrap import dedent

import support  # noqa: F401  (puts specdexlib on sys.path)
from specdexlib import markdown

SECTIONS = dedent("""\
    # Title
    intro
    ## A
    a text
    ### A.1
    deep text
    ## B
    b text
    """)


def parse(text: str) -> markdown.Document:
    return markdown.parse(dedent(text))


class SectionTest(unittest.TestCase):
    def test_heading_path_lists_titles_from_the_root(self):
        doc = markdown.parse(SECTIONS)
        self.assertEqual(doc.heading_path(doc.section_at(6)), ["Title", "A", "A.1"])

    def test_section_ends_before_the_next_heading_of_the_same_level(self):
        doc = markdown.parse(SECTIONS)
        section_a = next(s for s in doc.sections if s.title == "A")
        self.assertEqual((section_a.start, section_a.end), (3, 6))

    def test_last_section_runs_to_the_end_of_the_file(self):
        doc = markdown.parse(SECTIONS)
        self.assertEqual(doc.sections[0].end, len(doc.lines))


class FenceTest(unittest.TestCase):
    TEXT = """\
        ## Real
        ```
        ## Not a heading
        ```
        after
        """

    def test_heading_inside_a_fence_is_not_a_section(self):
        doc = parse(self.TEXT)
        self.assertEqual([s.title for s in doc.sections], ["Real"])

    def test_fence_lines_including_markers_are_marked_fenced(self):
        doc = parse(self.TEXT)
        self.assertEqual(doc.fenced, {2, 3, 4})

    def test_unclosed_fence_is_reported_at_its_opening_line(self):
        doc = parse("text\n~~~\ncode\n")
        self.assertEqual(doc.unclosed_fence, 2)


class ListItemTest(unittest.TestCase):
    def test_nested_item_records_its_parent_and_depth(self):
        doc = parse("""\
            - outer
              - inner
            """)
        outer, inner = doc.items
        self.assertEqual((inner.parent, inner.depth), (0, 1))
        self.assertEqual(outer.end, 2)

    def test_lazy_continuation_line_extends_the_item(self):
        doc = parse("""\
            - first line
            lazy continuation
            - next
            """)
        self.assertEqual((doc.items[0].start, doc.items[0].end), (1, 2))
        self.assertEqual(doc.paragraphs, [])

    def test_unindented_text_after_a_blank_line_ends_the_list(self):
        doc = parse("""\
            - item

            paragraph
            """)
        self.assertEqual(doc.items[0].end, 1)
        self.assertEqual([(p.start, p.end) for p in doc.paragraphs], [(3, 3)])

    def test_table_inside_an_item_extends_the_item_and_keeps_its_rows(self):
        doc = parse("""\
            - item with a table
              | key | value |
              |---|---|
              | a | 1 |
            - next
            """)
        self.assertEqual(doc.items[0].end, 4)
        self.assertEqual([(r.line, r.cells, r.header) for r in doc.rows], [(4, ["a", "1"], ["key", "value"])])


class TableTest(unittest.TestCase):
    def test_pipe_inside_inline_code_does_not_split_a_cell(self):
        self.assertEqual(markdown.split_cells("| `a|b` | c |"), ["`a|b`", "c"])

    def test_escaped_pipe_does_not_split_a_cell(self):
        self.assertEqual(markdown.split_cells(r"| a \| b | c |"), [r"a \| b", "c"])


class FrontmatterRangeTest(unittest.TestCase):
    def test_frontmatter_range_includes_both_fences(self):
        doc = parse("""\
            ---
            title: x
            ---
            # Body
            """)
        self.assertEqual(doc.frontmatter, (1, 3))
        self.assertEqual(doc.sections[0].start, 4)

    def test_unclosed_frontmatter_is_treated_as_body(self):
        doc = parse("---\ntitle: x\n")
        self.assertIsNone(doc.frontmatter)


if __name__ == "__main__":
    unittest.main()
