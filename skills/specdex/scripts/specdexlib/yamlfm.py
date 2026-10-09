"""Minimal YAML reader for Markdown frontmatter.

Supports what BMAD frontmatter uses: nested block mappings, block lists of
scalars, inline lists, and single- or double-quoted scalars. Each key keeps its
line number so tokens and fields can be cited. Anything else is reported as a
problem instead of being guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

KEY = re.compile(r"^(?P<indent> *)(?P<key>'[^']*'|\"[^\"]*\"|[^\s:#'\"][^:#]*?)\s*:(?:\s+(?P<value>.*?))?\s*$")
ITEM = re.compile(r"^(?P<indent> *)-\s+(?P<value>.*?)\s*$")


@dataclass(slots=True)
class Entry:
    path: str          # dotted key path, e.g. "colors.primary"
    line: int          # 1-based line in the source document
    end: int           # last line of the entry's block (children included)
    value: object      # str, list[str], or None for a mapping


@dataclass(slots=True)
class Frontmatter:
    entries: list[Entry] = field(default_factory=list)
    problems: list[tuple[int, str]] = field(default_factory=list)

    def get(self, path: str):
        for entry in self.entries:
            if entry.path == path:
                return entry.value
        return None


def strip_comment(text: str) -> str:
    """Drop a trailing ` # comment` that sits outside quotes (BMAD templates annotate values this way)."""
    quote = ""
    for index, char in enumerate(text):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    return text


def malformed(text: str) -> str | None:
    """Why a value cannot be read faithfully, or None."""
    if text.startswith("[") and not text.endswith("]"):
        return "unclosed inline list"
    if text[:1] in "'\"" and (len(text) < 2 or text[-1] != text[0]):
        return "unclosed quote"
    if text.startswith("{"):
        return "inline mapping (unsupported)"
    return None


def unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def inline_list(text: str) -> list[str] | None:
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    body = text[1:-1].strip()
    if not body:
        return []
    items, current, quote = [], [], ""
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == ",":
            items.append(unquote("".join(current)))
            current = []
        else:
            current.append(char)
    items.append(unquote("".join(current)))
    return items


def parse(lines: list[str], first_line: int) -> Frontmatter:
    """Parse frontmatter body lines; first_line is the document line of lines[0]."""
    result = Frontmatter()
    stack: list[tuple[int, Entry]] = []  # (indent, entry) of open mappings/lists
    for offset, raw in enumerate(lines):
        number = first_line + offset
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        while stack and indent <= stack[-1][0] and not (ITEM.match(raw) and indent == stack[-1][0] and isinstance(stack[-1][1].value, list)):
            stack.pop()
        item = ITEM.match(raw)
        if item and stack and isinstance(stack[-1][1].value, list):
            owner = stack[-1][1]
            owner.value.append(unquote(strip_comment(item.group("value"))))
            _close(stack, number)
            continue
        key = KEY.match(raw)
        if not key:
            result.problems.append((number, f"unsupported frontmatter line: {raw.strip()[:60]}"))
            continue
        name = unquote(key.group("key"))
        parent_path = stack[-1][1].path if stack else ""
        path = f"{parent_path}.{name}" if parent_path else name
        value_text = strip_comment(key.group("value") or "")
        if value_text == "":
            entry = Entry(path, number, number, None)
            result.entries.append(entry)
            _close(stack, number)
            entry.value = [] if _next_is_item(lines, offset, indent) else None
            stack.append((indent, entry))
            continue
        problem = malformed(value_text)
        if problem:
            result.problems.append((number, f"{problem} in {path}: {value_text[:60]}"))
        parsed = inline_list(value_text)
        entry = Entry(path, number, number, parsed if parsed is not None else unquote(value_text))
        result.entries.append(entry)
        _close(stack, number)
    return result


def _next_is_item(lines: list[str], offset: int, indent: int) -> bool:
    for raw in lines[offset + 1:]:
        if not raw.strip():
            continue
        match = ITEM.match(raw)
        return bool(match) and len(match.group("indent")) >= indent
    return False


def _close(stack: list[tuple[int, Entry]], number: int) -> None:
    """Extend every open ancestor's block to include this line."""
    for _, entry in stack:
        entry.end = max(entry.end, number)
