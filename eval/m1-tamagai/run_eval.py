#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["tiktoken>=0.7"]
# ///
"""M1 Layer A: specdex (Stage A, Stage B) versus baselines B0 and B1 on the gold tasks.

Every condition is a mechanical agent with a frozen policy (docs/m1-plan.md):
  1. an initial step from the prompt alone (IDs, quoted names, document §refs, words);
  2. up to MAX_STEPS continuation steps: follow a pointer it has already seen to the next
     missing gold unit (a line, a section, an ID), or else take its next discovery step.
     A step that shows nothing new (no new line, no new pointer) ends the task.

Shared oracle-assisted continuation: the continuation is oracle-assisted for every condition. The
missing gold unit decides which seen pointer is followed, where that read starts and when a task stops.
The definition and boundary lookups come from the engine under test for all conditions: where an ID is
defined (Corpus.definition) and where sections start and end (Corpus.sections: B1's outlines and section
reads, Stage A's section read after a grep). The baselines get these lookups for free, so the shared
oracle can only help them. Otherwise the policy is identical across conditions; only the tools differ.
The agent replay checks the policies against real agents.

Scoring (docs/m1-plan.md): every span a condition shows is recorded in order: a read or get unit, and
each grep or refs line. Search hits and outline entries are pointers until a read shows them. A span
contains a gold unit when it has the same path and its line range contains the unit's range (blank
edge lines of a unit carry no evidence and are ignored). Containment is per span, never a union of
lines. Contained recall uses every shown span; top-5 recall uses the first five distinct ones.
`workflow_recall` (secondary) is the share of units whose non-blank lines the union of everything
shown covers. Authority errors need the engine's labels: baselines show unlabelled text, so the proxy
cannot judge their authority use (the replay judgements do).
Usage: uv run run_eval.py [--split dev|heldout|all]
"""
from __future__ import annotations

import argparse
from abc import ABC, abstractmethod
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import tiktoken

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = HERE.parent / "corpora" / "tamagai-2026-10-04"
OVERLAY = HERE / "overlay.toml"
ENGINE = ROOT / "skills" / "specdex" / "scripts" / "specdex.py"
DB = HERE / "results" / ".eval-index.sqlite"
ENCODING = tiktoken.get_encoding("o200k_base")
MAX_STEPS = 5
TOP_K = 5
REFS_PAGE = 60  # the engine's first text page of `refs` (its --size default); nothing beyond it is shown

# Observed median requested range per document (extract-corpus §B6); default for others.
OBSERVED_RANGE = {"prd.md": 77, "EXPERIENCE.md": 145, "ARCHITECTURE-SPINE.md": 51, "addendum.md": 29, "DESIGN.md": 38}
DEFAULT_RANGE = 60
GREP_HEAD = 40
ID_PATTERN = re.compile(r"(?<![\w-])(?:SM-C\d+|(?:NFR|FR|UJ|SM|AD|CAP|CR|OQ|CQ|ACR|UX|A)-(?:\d+|[A-Z]))(?:\.\d+)?(?![\w-])")
SECTION_REF = re.compile(r"\b(PRD addendum|brief addendum|addendum|PRD|spine|EXPERIENCE|DESIGN|OVERVIEW)\s*§\s*(\d+(?:\.\d+)*)", re.I)
QUOTED = re.compile(r"[\"“'‘`]([^\"”'’`]{2,60})[\"”'’`]")
HYPHENATED = re.compile(r"\b[a-z]+(?:-[a-z]+)+\b")
CITATION_INTENT = re.compile(r"\b(every|all (?:the )?(?:places|lines|citations|rows)|list every|where is .* (?:cited|used)|which ads? bind|cites?|citations?)\b", re.I)
BIND_INTENT = re.compile(r"\bbinds?\b|\bbinding", re.I)
EXCLUSION_INTENT = re.compile(r"\b(?:not counting|apart from|except|excluding|other than)\b", re.I)
BINDS_LINE = re.compile(r"\bbinds\b", re.I)
STOPWORDS = set("""a an and are as at be by can do does for from has have how i if in is it its me my of on or our so than that the their them then there
these they this to under up was we were what when where which while who why will with would you your about after all also any because before both
each more most no not now only other out same some such too very just show tell give find list say pull see look does doesn't isn't what's spec specs
section pip""".split())
MANIFEST = """Specs of record (Tamagai): PRD prd.md (FR/NFR headings, UJ list §2.3, glossary §3, CR §7, SM §13, OQ §15, CQ §15.1); PRD addendum.md;
DESIGN.md (tokens in frontmatter); EXPERIENCE.md; ARCHITECTURE-SPINE.md (AD headings, A-n rows); ARCHITECTURE-OVERVIEW.md; CHANGE-REQUESTS.md (ACR/UX rows);
brief.md and brief addendum.md (superseded by the PRD except economics, brief addendum §1.2). Everything else is supporting or trail."""
OWNER_FILE = {"FR": "prd.md", "NFR": "prd.md", "UJ": "prd.md", "SM": "prd.md", "CR": "prd.md", "OQ": "prd.md", "CQ": "prd.md",
              "AD": "ARCHITECTURE-SPINE.md", "A": "ARCHITECTURE-SPINE.md", "ACR": "CHANGE-REQUESTS.md", "UX": "CHANGE-REQUESTS.md"}
DOC_FILES = {"prd addendum": "prds/prd-tamagai-2026-09-29/addendum.md", "addendum": "prds/prd-tamagai-2026-09-29/addendum.md",
             "brief addendum": "briefs/brief-tamagai-2026-09-29/addendum.md", "prd": "prd.md", "spine": "ARCHITECTURE-SPINE.md",
             "experience": "EXPERIENCE.md", "design": "DESIGN.md", "overview": "ARCHITECTURE-OVERVIEW.md"}
POINTER = re.compile(r"(?P<path>[\w./-]+\.md):(?P<a>\d+)(?:-(?P<b>\d+))?")

# Authority (GOLD-SPEC "Historical text inside record files"; the overlay's [[historical]] and [[superseded]] rules).
HISTORICAL_SECTIONS = {"addendum.md": ("1.9 Declined proposals", "6. What this PRD changes", "Appendix A"),
                       "EXPERIENCE.md": ("PRD change requests", "Architecture change requests")}
HISTORICAL_LABELS = {"prd.md": "**Retired claims", "EXPERIENCE.md": "**Retired claims"}  # PRD §9 and EXPERIENCE lists
REQUEST_ROWS_FILE = "CHANGE-REQUESTS.md"  # each row's request text is historical; only its Decision cell is current
BRIEF_AUTHORITY = ("briefs/brief-tamagai-2026-09-29/addendum.md", "1.2 Economics")  # PRD §0: the brief stays authority only here

# Gates (docs/m1-plan.md, "Smallest worthwhile benefit").
LOOKUP = ("section", "exact")
STAGE_B_CATEGORY = "paraphrase"  # GOLD-SPEC has no separate "wording" category
STAGE_A_REDUCTION = 0.30
STAGE_B_GAIN_PP = 10
BASELINES = ("B0", "B1")
NOT_MEASURABLE = "not measurable by proxy; see replay judgements"
CONTINUATION = ("shared oracle-assisted continuation: gold units choose the pointer to follow and when to stop; "
                "ID definitions and section boundaries come from the engine for every condition")

Span = tuple[str, int, int]


def tokens(text: str) -> int:
    return len(ENCODING.encode_ordinary(text))


def specdex(*args: str) -> tuple[str, int, float]:
    started = time.perf_counter()
    done = subprocess.run([sys.executable, str(ENGINE), "--project", str(CORPUS), "--overlay", str(OVERLAY), "--db", str(DB), *args],
                          capture_output=True, text=True)
    text = done.stdout if done.returncode in (0, 1) else done.stdout + done.stderr
    return text, done.returncode, time.perf_counter() - started


@dataclass
class Run:
    condition: str
    outputs: list[str] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)             # every span whose text was shown, in order
    shown: dict[str, set[int]] = field(default_factory=dict)    # union of the shown lines
    pointers: list[Span] = field(default_factory=list)          # seen, maybe unread; removed once followed
    seen_pointers: set[Span] = field(default_factory=set)
    search_hits: list[Span] = field(default_factory=list)
    cited: set[tuple[str, int]] | None = None
    labelled: list[dict] = field(default_factory=list)
    seconds: list[float] = field(default_factory=list)
    initial_tokens: int = 0

    def show(self, path: str, start: int, end: int) -> None:
        self.spans.append((path, start, end))
        self.shown.setdefault(path, set()).update(range(start, end + 1))

    def point(self, path: str, start: int, end: int) -> None:
        self.pointers.append((path, start, end))
        self.seen_pointers.add((path, start, end))

    def progress(self) -> tuple[int, int]:
        """What the run has seen so far: distinct lines shown and distinct pointers seen."""
        return sum(len(lines) for lines in self.shown.values()), len(self.seen_pointers)

    @property
    def tokens(self) -> int:
        return sum(tokens(o) for o in self.outputs)


class Corpus:
    def __init__(self) -> None:
        outline = json.loads(specdex("--json", "outline")[0])
        self.records = [f["path"] for f in outline]
        self.sections = {f["path"]: f["sections"] for f in outline}
        self.all_files = sorted(p.relative_to(CORPUS).as_posix() for p in (CORPUS / "_bmad-output").rglob("*.md"))
        self._lines: dict[str, list[str]] = {}
        self._definitions: dict[str, tuple[str, int, int] | None] = {}

    def lines(self, path: str) -> list[str]:
        if path not in self._lines:
            self._lines[path] = (CORPUS / path).read_text(errors="replace").split("\n")
        return self._lines[path]

    def record(self, name: str) -> str:
        return next(p for p in self.records if p.endswith("/" + name) or p.endswith(name))

    def full_path(self, fragment: str) -> str | None:
        matches = [p for p in self.all_files if p == fragment or p.endswith("/" + fragment)]
        return matches[0] if len(matches) == 1 else None

    def enclosing_section(self, path: str, line: int) -> tuple[int, int, str]:
        best = (line, line, "")
        for s in self.sections.get(path, []):
            if s["start"] <= line <= s["end"] and (best[2] == "" or s["start"] >= best[0]):
                best = (s["start"], s["end"], s["title"])
        return best

    def section_lines(self, path: str, prefixes: tuple[str, ...]) -> set[int]:
        return {n for s in self.sections.get(path, []) if s["title"].startswith(prefixes) for n in range(s["start"], s["end"] + 1)}

    def definition(self, ident: str) -> tuple[str, int, int] | None:
        """Where an ID is defined: the engine's answer, shared by every condition (the oracle, see the module docstring)."""
        if ident not in self._definitions:
            try:
                data = json.loads(specdex("--json", "resolve", ident)[0])
            except json.JSONDecodeError:
                data = {}
            found = data.get("definitions") or []
            self._definitions[ident] = (found[0]["path"], found[0]["start"], found[0]["end"]) if found else None
        return self._definitions[ident]


def grep(pattern: str, paths: list[str], ignore_case: bool = False, head: int | None = None,
         then: re.Pattern | None = None) -> tuple[str, list[tuple[str, int]]]:
    """Mimics `rg -n --no-heading PATTERN paths [| rg THEN] | head`."""
    regex = re.compile(pattern, re.I if ignore_case else 0)
    out, hits = [], []
    for path in paths:
        for number, line in enumerate((CORPUS / path).read_text(errors="replace").split("\n"), start=1):
            if regex.search(line) and (then is None or then.search(line)):
                hits.append((path, number))
                out.append(f"{path}:{number}:{line}")
    if head is not None:
        out, hits = out[:head], hits[:head]
    return "\n".join(out), hits


def id_pattern(key: str) -> str:
    return r"(?<![\w-])" + re.escape(key) + r"(?![\w-]|\.\d)"


def keys_of(prompt: str) -> list[str]:
    keys = [f"{doc} §{num}" for doc, num in SECTION_REF.findall(prompt)]
    keys += list(dict.fromkeys(ID_PATTERN.findall(prompt)))
    keys += [q for q in QUOTED.findall(prompt) if not ID_PATTERN.fullmatch(q) and len(q.split()) <= 4]
    keys += [h for h in HYPHENATED.findall(prompt) if h not in keys]
    return list(dict.fromkeys(keys))[:3]


def keywords(prompt: str) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z']+", ID_PATTERN.sub(" ", prompt))]
    return list(dict.fromkeys(w for w in words if w not in STOPWORDS and len(w) > 2))[:8]


def named_document(prompt: str, corpus: Corpus) -> str | None:
    for word, name in DOC_FILES.items():
        if re.search(rf"\b{re.escape(word)}\b", prompt, re.I):
            return corpus.record(name)
    return None


def ids_in(text: str) -> list[str]:
    return list(dict.fromkeys(ID_PATTERN.findall(text)))


def citation_target(keys: list[str]) -> str:
    return next((k for k in keys if ID_PATTERN.fullmatch(k)), keys[0])


def observed_range(path: str) -> int:
    return OBSERVED_RANGE.get(path.rsplit("/", 1)[-1], DEFAULT_RANGE)


# -- agents ---------------------------------------------------------------------------------------
class Agent(ABC):
    name = "agent"
    labels_authority = False  # whether the condition's output labels authority (role, temporal status)

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus

    def answer(self, task: dict) -> Run:
        run = Run(self.name)
        self.reset()
        self.initial(task, run)
        run.initial_tokens = run.tokens
        for _ in range(MAX_STEPS):
            missing = [u for u in task["evidence"] if not covered(u, run.shown, self.corpus)]
            if not missing:
                break
            seen = run.progress()
            if not self.follow(run, missing[0]) and not self.discover(task, run):
                break
            if run.progress() == seen:  # progress guard: a step that shows nothing new ends the task
                break
        return run

    def follow(self, run: Run, unit: dict) -> bool:
        """Read a missing unit if a pointer to it was already seen (a line, a section or an ID)."""
        for pointer in list(run.pointers):
            path, start, end = pointer
            if path == unit["path"] and start <= unit["end"] and unit["start"] <= end:
                run.pointers.remove(pointer)
                if self.read_at(run, path, unit["start"] if start <= unit["start"] <= end else start):
                    return True
        for ident in ids_in("\n".join(run.outputs)):
            where = self.corpus.definition(ident)
            if where and where[0] == unit["path"] and where[1] <= unit["end"] and unit["start"] <= where[2] and not covered(
                    {"path": where[0], "start": where[1], "end": where[2]}, run.shown, self.corpus) and self.read_id(run, ident):
                return True
        return False

    def reset(self) -> None:
        """Per-task state."""

    @abstractmethod
    def initial(self, task: dict, run: Run) -> None:
        ...

    @abstractmethod
    def read_at(self, run: Run, path: str, line: int) -> bool:
        """Read around a line; False when nothing was done."""

    @abstractmethod
    def read_id(self, run: Run, ident: str) -> bool:
        """Read an ID's definition; False when nothing was done."""

    @abstractmethod
    def discover(self, task: dict, run: Run) -> bool:
        ...

    def add_output(self, run: Run, text: str) -> None:
        run.outputs.append(text)
        for match in POINTER.finditer(text):
            path = self.corpus.full_path(match.group("path"))
            if path:
                a = int(match.group("a"))
                run.point(path, a, int(match.group("b") or a))

    def show_grep(self, run: Run, text: str, hits: list[tuple[str, int]]) -> None:
        """rg output: every hit line is shown in full."""
        self.add_output(run, text)
        for path, line in hits:
            run.show(path, line, line)

    def sed(self, run: Run, path: str, start: int, end: int) -> None:
        lines = self.corpus.lines(path)
        start, end = max(1, start), min(end, len(lines))
        run.outputs.append("\n".join(f"{n}\t{lines[n - 1]}" for n in range(start, end + 1)))
        run.show(path, start, end)

    def citations(self, run: Run, prompt: str, ident: str) -> None:
        """Baselines answer exhaustive citation requests with an ID grep over the record files.

        The prompt's own restrictions apply as an agent applies them to rg output: a Binds request pipes the
        hits through `rg -i binds`, and an exclusion ("not counting its own heading", "apart from where it's
        defined") leaves the target's definition line out of the answer. rg cannot expand ranges (FR-3–FR-9
        never matches FR-7); that is a documented limitation of the baselines and is not compensated.
        """
        text, hits = grep(id_pattern(ident), self.corpus.records, then=BINDS_LINE if BIND_INTENT.search(prompt) else None)
        self.show_grep(run, text, hits)
        own = definition_line(self.corpus, hits, ident) if EXCLUSION_INTENT.search(prompt) else None
        run.cited = set(hits) - {own}


class Specdex(Agent):
    labels_authority = True

    def __init__(self, corpus: Corpus, stage: str) -> None:
        super().__init__(corpus)
        self.stage = stage
        self.name = f"specdex-{stage}"

    def reset(self) -> None:
        self.outlined = False

    def call(self, run: Run, *args: str) -> dict:
        text, _code, seconds = specdex(*args)
        self.add_output(run, text)
        run.seconds.append(seconds)
        try:  # the same call's JSON twin is uncharged instrumentation: it may credit only what the text shows
            data = json.loads(specdex("--json", *args)[0])
        except json.JSONDecodeError:
            return {}
        if isinstance(data, list):  # outline
            data = {"files": data}
        for f in data.get("files", []):
            for sec in f["sections"]:
                run.point(f["path"], sec["start"], sec["end"])
        for hit in data.get("hits", []):
            if args[0] == "search":  # a ranked pointer (header and snippet) until a get shows the unit
                run.search_hits.append((hit["path"], hit["start"], hit["end"]))
            else:
                run.show(hit["path"], hit["start"], hit["end"])
            run.labelled.append({"path": hit["path"], "start": hit["start"], "end": hit["end"], "role": hit.get("role"),
                                 "temporal": hit.get("temporal"), "authority": hit.get("authority")})
        if args[0] == "refs":
            rows = data.get("lines", [])[:REFS_PAGE]
            run.cited = {(r["path"], r["line"]) for r in rows}
            for r in rows:
                run.show(r["path"], r["line"], r["line"])
                run.labelled.append({"path": r["path"], "start": r["line"], "end": r["line"], "role": r["role"], "temporal": r.get("temporal")})
        return data

    def initial(self, task: dict, run: Run) -> None:
        prompt, keys = task["prompt"], keys_of(task["prompt"])
        if keys and CITATION_INTENT.search(prompt):
            self.call(run, "refs", citation_target(keys), *(["--kind", "binds"] if BIND_INTENT.search(prompt) else []))
        elif keys:
            for key in keys:
                self.call(run, "get", key)
        elif self.stage == "B":
            data = self.call(run, "search", prompt)
            if data.get("hits"):
                hit = data["hits"][0]
                self.call(run, "get", f"{hit['path']}:{hit['start']}-{hit['end']}")
        else:
            self.grep_words(run, prompt)

    def grep_words(self, run: Run, prompt: str) -> None:
        words = keywords(prompt)
        if not words:
            return
        document = named_document(prompt, self.corpus)
        text, hits = grep("|".join(re.escape(w) for w in words), [document] if document else self.corpus.records, ignore_case=True, head=GREP_HEAD)
        self.show_grep(run, text, hits)
        best = best_hit(self.corpus, hits, words)
        if best:
            start, end, _ = self.corpus.enclosing_section(*best)
            self.call(run, "get", f"{best[0]}:{start}-{end}")

    def read_at(self, run: Run, path: str, line: int) -> bool:
        before = len(run.shown.get(path, set()))
        self.call(run, "get", f"{path}:{line}")
        _start, _end, title = self.corpus.enclosing_section(path, line)
        if len(run.shown.get(path, set())) - before <= 1 and title:  # a one-line unit: read its section by heading
            self.call(run, "get", f"{path}#{title}")
        return True

    def read_id(self, run: Run, ident: str) -> bool:
        self.call(run, "get", ident)
        return True

    def discover(self, task: dict, run: Run) -> bool:
        if self.stage == "A":
            return False
        if not run.search_hits:
            self.call(run, "search", task["prompt"])
        for path, start, end in run.search_hits:
            if not covered({"path": path, "start": start, "end": end}, run.shown, self.corpus):
                self.call(run, "get", f"{path}:{start}-{end}")
                return True
        if not self.outlined:  # like B1: scan headings when ranked hits run out
            self.outlined = True
            document = named_document(task["prompt"], self.corpus)
            self.call(run, "outline", *([document] if document else []))
            return True
        return False


class B0(Agent):
    """`rg` plus reads. B0 never repeats an identical rg call or read: when a step would repeat one, it
    moves to its next discovery strategy (the keyword grep, then one keyword at a time, then the next
    observed location)."""
    name = "B0"

    def reset(self) -> None:
        self.actions: set[tuple] = set()
        self.queue: list[str] | None = None  # keyword patterns not yet grepped
        self.words: list[str] = []

    def once(self, *action) -> bool:
        """True the first time an action is requested; an identical action is never repeated."""
        if action in self.actions:
            return False
        self.actions.add(action)
        return True

    def rg(self, run: Run, pattern: str, paths: list[str], ignore_case: bool = False) -> list[tuple[str, int]] | None:
        """One rg call: its hits, or None when the identical call was already made."""
        if not self.once("rg", pattern, ignore_case, tuple(paths)):
            return None
        text, hits = grep(pattern, paths, ignore_case=ignore_case, head=GREP_HEAD)
        self.show_grep(run, text, hits)
        return hits

    def read(self, run: Run, path: str, start: int, end: int) -> bool:
        if not self.once("sed", path, start, end):
            return False
        self.sed(run, path, start, end)
        return True

    def unread(self, path: str, line: int) -> bool:
        return not any(a[0] == "sed" and a[1] == path and a[2] <= line <= a[3] for a in self.actions)

    def initial(self, task: dict, run: Run) -> None:
        prompt, keys = task["prompt"], keys_of(task["prompt"])
        if keys and CITATION_INTENT.search(prompt):
            self.citations(run, prompt, citation_target(keys))
            return
        for key in keys:
            self.lookup(run, key)
        if not keys:
            self.discover(task, run)

    def lookup(self, run: Run, key: str) -> bool:
        section = SECTION_REF.fullmatch(key)
        pattern = rf"^#+\s+{re.escape(section.group(2))}\b" if section else id_pattern(key) if ID_PATTERN.fullmatch(key) else re.escape(key)
        paths = [named_document(key, self.corpus) or self.corpus.records[0]] if section else self.corpus.all_files
        hits = self.rg(run, pattern, paths)
        if hits is None:
            return False
        record_hits = [(p, l) for p, l in hits if p in self.corpus.records]
        target = definition_like(self.corpus, record_hits, key) or (record_hits[0] if record_hits else None)
        if target:
            self.read_at(run, *target)
        return True

    def read_at(self, run: Run, path: str, line: int) -> bool:
        return self.read(run, path, line - 3, line - 3 + observed_range(path))

    def read_id(self, run: Run, ident: str) -> bool:
        return self.lookup(run, ident)

    def discover(self, task: dict, run: Run) -> bool:
        if self.queue is None:
            self.words = keywords(task["prompt"])
            self.queue = (["|".join(re.escape(w) for w in self.words)] if self.words else []) + [re.escape(w) for w in self.words]
        while self.queue:
            if self.keyword_step(run, self.queue.pop(0)):
                return True
        return self.next_location(run)

    def keyword_step(self, run: Run, pattern: str) -> bool:
        hits = self.rg(run, pattern, self.corpus.all_files, ignore_case=True)
        if hits is None:
            return False
        best = best_hit(self.corpus, [(p, l) for p, l in hits if p in self.corpus.records], self.words)
        if best:
            span = observed_range(best[0])
            self.read(run, best[0], best[1] - span // 3, best[1] + span - span // 3)
        return True

    def next_location(self, run: Run) -> bool:
        """Read around the next observed record-file location that no read has covered yet."""
        for path, line, _end in run.pointers:
            if path in self.corpus.records and self.unread(path, line):
                return self.read_at(run, path, line)
        return False


class B1(Agent):
    name = "B1"

    def reset(self) -> None:
        self.outlined: set[str] = set()
        self.ranked: list[tuple[int, str, dict]] | None = None

    def initial(self, task: dict, run: Run) -> None:
        run.outputs.append(MANIFEST)
        prompt, keys = task["prompt"], keys_of(task["prompt"])
        if keys and CITATION_INTENT.search(prompt):
            self.citations(run, prompt, citation_target(keys))
            return
        for key in keys:
            self.lookup(run, key)
        if not keys:
            self.discover(task, run)

    def outline(self, run: Run, path: str) -> None:
        if path in self.outlined:
            return
        self.outlined.add(path)
        run.outputs.append(path + "\n" + "\n".join(f"{s['start']}:{'#' * s['level']} {s['title']}" for s in self.corpus.sections[path]))
        for s in self.corpus.sections[path]:
            run.point(path, s["start"], s["end"])

    def lookup(self, run: Run, key: str) -> None:
        section = SECTION_REF.fullmatch(key)
        if section:
            path = named_document(key, self.corpus) or self.corpus.records[0]
            self.outline(run, path)
            match = next((s for s in self.corpus.sections[path] if re.match(rf"{re.escape(section.group(2))}(?:[.\s]|$)", s["title"])), None)
            if match:
                self.sed(run, path, match["start"], match["end"])
            return
        family = key.rsplit("-", 1)[0] if ID_PATTERN.fullmatch(key) else None
        paths = [self.corpus.record(OWNER_FILE[family])] if family in OWNER_FILE else self.corpus.records
        for path in paths:
            self.outline(run, path)
        heading = next(((p, s) for p in paths for s in self.corpus.sections[p] if re.match(rf"{re.escape(key)}[:.\s]", s["title"] + " ")), None)
        if heading:
            self.sed(run, heading[0], heading[1]["start"], heading[1]["end"])
            return
        text, hits = grep(id_pattern(key) if family else re.escape(key), paths, head=20)
        self.show_grep(run, text, hits)
        target = definition_like(self.corpus, hits, key) or (hits[0] if hits else None)
        if target:
            self.read_at(run, *target)

    def read_at(self, run: Run, path: str, line: int) -> bool:
        start, end, _ = self.corpus.enclosing_section(path, line)
        self.sed(run, path, start, end)
        return True

    def read_id(self, run: Run, ident: str) -> bool:
        self.lookup(run, ident)
        return True

    def discover(self, task: dict, run: Run) -> bool:
        words = keywords(task["prompt"])
        if self.ranked is None:
            named = named_document(task["prompt"], self.corpus)
            paths = [named] if named else self.corpus.records
            for path in paths:
                self.outline(run, path)
            scored = ((sum(1 for w in words if w in s["title"].lower()), p, s) for p in paths for s in self.corpus.sections[p])
            self.ranked = sorted((t for t in scored if t[0]), key=lambda t: (-t[0], t[2]["end"] - t[2]["start"]))
        while self.ranked:
            _, path, section = self.ranked.pop(0)
            if not covered({"path": path, "start": section["start"], "end": section["end"]}, run.shown, self.corpus):
                self.sed(run, path, section["start"], section["end"])
                return True
        return False


def best_hit(corpus: Corpus, hits: list[tuple[str, int]], words: list[str]) -> tuple[str, int] | None:
    best, best_score = None, 0
    for path, line in hits:
        text = corpus.lines(path)[line - 1].lower()
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best, best_score = (path, line), score
    return best


def definition_like(corpus: Corpus, hits: list[tuple[str, int]], key: str) -> tuple[str, int] | None:
    shapes = (rf"^#+\s+{re.escape(key)}\b", rf"^\s*-\s+\*\*{re.escape(key)}\b", rf"^\|\s*\**{re.escape(key)}\**\s*\|", rf"^\s*{re.escape(key)}:")
    for path, line in hits:
        if any(re.search(s, corpus.lines(path)[line - 1]) for s in shapes):
            return path, line
    return None


def definition_line(corpus: Corpus, hits: list[tuple[str, int]], key: str) -> tuple[str, int] | None:
    """The target's own definition line among the hits, looked for in its owner file first."""
    owner = OWNER_FILE.get(key.rsplit("-", 1)[0]) if ID_PATTERN.fullmatch(key) else None
    return definition_like(corpus, sorted(hits, key=lambda hit: not (owner and hit[0].endswith(owner))), key)


# -- scoring --------------------------------------------------------------------------------------------
def covered(unit: dict, shown: dict[str, set[int]], corpus: Corpus) -> bool:
    """Union coverage: every non-blank line of the unit was shown somewhere (workflow coverage)."""
    lines = corpus.lines(unit["path"])
    needed = {n for n in range(unit["start"], unit["end"] + 1) if n <= len(lines) and lines[n - 1].strip()}
    return needed <= shown.get(unit["path"], set())


def content_range(unit: dict, corpus: Corpus) -> tuple[int, int]:
    """The unit's line range without blank edge lines."""
    lines = corpus.lines(unit["path"])
    start, end = unit["start"], unit["end"]
    while start < end and not lines[start - 1].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def contains(span: Span, unit: dict, corpus: Corpus) -> bool:
    start, end = content_range(unit, corpus)
    return span[0] == unit["path"] and span[1] <= start and end <= span[2]


def share(units: list[dict], test: Callable[[dict], bool]) -> float:
    return sum(1 for u in units if test(u)) / len(units) if units else 1.0


def score(task: dict, run: Run, corpus: Corpus, labels_authority: bool) -> dict:
    units = task["evidence"]
    distinct = list(dict.fromkeys(run.spans))
    top = distinct[:TOP_K]
    result = {"tokens": run.tokens, "initial_tokens": run.initial_tokens, "calls": len(run.outputs),
              "contained_recall": share(units, lambda u: any(contains(s, u, corpus) for s in distinct)),
              "top5_recall": share(units, lambda u: any(contains(s, u, corpus) for s in top)),
              "workflow_recall": share(units, lambda u: covered(u, run.shown, corpus))}
    if task.get("citations"):
        gold = {(l["path"], l["line"]) for l in task["citations"]["lines"]}
        got = run.cited or set()
        result["citation_precision"] = len(gold & got) / len(got) if got else 0.0
        result["citation_recall"] = len(gold & got) / len(gold) if gold else 1.0
    result["authority_errors"] = authority_errors(task, run, corpus) if labels_authority else None
    result["top5"] = [f"{p}:{a}-{b}" for p, a, b in top]
    result["shown"] = {path: ranges(lines) for path, lines in run.shown.items()}
    if run.seconds:
        result["seconds"] = run.seconds
    return result


def ranges(lines: set[int]) -> str:
    parts: list[list[int]] = []
    for n in sorted(lines):
        if parts and n == parts[-1][1] + 1:
            parts[-1][1] = n
        else:
            parts.append([n, n])
    return ",".join(f"{a}-{b}" if a != b else str(a) for a, b in parts)


def labelled_block(lines: list[str], label: str) -> set[int]:
    """Lines of each paragraph or list led by a bold label: the label line through the next blank line."""
    found: set[int] = set()
    for number, text in enumerate(lines, start=1):
        if text.lstrip().startswith(label):
            end = number
            while end < len(lines) and lines[end].strip():
                end += 1
            found.update(range(number, end + 1))
    return found


def historical_lines(path: str, corpus: Corpus) -> set[int]:
    """History inside a record file: historical sections, retired-claim lists and change-request rows."""
    name = path.rsplit("/", 1)[-1]
    lines = corpus.lines(path)
    found = corpus.section_lines(path, HISTORICAL_SECTIONS.get(name, ()))
    if name in HISTORICAL_LABELS:
        found |= labelled_block(lines, HISTORICAL_LABELS[name])
    if name == REQUEST_ROWS_FILE:
        found |= {n for n, text in enumerate(lines, start=1) if text.lstrip().startswith("|")}
    return found


def non_current_lines(span: dict, corpus: Corpus) -> set[int]:
    """The lines of a span that are not current record text."""
    path, lines = span["path"], set(range(span["start"], span["end"] + 1))
    if path not in corpus.records:
        return lines  # supporting material and the working trail
    if "/briefs/" in path:  # superseded by the PRD, except the economics section
        return lines - corpus.section_lines(path, (BRIEF_AUTHORITY[1],)) if path.endswith(BRIEF_AUTHORITY[0]) else lines
    return lines & historical_lines(path, corpus)


def labelled_current(shown: dict) -> bool:
    """Labelled as current record text: record role, no historical or partly historical label, no authority qualifier."""
    return shown.get("role") == "record" and shown.get("temporal") in (None, "current") and not shown.get("authority")


def authority_errors(task: dict, run: Run, corpus: Corpus) -> int:
    """Forbidden spans whose non-current lines overlap a shown span labelled current record."""
    errors = 0
    for bad in task.get("forbidden", []):
        stale = non_current_lines(bad, corpus)
        errors += any(s["path"] == bad["path"] and labelled_current(s) and any(s["start"] <= n <= s["end"] for n in stale)
                      for s in run.labelled)
    return errors


def condition_summary(scored: list[dict]) -> dict:
    entry = {
        "tasks": len(scored),
        "contained_complete": sum(1 for s in scored if s["contained_recall"] == 1.0),
        "mean_contained_recall": round(statistics.mean(s["contained_recall"] for s in scored), 3),
        "mean_top5_recall": round(statistics.mean(s["top5_recall"] for s in scored), 3),
        "workflow_recall": round(statistics.mean(s["workflow_recall"] for s in scored), 3),
        "workflow_complete": sum(1 for s in scored if s["workflow_recall"] == 1.0),
        "median_tokens": statistics.median(s["tokens"] for s in scored),
        "p90_tokens": sorted(s["tokens"] for s in scored)[int(0.9 * (len(scored) - 1))],
        "median_calls": statistics.median(s["calls"] for s in scored),
        "authority_errors": NOT_MEASURABLE if any(s["authority_errors"] is None for s in scored) else sum(s["authority_errors"] for s in scored),
    }
    cites = [s for s in scored if "citation_recall" in s]
    if cites:
        entry["citation_recall"] = round(statistics.mean(s["citation_recall"] for s in cites), 3)
        entry["citation_precision"] = round(statistics.mean(s["citation_precision"] for s in cites), 3)
    seconds = sorted(x for s in scored for x in s.get("seconds", []))
    if seconds:
        entry["p95_call_seconds"] = round(seconds[min(len(seconds) - 1, int(0.95 * len(seconds)))], 3)
    return entry


def stage_a_gate(lookup: dict | None) -> dict:
    """Median lookup tokens at least 30% below the stronger baseline, with no loss of contained-evidence completion."""
    if not lookup:
        return {"computable": False, "reason": "no section or exact tasks in this split"}
    stronger = max(BASELINES, key=lambda b: (lookup[b]["contained_complete"], -lookup[b]["median_tokens"]))
    ours, theirs = lookup["specdex-A"], lookup[stronger]
    reduction = 1 - ours["median_tokens"] / theirs["median_tokens"]
    no_loss = ours["contained_complete"] >= theirs["contained_complete"]
    return {"computable": True, "condition": "specdex-A", "tasks": "lookup (section + exact)", "stronger_baseline": stronger,
            "stronger_rule": "more contained-evidence completions on lookup tasks; ties: fewer median tokens",
            "median_lookup_tokens": {"specdex-A": ours["median_tokens"], stronger: theirs["median_tokens"]},
            "token_reduction": round(reduction, 3), "required_reduction": STAGE_A_REDUCTION,
            "contained_complete": {name: f"{e['contained_complete']}/{e['tasks']}" for name, e in (("specdex-A", ours), (stronger, theirs))},
            "no_evidence_loss": no_loss, "answer_correctness": NOT_MEASURABLE,
            "proxy_passed": reduction >= STAGE_A_REDUCTION and no_loss}


def stage_b_gate(tasks: dict | None, conditions: dict) -> dict:
    """Top-5 recall on paraphrase tasks at least 10 pp above Stage A plus rg (specdex-A), with no authority regression."""
    if not tasks:
        return {"computable": False, "reason": f"no {STAGE_B_CATEGORY} tasks in this split"}
    gain = 100 * (tasks["specdex-B"]["mean_top5_recall"] - tasks["specdex-A"]["mean_top5_recall"])
    regression = conditions["specdex-B"]["authority_errors"] > conditions["specdex-A"]["authority_errors"]
    return {"computable": True, "condition": "specdex-B vs specdex-A", "tasks": f"{STAGE_B_CATEGORY} ({tasks['specdex-B']['tasks']})",
            "top5_recall": {name: tasks[name]["mean_top5_recall"] for name in ("specdex-B", "specdex-A")},
            "gain_pp": round(gain, 1), "required_gain_pp": STAGE_B_GAIN_PP, "authority_regression": regression,
            "proxy_passed": gain >= STAGE_B_GAIN_PP and not regression}


def authority_gate(conditions: dict) -> dict:
    """Zero authority errors; only conditions with labelled output are measurable by the proxy."""
    errors = {name: entry["authority_errors"] for name, entry in conditions.items()}
    return {"errors": errors, "proxy_passed": all(v == 0 for v in errors.values() if v != NOT_MEASURABLE)}


def summarize(rows: list[dict], conditions: list[str]) -> dict:
    groups = {"lookup": LOOKUP} | {c: (c,) for c in sorted({r["category"] for r in rows})}

    def scored(condition: str, categories: tuple[str, ...] | None = None) -> list[dict]:
        return [r["conditions"][condition] for r in rows if categories is None or r["category"] in categories]

    overall = {c: condition_summary(scored(c)) for c in conditions}
    by_category = {name: {c: condition_summary(scored(c, cats)) for c in conditions}
                   for name, cats in groups.items() if any(r["category"] in cats for r in rows)}
    return {"continuation": CONTINUATION, "conditions": overall, "categories": by_category,
            "gates": {"stage_a": stage_a_gate(by_category.get("lookup")),
                      "stage_b": stage_b_gate(by_category.get(STAGE_B_CATEGORY), overall),
                      "authority": authority_gate(overall)}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "heldout", "all"), default="dev")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    files = {"dev": ["dev.json"], "heldout": ["heldout.json"], "all": ["dev.json", "heldout.json"]}[args.split]
    tasks = [t for f in files for t in json.loads((HERE / "gold" / f).read_text())]
    specdex("status")  # build once; every later call still verifies every byte
    corpus = Corpus()
    agents = [Specdex(corpus, "A"), Specdex(corpus, "B"), B0(corpus), B1(corpus)]
    rows = []
    for task in tasks:
        row = {"id": task["id"], "category": task["category"], "conditions": {}}
        for agent in agents:
            row["conditions"][agent.name] = score(task, agent.answer(task), corpus, agent.labels_authority)
        rows.append(row)
        print(f"{task['id']:4} " + "  ".join(f"{n}: {r['tokens']}t c{r['contained_recall']:.2f} t{r['top5_recall']:.2f}"
                                         + (f" cit{r['citation_recall']:.2f}" if "citation_recall" in r else "")
                                         for n, r in row["conditions"].items()), flush=True)
    summary = summarize(rows, [a.name for a in agents])
    out = args.out or HERE / "results" / f"layer-a-{args.split}.json"
    out.write_text(json.dumps({"split": args.split, "max_steps": MAX_STEPS, "summary": summary, "tasks": rows}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
