"""Fence-aware Markdown block parser.

Produces line-addressed blocks (1-based, inclusive): frontmatter, sections,
table rows, list items and paragraphs. It deliberately supports only the
CommonMark subset BMAD documents use; anything else stays inside a paragraph
and is still searchable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LIST_ITEM = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])[ \t]+")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


@dataclass(slots=True)
class Section:
    level: int
    title: str
    start: int
    end: int
    parent: int | None  # index into Document.sections


@dataclass(slots=True)
class Row:
    line: int
    cells: list[str]
    header: list[str]
    header_line: int
    indent: int


@dataclass(slots=True)
class Item:
    start: int
    end: int
    indent: int
    depth: int
    parent: int | None  # index into Document.items
    first_text: str     # text after the list marker on the lead line


@dataclass(slots=True)
class Paragraph:
    start: int
    end: int


@dataclass(slots=True)
class Document:
    lines: list[str]
    frontmatter: tuple[int, int] | None = None  # line range including the --- fences
    sections: list[Section] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    fenced: set[int] = field(default_factory=set)  # line numbers inside code fences
    unclosed_fence: int | None = None
    unclosed_frontmatter: bool = False
    line_section: list[int | None] = field(default_factory=list)  # innermost section per line (index 0 unused)

    def text(self, start: int, end: int) -> str:
        return "\n".join(self.lines[start - 1:end])

    def section_at(self, line: int) -> int | None:
        """Index of the innermost section containing the line."""
        return self.line_section[line] if 0 < line < len(self.line_section) else None

    def heading_path(self, index: int | None) -> list[str]:
        path: list[str] = []
        while index is not None:
            path.append(self.sections[index].title)
            index = self.sections[index].parent
        return list(reversed(path))


def split_cells(line: str) -> list[str]:
    """Split a table row on unescaped pipes outside inline code."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells, current, in_code = [], [], False
    previous = ""
    for char in body:
        if char == "`":
            in_code = not in_code
        if char == "|" and not in_code and previous != "\\":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        previous = char
    cells.append("".join(current).strip())
    return cells


def parse(text: str) -> Document:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    doc = Document(lines=lines)
    body_start = _parse_frontmatter(doc)
    _mark_fences(doc, body_start)
    _parse_sections(doc, body_start)
    _index_sections(doc)
    _parse_blocks(doc, body_start)
    return doc


def _parse_frontmatter(doc: Document) -> int:
    if not doc.lines or doc.lines[0].rstrip() != "---":
        return 1
    for number in range(2, len(doc.lines) + 1):
        if doc.lines[number - 1].rstrip() == "---":
            doc.frontmatter = (1, number)
            return number + 1
    doc.unclosed_frontmatter = True
    return 1


def _mark_fences(doc: Document, body_start: int) -> None:
    opener: str | None = None
    open_line = 0
    for number in range(body_start, len(doc.lines) + 1):
        line = doc.lines[number - 1]
        match = FENCE.match(line)
        if opener is None:
            if match:
                opener, open_line = match.group(1), number
                doc.fenced.add(number)
            continue
        doc.fenced.add(number)
        if match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener) and not line.strip()[len(match.group(1)):].strip():
            opener = None
    if opener is not None:
        doc.unclosed_fence = open_line


def _parse_sections(doc: Document, body_start: int) -> None:
    stack: list[int] = []
    last = len(doc.lines)
    for number in range(body_start, last + 1):
        if number in doc.fenced:
            continue
        match = HEADING.match(doc.lines[number - 1])
        if not match:
            continue
        level = len(match.group(1))
        while stack and doc.sections[stack[-1]].level >= level:
            doc.sections[stack.pop()].end = number - 1
        parent = stack[-1] if stack else None
        doc.sections.append(Section(level, match.group(2).strip(), number, last, parent))
        stack.append(len(doc.sections) - 1)


def _index_sections(doc: Document) -> None:
    doc.line_section = [None] * (len(doc.lines) + 1)
    for index, section in enumerate(doc.sections):  # parents precede children, so children overwrite
        for number in range(section.start, section.end + 1):
            doc.line_section[number] = index


def _parse_blocks(doc: Document, body_start: int) -> None:
    heading_lines = {section.start for section in doc.sections}
    number = body_start
    last = len(doc.lines)
    open_items: list[int] = []  # stack of item indices whose content may continue
    while number <= last:
        line = doc.lines[number - 1]
        if number in doc.fenced or number in heading_lines:
            if number in heading_lines:
                open_items.clear()
            number += 1
            continue
        if not line.strip():
            number += 1
            continue
        if _is_table_start(doc, number):
            number = _consume_table(doc, number, open_items)
            continue
        item_match = LIST_ITEM.match(line)
        indent = _indent_width(line)
        if item_match:
            _open_item(doc, number, item_match, open_items)
            number += 1
            continue
        if open_items and _continues_item(doc, open_items, number, indent):
            _extend_items(doc, open_items, number)
            number += 1
            continue
        open_items.clear()
        number = _consume_paragraph(doc, number, heading_lines)


def _indent_width(line: str) -> int:
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip(" "))


def _is_table_start(doc: Document, number: int) -> bool:
    line = doc.lines[number - 1]
    if not line.lstrip().startswith("|") or number >= len(doc.lines):
        return False
    return bool(TABLE_SEPARATOR.match(doc.lines[number])) and "|" in doc.lines[number]


def _consume_table(doc: Document, number: int, open_items: list[int]) -> int:
    header_line = number
    header = split_cells(doc.lines[number - 1])
    indent = _indent_width(doc.lines[number - 1])
    if open_items:
        _extend_items(doc, open_items, number + 1)
    current = number + 2
    while current <= len(doc.lines) and current not in doc.fenced:
        line = doc.lines[current - 1]
        if not line.lstrip().startswith("|"):
            break
        doc.rows.append(Row(current, split_cells(line), header, header_line, indent))
        if open_items and indent > doc.items[open_items[-1]].indent:
            _extend_items(doc, open_items, current)
        current += 1
    if open_items and indent <= doc.items[open_items[-1]].indent:
        open_items.clear()
    return current


def _open_item(doc: Document, number: int, match: re.Match, open_items: list[int]) -> None:
    indent = _indent_width(match.group(1))
    while open_items and doc.items[open_items[-1]].indent >= indent:
        open_items.pop()
    parent = open_items[-1] if open_items else None
    depth = doc.items[parent].depth + 1 if parent is not None else 0
    first_text = doc.lines[number - 1][match.end():]
    doc.items.append(Item(number, number, indent, depth, parent, first_text))
    open_items.append(len(doc.items) - 1)
    if parent is not None:
        _extend_items(doc, open_items[:-1], number)


def _continues_item(doc: Document, open_items: list[int], number: int, indent: int) -> bool:
    """A non-item line continues the innermost open item when indented past its marker,
    or lazily when it directly follows the item's text with no blank line (CommonMark)."""
    while open_items and indent <= doc.items[open_items[-1]].indent:
        if doc.items[open_items[-1]].end == number - 1:
            return True
        open_items.pop()
    return bool(open_items)


def _extend_items(doc: Document, open_items: list[int], number: int) -> None:
    for index in open_items:
        if doc.items[index].end < number:
            doc.items[index].end = number


def _consume_paragraph(doc: Document, number: int, heading_lines: set[int]) -> int:
    start = number
    current = number
    while current <= len(doc.lines):
        line = doc.lines[current - 1]
        if not line.strip() or current in heading_lines or current in doc.fenced:
            break
        if current != start and (LIST_ITEM.match(line) or _is_table_start(doc, current)):
            break
        current += 1
    doc.paragraphs.append(Paragraph(start, current - 1))
    return current
