"""Per-file extraction: units, ID occurrences, definition candidates and flags.

Everything here depends only on one file's bytes, its path and the config, so
a changed file can be re-extracted alone. Decisions that need the whole corpus
(which owner is current, how a citation resolves) happen in resolve.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import markdown, yamlfm
from .config import Config

CHUNK_MAX_LINES = 40
ROW_CHUNK_MIN = 3
SHORT_END = re.compile(r"(\d+)(?![\w-]|\.\d)")  # a sentence-final period still ends the range
BOLD_LEAD = re.compile(r"^\*\*(?P<inner>(?:[^*]|\*(?!\*))+?)\*\*")  # single-star italics may sit inside the bold
BACKTICK_WORD = re.compile(r"`([a-z][a-z0-9-]*[a-z0-9])`")
TOKEN_REF = re.compile(r"\{([a-z][\w-]*(?:\.[\w-]+)+)\}")
ID_TAIL = re.compile(r"^(?:$|[\s:.,;—–(*])")
PROSE_AFTER_ID = re.compile(r"^\s+[a-z]")  # "**FR-2 is verified by …**" may be a sentence citing FR-2
REFINABLE_KINDS = ("owner", "ticket", "other")  # "other": no path rule matched
PARENTHETICAL = re.compile(r"\([^)]*\)")
TEXTUAL_SCOPE = re.compile(r"\ball\b[^,;.]*", re.I)  # "all MVP FRs and NFRs": a binding by phrase, not by ID
CAMEL_CASE = re.compile(r"\b[A-Za-z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
CAMEL_PART = re.compile(r"[A-Z]?[a-z0-9]+")


@dataclass(slots=True)
class SpanFact:
    kind: str                  # file | frontmatter | yaml | section | row | item | para
    start: int
    end: int
    level: int = 0
    title: str = ""
    hpath: str = ""
    temporal: str = "current"  # current | historical
    flags: tuple[str, ...] = ()
    disposition: str | None = None


@dataclass(slots=True)
class Occurrence:
    line: int
    col: int
    family: str
    id: str
    raw: str
    via_range: bool
    span: int                  # index into spans (innermost unit)
    kind: str = "mentions"     # defines | elaborates | binds | mentions
    src_id: str | None = None
    rule: str | None = None


@dataclass(slots=True)
class Candidate:
    id: str
    family: str
    shape: str
    span: int
    line: int
    parent_id: str | None = None
    ordinal: int | None = None


@dataclass(slots=True)
class Chunk:
    span: int
    start: int
    end: int
    hpath: str
    body: str

    @property
    def terms(self) -> str:
        """CamelCase identifiers as words, so "access tokens" finds AccessToken."""
        return " ".join(" ".join(CAMEL_PART.findall(name)) for name in CAMEL_CASE.findall(self.body))


@dataclass(slots=True)
class FileFacts:
    path: str
    artifact: str
    kind: str
    scope_kind: str
    lines: int
    frontmatter: dict = field(default_factory=dict)
    spans: list[SpanFact] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    occurrences: list[Occurrence] = field(default_factory=list)
    definitions: list[Candidate] = field(default_factory=list)
    elaborations: list[Candidate] = field(default_factory=list)
    positional_counts: dict[str, int] = field(default_factory=dict)
    backtick_words: list[tuple[int, int, str, int]] = field(default_factory=list)  # line, col, word, span
    companions: list[tuple[str, int]] = field(default_factory=list)
    diagnostics: list[tuple[str, str, int, str]] = field(default_factory=list)  # code, severity, line, detail


def classify(config: Config, path: str, frontmatter_type: str | None) -> tuple[str, str, str]:
    """Artifact type, kind and scope kind for a project-relative path."""
    artifact, kind, scope = "unknown", "other", "project"
    for rule in config.artifacts:
        if rule.matches(path):
            artifact, kind, scope = rule.type, rule.kind, rule.scope
            break
    # `type` refines an owner, a ticket or an unmatched file; an archived or working copy keeps its trail kind.
    if frontmatter_type in config.frontmatter_types and kind in REFINABLE_KINDS:
        refined = config.frontmatter_types[frontmatter_type]
        if refined != artifact:
            artifact = refined
            kind = next((r.kind for r in config.artifacts if r.type == refined), "owner")
    return artifact, kind, scope


def extract(config: Config, path: str, text: str) -> FileFacts:
    if path.endswith(".toml"):
        return _extract_toml(config, path, text)
    doc = markdown.parse(text)
    fm = _frontmatter(doc)
    fm_type = fm.get("type") if isinstance(fm.get("type"), str) else None
    artifact, kind, scope = classify(config, path, fm_type)
    facts = FileFacts(path, artifact, kind, scope, len(doc.lines), frontmatter=fm)
    builder = _Builder(config, doc, facts)
    builder.run()
    return facts


def _frontmatter(doc: markdown.Document) -> dict:
    if not doc.frontmatter:
        return {}
    start, end = doc.frontmatter
    parsed = yamlfm.parse(doc.lines[start:end - 1], start + 1)
    values = {e.path: e.value for e in parsed.entries if "." not in e.path}
    values["__entries__"] = parsed.entries
    values["__problems__"] = parsed.problems
    return values


def _extract_toml(config: Config, path: str, text: str) -> FileFacts:
    artifact, kind, scope = classify(config, path, None)
    lines = text.split("\n")
    facts = FileFacts(path, artifact, kind, scope, len(lines))
    facts.spans.append(SpanFact("file", 1, max(1, len(lines)), title=PurePosixPath(path).name, hpath=PurePosixPath(path).name))
    return facts


class _Builder:
    """Builds FileFacts for one Markdown document."""

    def __init__(self, config: Config, doc: markdown.Document, facts: FileFacts) -> None:
        self.config = config
        self.doc = doc
        self.facts = facts
        self.name = PurePosixPath(facts.path).name
        self.section_span: dict[int, int] = {}
        self.item_span: dict[int, int] = {}
        self.row_span: dict[int, int] = {}
        self.yaml_span: dict[str, int] = {}
        self.para_span: dict[int, int] = {}
        self.line_unit: list[int] = []
        self.historical_lines: set[int] = set()

    def run(self) -> None:
        self._diagnose()
        self._build_spans()
        self._mark_history()
        self._mark_flags()
        self._occurrences()
        self._definitions()
        self._elaborations()
        self._positional()
        self._binds()
        self._attribute_sources()
        self._companions()
        self._chunks()

    # -- units ---------------------------------------------------------------
    def _add(self, span: SpanFact) -> int:
        self.facts.spans.append(span)
        return len(self.facts.spans) - 1

    def _hpath(self, section_index: int | None) -> str:
        return " › ".join([self.name] + self.doc.heading_path(section_index))

    def _diagnose(self) -> None:
        if self.doc.unclosed_fence:
            self.facts.diagnostics.append(("parse-gap", "high", self.doc.unclosed_fence, "unclosed code fence; the rest of the file is treated as code"))
        if self.doc.unclosed_frontmatter:
            self.facts.diagnostics.append(("parse-gap", "medium", 1, "frontmatter opened on line 1 is never closed; it is read as body text"))
        for line, problem in self.facts.frontmatter.get("__problems__", []):
            self.facts.diagnostics.append(("parse-gap", "medium", line, problem))
        list_fields = set(self.config.fields.values()) | {self.config.spine.get("frontmatter_binds", "binds")}
        for entry in self.facts.frontmatter.get("__entries__", []):
            if entry.path in list_fields and isinstance(entry.value, str):
                self.facts.diagnostics.append(("parse-gap", "medium", entry.line, f"{entry.path} should be a list; read as one item"))
            elif entry.path == "type" and isinstance(entry.value, list):
                self.facts.diagnostics.append(("parse-gap", "medium", entry.line, "type should be one value; the document type is unknown"))

    def _build_spans(self) -> None:
        doc = self.doc
        total = max(1, len(doc.lines))
        file_index = self._add(SpanFact("file", 1, total, title=self.name, hpath=self.name))
        self.line_unit = [file_index] * (total + 1)
        if doc.frontmatter:
            start, end = doc.frontmatter
            fm_index = self._add(SpanFact("frontmatter", start, end, title="frontmatter", hpath=f"{self.name} › frontmatter"))
            self._paint(start, end, fm_index)
            for entry in self.facts.frontmatter.get("__entries__", []):
                index = self._add(SpanFact("yaml", entry.line, entry.end, title=entry.path, hpath=f"{self.name} › frontmatter › {entry.path}"))
                self.yaml_span[entry.path] = index
                if entry.line == entry.end:
                    self.line_unit[entry.line] = index
        for number, section in enumerate(doc.sections):
            index = self._add(SpanFact("section", section.start, section.end, section.level, section.title, self._hpath(number)))
            self.section_span[number] = index
            self._paint(section.start, section.end, index)
        for paragraph in doc.paragraphs:
            index = self._add(SpanFact("para", paragraph.start, paragraph.end, hpath=self._hpath(doc.section_at(paragraph.start))))
            self.para_span[paragraph.start] = index
            self._paint(paragraph.start, paragraph.end, index)
        for number, item in sorted(enumerate(doc.items), key=lambda pair: pair[1].depth):
            index = self._add(SpanFact("item", item.start, item.end, item.depth, item.first_text[:80], self._hpath(doc.section_at(item.start))))
            self.item_span[number] = index
            self._paint(item.start, item.end, index)
        for number, row in enumerate(doc.rows):
            index = self._add(SpanFact("row", row.line, row.line, title=row.cells[0][:80] if row.cells else "", hpath=self._hpath(doc.section_at(row.line))))
            self.row_span[number] = index
            self.line_unit[row.line] = index

    def _paint(self, start: int, end: int, index: int) -> None:
        for number in range(start, min(end, len(self.line_unit) - 1) + 1):
            self.line_unit[number] = index

    def _sections_titled(self, prefix: str) -> list[int]:
        return [n for n, s in enumerate(self.doc.sections) if s.title.startswith(prefix)]

    def _in_section(self, line: int, prefix: str | None) -> bool:
        if not prefix:
            return True
        return any(self.doc.sections[n].start <= line <= self.doc.sections[n].end for n in self._sections_titled(prefix))

    # -- history and markers -----------------------------------------------------
    def _mark_history(self) -> None:
        rules = [r for r in self.config.historical if r.artifact == self.facts.artifact]
        for rule in rules:
            if rule.section:
                for n in self._sections_titled(rule.section):
                    section = self.doc.sections[n]
                    self.historical_lines.update(range(section.start, section.end + 1))
            if rule.label:
                self._mark_labelled(rule.label)
            if rule.rows:
                self._mark_rows(rule.disposition_column)
        for span in self.facts.spans:
            if span.kind == "file":
                continue
            nonblank = {n for n in range(span.start, span.end + 1) if self.doc.lines[n - 1].strip()}
            history = nonblank & self.historical_lines
            if history:  # a parent section holding a historical subsection is not current as a whole
                span.temporal = "historical" if history == nonblank else "partly historical"

    def _mark_labelled(self, label: str) -> None:
        for paragraph in self.doc.paragraphs:
            if not self.doc.lines[paragraph.start - 1].lstrip().startswith(label):
                continue
            end = paragraph.end
            following = [i for i in self.doc.items if i.depth == 0 and i.start > end]
            for item in sorted(following, key=lambda i: i.start):
                gap = self.doc.lines[end:item.start - 1]
                if any(line.strip() for line in gap):
                    break
                end = item.end
            self.historical_lines.update(range(paragraph.start, end + 1))

    def _mark_rows(self, disposition_column: str | None) -> None:
        for number, row in enumerate(self.doc.rows):
            self.historical_lines.add(row.line)
            if disposition_column and disposition_column in row.header:
                column = row.header.index(disposition_column)
                if column < len(row.cells):
                    self.facts.spans[self.row_span[number]].disposition = row.cells[column]

    def _mark_flags(self) -> None:
        if not self.config.markers:
            return
        for span in self.facts.spans:
            if span.kind in ("file", "frontmatter"):
                continue
            end = span.end
            if span.kind == "section":
                children = [s.start for s in self.doc.sections if span.start < s.start <= span.end]
                end = min(children) - 1 if children else span.end
            text = self.doc.text(span.start, end)
            span.flags = tuple(name for name, regex in self.config.markers if regex.search(text))
        for section in self.doc.sections:  # a marker in a heading qualifies everything under it
            heading = self.doc.lines[section.start - 1]
            inherited = [name for name, regex in self.config.markers if regex.search(heading)]
            for span in self.facts.spans if inherited else ():
                if span.kind not in ("file", "frontmatter") and section.start <= span.start and span.end <= section.end:
                    span.flags = tuple(dict.fromkeys(span.flags + tuple(inherited)))

    # -- occurrences ---------------------------------------------------------------
    def _occurrences(self) -> None:
        config = self.config
        token_roots = self._token_roots()
        for number, line in enumerate(self.doc.lines, start=1):
            if not line:
                continue
            unit = self.line_unit[number]
            matches = list(config.id_regex.finditer(line))
            for match in matches:
                family, base, sub = self._identify(match)
                if family is None:
                    continue
                ident = f"{base}.{sub}" if sub and family in config.positional else base
                self.facts.occurrences.append(Occurrence(number, match.start(), family, ident, match.group(0), False, unit))
            self._expand_ranges(number, line, matches, unit)
            if token_roots:
                for ref in TOKEN_REF.finditer(line):
                    if ref.group(1).split(".")[0] in token_roots:
                        self.facts.occurrences.append(Occurrence(number, ref.start(), "TOKEN", ref.group(1), ref.group(0), False, unit))
            if self.config.token_bare_backtick and self.facts.artifact in ("ux-design", "ux-experience"):
                for word in BACKTICK_WORD.finditer(line):
                    self.facts.backtick_words.append((number, word.start(), word.group(1), unit))

    def _token_roots(self) -> set[str]:
        roots: set[str] = set()
        for rule in self.config.defines:
            if rule.shape == "yaml-tokens":
                roots.update(rule.roots)
        return roots

    def _identify(self, match: re.Match) -> tuple[str | None, str, str | None]:
        for group, family in self.config.family_groups.items():
            if match.group(group):
                return family, match.group(group), match.group("sub")
        return None, "", None

    def _expand_ranges(self, number: int, line: str, matches: list[re.Match], unit: int) -> None:
        config = self.config
        separators = "|".join(re.escape(s) for s in config.range_separators)
        joint = re.compile(rf"\s*(?:{separators})\s*")
        for index, first in enumerate(matches):
            family, base, sub = self._identify(first)
            if family is None:
                continue
            fam = config.families[family]
            gap = joint.match(line, first.end())
            if not gap:
                continue
            second = matches[index + 1] if index + 1 < len(matches) else None
            if second is not None and second.start() == gap.end():
                family2, base2, sub2 = self._identify(second)
                if family2 == family:
                    self._add_members(number, first, fam, base, sub, base2, sub2, unit, line[first.start():second.end()])
                continue
            if config.range_short_form and fam.key == "int" and not sub:
                short = SHORT_END.match(line, gap.end())
                span = int(short.group(1)) - int(_key_of(fam, base)) if short else 0
                if 0 < span < config.range_max:
                    prefix = base[: len(base) - len(_key_of(fam, base))]
                    end_id = f"{prefix}{short.group(1)}"
                    self._add_members(number, first, fam, base, None, end_id, None, unit, line[first.start():short.end()], include_end=True)
                elif span >= config.range_max:
                    self.facts.diagnostics.append(("bad-range", "low", number,
                                                   f"{line[first.start():short.end()]} read as an ID and a number (more than {config.range_max} members)"))

    def _add_members(self, number, first, fam, base, sub, base2, sub2, unit, raw, include_end=False) -> None:
        members = _range_members(fam, base, sub, base2, sub2, self.config)
        if members is None:
            self.facts.diagnostics.append(("bad-range", "medium", number, f"cannot expand range {raw}"))
            return
        if include_end:
            members = members + [base2]
        for member in members:
            self.facts.occurrences.append(Occurrence(number, first.start(), fam.name, member, raw, True, unit))

    # -- definitions -----------------------------------------------------------
    def _definitions(self) -> None:
        sentence_leads: list[Candidate] = []
        for rule in self.config.defines:
            if rule.artifact != self.facts.artifact:
                continue
            if rule.shape == "heading":
                self._define_headings(rule.family, rule.section, self.facts.definitions)
            elif rule.shape == "item-lead":
                self._define_item_leads(rule.family, rule.section, sentence_leads)
            elif rule.shape == "row-key":
                self._define_row_keys(rule.family, rule.section, self.facts.definitions)
            elif rule.shape == "yaml-tokens":
                self._define_tokens(rule.roots)
            elif rule.shape == "item-lead-term":
                self._define_terms(rule.section)
        # A lead reading as a sentence ("**FR-2 is verified by …**") cites an ID this file defines elsewhere;
        # alone, it is the definition ("**SM-1 weekly active readers**").
        defined = {c.id for c in self.facts.definitions}
        self.facts.definitions += [c for c in sentence_leads if c.id not in defined]
        self._mark_defining_occurrences(self.facts.definitions, "defines")

    def _leading_ids(self, text: str, family: str) -> list[str]:
        """IDs of the family at the very start of text (a bold wrapper allowed)."""
        stripped = text.strip().lstrip("*").strip()
        match = self.config.id_regex.match(stripped)
        if not match:
            return []
        fam, base, sub = self._identify(match)
        if fam != family or not ID_TAIL.match(stripped[match.end():]):
            return []
        return [base if not sub else f"{base}.{sub}"]

    def _reads_as_sentence(self, text: str) -> bool:
        """The leading ID is followed by lowercase words ("FR-2 is verified …")."""
        stripped = text.strip().lstrip("*").strip()
        match = self.config.id_regex.match(stripped)
        return bool(match and PROSE_AFTER_ID.match(stripped[match.end():]))

    def _define_headings(self, family: str, section: str | None, out: list[Candidate]) -> None:
        for number, sect in enumerate(self.doc.sections):
            if section and not self._in_section(sect.start, section):
                continue
            for ident in self._leading_ids(sect.title, family):
                out.append(Candidate(ident, family, "heading", self.section_span[number], sect.start))

    def _define_item_leads(self, family: str, section: str | None, sentence_leads: list[Candidate]) -> None:
        for number, item in enumerate(self.doc.items):
            if section and not self._in_section(item.start, section):
                continue
            lead = BOLD_LEAD.match(item.first_text.strip())
            if not lead:
                continue
            found = sentence_leads if self._reads_as_sentence(lead.group("inner")) else self.facts.definitions
            for ident in self._leading_ids(lead.group("inner"), family):
                found.append(Candidate(ident, family, "item-lead", self.item_span[number], item.start))

    def _first_cell_ids(self, row: markdown.Row) -> list[tuple[str, str]]:
        """IDs keying a row: a first cell made only of IDs (a trailing parenthetical allowed)."""
        if not row.cells:
            return []
        cell = PARENTHETICAL.sub("", row.cells[0].replace("**", "").replace("`", ""))
        pairs = [self._identify(m) for m in self.config.id_regex.finditer(cell)]
        if not pairs or self.config.id_regex.sub("", cell).strip(" ,;&") not in ("", "and"):
            return []
        return [(fam, base if not sub else f"{base}.{sub}") for fam, base, sub in pairs if fam]

    def _define_row_keys(self, family: str, section: str | None, out: list[Candidate]) -> None:
        for number, row in enumerate(self.doc.rows):
            if section and not self._in_section(row.line, section):
                continue
            cell = row.cells[0].replace("**", "").replace("`", "").strip() if row.cells else ""
            match = self.config.id_regex.fullmatch(cell)
            if not match:
                continue
            fam, base, sub = self._identify(match)
            if fam == family:
                out.append(Candidate(base, family, "row-key", self.row_span[number], row.line))

    def _define_tokens(self, roots: tuple[str, ...]) -> None:
        for entry in self.facts.frontmatter.get("__entries__", []):
            if entry.path.split(".")[0] in roots and "." in entry.path:
                self.facts.definitions.append(Candidate(entry.path, "TOKEN", "yaml", self.yaml_span[entry.path], entry.line))

    def _define_terms(self, section: str | None) -> None:
        for number, item in enumerate(self.doc.items):
            if item.depth != 0 or (section and not self._in_section(item.start, section)):
                continue
            lead = BOLD_LEAD.match(item.first_text.strip())
            if lead:
                self.facts.definitions.append(Candidate(lead.group("inner").strip(), "TERM", "item-lead", self.item_span[number], item.start))

    def _mark_defining_occurrences(self, candidates: list[Candidate], kind: str) -> None:
        keyed = {(c.line, c.id) for c in candidates}
        for occurrence in self.facts.occurrences:
            if (occurrence.line, occurrence.id) in keyed and not occurrence.via_range:
                occurrence.kind = kind

    # -- elaborations ------------------------------------------------------------
    def _elaborations(self) -> None:
        for rule in self.config.elaborations:
            if rule.artifact != self.facts.artifact:
                continue
            sections = self._sections_titled(rule.section)
            ranges = [(self.doc.sections[n].start, self.doc.sections[n].end) for n in sections]

            def inside(line: int) -> bool:
                return any(a <= line <= b for a, b in ranges)

            if rule.shape == "heading":
                for number, sect in enumerate(self.doc.sections):
                    if number in sections or not inside(sect.start):
                        continue
                    for family in rule.families:
                        for ident in self._leading_ids(sect.title, family):
                            self.facts.elaborations.append(Candidate(ident, family, "heading", self.section_span[number], sect.start))
            else:
                for number, row in enumerate(self.doc.rows):
                    if not inside(row.line):
                        continue
                    if rule.shape == "row-key":
                        pairs = self._first_cell_ids(row)
                    else:
                        pairs = [(o.family, o.id) for o in self.facts.occurrences if o.line == row.line]
                    for family, ident in pairs:
                        if family in rule.families:
                            self.facts.elaborations.append(Candidate(ident, family, rule.shape, self.row_span[number], row.line))
        self._mark_defining_occurrences(self.facts.elaborations, "elaborates")

    # -- positional ------------------------------------------------------------------
    def _positional(self) -> None:
        for candidate in list(self.facts.definitions):
            rule = self.config.positional.get(candidate.family)
            if not rule or candidate.shape != "heading":
                continue
            section = self.facts.spans[candidate.span]
            items = self._positional_items(rule, section.start, section.end)
            self.facts.positional_counts[candidate.id] = len(items)
            for ordinal, item_number in enumerate(items, start=1):
                item = self.doc.items[item_number]
                self.facts.definitions.append(Candidate(f"{candidate.id}.{ordinal}", candidate.family, "positional",
                                                        self.item_span[item_number], item.start, candidate.id, ordinal))

    def _positional_items(self, rule, start: int, end: int) -> list[int]:
        begin = start
        if rule.container == "after-marker":
            marker_line = next((n for n in range(start, end + 1) if self.doc.lines[n - 1].strip().startswith(rule.marker)), None)
            if marker_line is None:
                return []
            begin = marker_line
        tops = sorted((n for n, i in enumerate(self.doc.items) if i.depth == 0 and begin < i.start <= end), key=lambda n: self.doc.items[n].start)
        if not tops:
            return []
        first = self.doc.items[tops[0]].start
        stops = [p.start for p in self.doc.paragraphs if first < p.start <= end]
        stops += [r.line for r in self.doc.rows if first < r.line <= end and not any(self.doc.items[n].start <= r.line <= self.doc.items[n].end for n in tops)]
        stop = min(stops) if stops else end + 1
        return [n for n in tops if self.doc.items[n].start < stop]

    # -- binds ---------------------------------------------------------------------------
    def _binds(self) -> None:
        if self.facts.artifact != "architecture-spine":
            return
        marker = self.config.spine.get("binds_marker", "**Binds:**")
        ad_sections = {c.span: c.id for c in self.facts.definitions if c.shape == "heading"}
        bind_lines: dict[int, str | None] = {}
        for span_index, ident in ad_sections.items():
            span = self.facts.spans[span_index]
            for number, item in enumerate(self.doc.items):
                if span.start <= item.start <= span.end and item.first_text.strip().startswith(marker):
                    for line in range(item.start, item.end + 1):
                        bind_lines[line] = ident
                    phrase = TEXTUAL_SCOPE.search(item.first_text)
                    if phrase:
                        self.facts.occurrences.append(Occurrence(item.start, phrase.start(), "SCOPE", "*", phrase.group(0), False,
                                                                 self.item_span[number], "binds", ident, "binds-textual"))
        field_name = self.config.spine.get("frontmatter_binds", "binds")
        for entry in self.facts.frontmatter.get("__entries__", []):
            if entry.path == field_name:
                for line in range(entry.line, entry.end + 1):
                    bind_lines[line] = None
        inherited = self.config.spine.get("inherited_section")
        inherited_lines = {r.line for r in self.doc.rows if inherited and self._in_section(r.line, inherited)}
        for occurrence in self.facts.occurrences:
            if occurrence.line in bind_lines and occurrence.kind == "mentions":
                occurrence.kind = "binds"
                occurrence.src_id = bind_lines[occurrence.line]
                occurrence.rule = "binds-field" if bind_lines[occurrence.line] is None else "binds-marker"
            elif occurrence.line in inherited_lines and occurrence.family == "AD":
                occurrence.rule = "inherited"

    # -- attribution ----------------------------------------------------------------------
    def _attribute_sources(self) -> None:
        """Attach each occurrence to the innermost defined or elaborated unit that contains it."""
        units = sorted(((self.facts.spans[c.span].start, self.facts.spans[c.span].end, c.id)
                        for c in self.facts.definitions + self.facts.elaborations if c.shape != "positional"),
                       key=lambda u: u[1] - u[0])
        for occurrence in self.facts.occurrences:
            if occurrence.src_id is not None:
                continue
            for start, end, ident in units:
                if start <= occurrence.line <= end and ident != occurrence.id:
                    occurrence.src_id = ident
                    break

    def _companions(self) -> None:
        field_name = self.config.fields.get("companions", "companions")
        for entry in self.facts.frontmatter.get("__entries__", []):
            if entry.path == field_name and isinstance(entry.value, (list, str)):
                for value in [entry.value] if isinstance(entry.value, str) else entry.value:
                    self.facts.companions.append((value, entry.line))

    # -- search chunks ------------------------------------------------------------------
    def _chunks(self) -> None:
        doc = self.doc
        body_start = doc.frontmatter[1] + 1 if doc.frontmatter else 1
        first_heading = doc.sections[0].start if doc.sections else len(doc.lines) + 1
        if first_heading > body_start:
            self._chunk_range(0, body_start, first_heading - 1, self.name)
        for number, section in enumerate(doc.sections):
            children = [s.start for s in doc.sections if section.start < s.start <= section.end]
            own_end = (min(children) - 1) if children else section.end
            self._chunk_range(self.section_span[number], section.start, own_end, self.facts.spans[self.section_span[number]].hpath)
        for entry in self.facts.frontmatter.get("__entries__", []):
            if entry.path.count(".") <= 1 and (entry.value is not None or "." in entry.path):
                self.facts.chunks.append(Chunk(self.yaml_span[entry.path], entry.line, entry.end, f"{self.name} › frontmatter › {entry.path}", doc.text(entry.line, entry.end)))

    def _chunk_range(self, span: int, start: int, end: int, hpath: str) -> None:
        nonblank = [n for n in range(start, end + 1) if self.doc.lines[n - 1].strip()]
        if not nonblank:
            return
        if len(nonblank) <= CHUNK_MAX_LINES:
            self.facts.chunks.append(Chunk(span, start, end, hpath, self.doc.text(start, end)))
            rows = [(n, r) for n, r in enumerate(self.doc.rows) if start < r.line <= end]
            if len(rows) >= ROW_CHUNK_MIN:  # rows are the smallest answering unit of a table
                for number, row in rows:
                    self.facts.chunks.append(Chunk(self.row_span[number], row.line, row.line, hpath, f"{' | '.join(row.header)}\n{self.doc.lines[row.line - 1]}"))
            return
        self.facts.chunks.append(Chunk(span, start, start, hpath, self.doc.lines[start - 1]))
        covered: set[int] = {start}
        for number, item in enumerate(self.doc.items):
            if item.depth == 0 and start < item.start <= end:
                self.facts.chunks.append(Chunk(self.item_span[number], item.start, item.end, hpath, self.doc.text(item.start, item.end)))
                covered.update(range(item.start, item.end + 1))
        for number, row in enumerate(self.doc.rows):
            if start < row.line <= end and row.line not in covered:
                header = " | ".join(row.header)
                self.facts.chunks.append(Chunk(self.row_span[number], row.line, row.line, hpath, f"{header}\n{self.doc.lines[row.line - 1]}"))
                covered.add(row.line)
        for paragraph in self.doc.paragraphs:
            if start < paragraph.start <= end and paragraph.start not in covered:
                self.facts.chunks.append(Chunk(self.para_span[paragraph.start], paragraph.start, paragraph.end, hpath, self.doc.text(paragraph.start, paragraph.end)))


def _key_of(family, ident: str) -> str:
    match = re.fullmatch(family.pattern, ident)
    return match.group("key") if match else ""


def _range_members(family, base, sub, base2, sub2, config: Config) -> list[str] | None:
    """IDs strictly between two range ends (the ends are explicit occurrences)."""
    key_a, key_b = _key_of(family, base), _key_of(family, base2)
    if not key_a or not key_b:
        return None
    if sub or sub2:
        if base != base2 or not (sub and sub2) or int(sub2) < int(sub) or int(sub2) - int(sub) + 1 > config.range_max:
            return None
        return [f"{base}.{k}" for k in range(int(sub) + 1, int(sub2))]
    prefix = base[: len(base) - len(key_a)]
    if family.key == "int":
        a, b = int(key_a), int(key_b)
        if b < a or b - a + 1 > config.range_max:
            return None
        return [f"{prefix}{k}" for k in range(a + 1, b)]
    if family.key == "alpha" and len(key_a) == 1 and len(key_b) == 1 and key_a <= key_b and ord(key_b) - ord(key_a) + 1 <= config.range_max:
        return [f"{prefix}{chr(c)}" for c in range(ord(key_a) + 1, ord(key_b))]
    return None
