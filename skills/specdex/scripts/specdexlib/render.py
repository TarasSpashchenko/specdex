"""Compact text and JSON renderings. Text output groups lines by file and prints
project-relative paths exactly as an answer should cite them."""
from __future__ import annotations

import dataclasses
import json
from itertools import groupby

from .queries import Hit, Resolution


def to_json(value) -> str:
    def default(obj):
        if dataclasses.is_dataclass(obj):
            return {k: v for k, v in dataclasses.asdict(obj).items() if v is not None and v != ""}
        if isinstance(obj, set):
            return sorted(obj)
        raise TypeError(type(obj).__name__)
    return json.dumps(value, default=default, ensure_ascii=False, indent=1)


def labels(hit: Hit) -> str:
    parts = [hit.role]
    if hit.temporal != "current":
        parts.append(hit.temporal)
    if hit.disposition:
        parts.append(f"decision: {hit.disposition}")
    if hit.flags:
        parts.append(hit.flags)
    if hit.authority:
        parts.append(hit.authority)
    return "[" + "; ".join(parts) + "]"


def section_of(hit: Hit) -> str:
    """Heading path without the file name (the reference already names the file)."""
    return hit.hpath.split(" › ", 1)[1] if " › " in hit.hpath else hit.hpath


def hit_header(hit: Hit) -> str:
    label = f" {hit.label}" if hit.label else ""
    return f"{hit.ref()} {labels(hit)}{label} — {section_of(hit)}"


def hits_text(hits: list[Hit], notes: list[str], generation: str) -> str:
    out = []
    for hit in hits:
        out.append(hit_header(hit))
        if hit.text is not None:
            out.append(hit.text)
        elif hit.snippet:
            out.append(f"  {hit.snippet}")
    out += [f"note: {n}" for n in notes]
    out.append(f"generation {generation}")
    return "\n".join(out)


def resolution_text(r: Resolution, generation: str) -> str:
    out = [f"{r.query}: {r.status}"]
    for hit in r.definitions:
        out.append("definition " + hit_header(hit))
        if hit.text is not None:
            out.append(hit.text)
    if r.children is not None:
        out.append(f"positional items: {r.children}" + (f" ({r.query}.1–{r.query}.{r.children})" if r.children else ""))
    for hit in r.elaborations:
        out.append(f"elaborated in {hit.ref()} {labels(hit)} — {section_of(hit)}")
    for hit in r.historical:
        out.append(f"historical definition {hit_header(hit)}")
    out += [f"note: {n}" for n in r.notes]
    out.append(f"generation {generation}")
    return "\n".join(out)


def refs_text(r: Resolution, rows: list[dict], empty: str | None, page: int, size: int, generation: str) -> str:
    files = len({row["path"] for row in rows})
    defined = f" at {', '.join(h.ref() for h in r.definitions)}" if r.definitions else ""
    head = f"{r.query}: {r.status}{defined}; {len(rows)} citing line(s) in {files} file(s)"
    notes = [f"note: {n}" for n in r.notes]
    if empty:
        return "\n".join([f"{head}: {empty}", *notes, f"generation {generation}"])
    start = (page - 1) * size
    chunk = rows[start:start + size]
    out = [head + (f"; page {page} of {(len(rows) + size - 1) // size}" if len(rows) > size else "")]
    for path, group in groupby(chunk, key=lambda row: row["path"]):
        group = list(group)
        out.append(f"{path} [{group[0]['role']}]")
        for row in group:
            tags = [] if row["kind"] == "mentions" else [row["kind"]]
            if row["temporal"] and row["temporal"] != "current":
                tags.append(row["temporal"])
            if row["via_range"]:
                tags.append(f"in {row['raw']}")
            if row["status"] not in (None, "resolved"):
                tags.append(row["status"])
            if len(row["ids"]) > 1 or (next(iter(row["ids"])) != r.query and row["status"] != "textual"):
                tags.append("cites " + ",".join(sorted(row["ids"])))
            if row["src_id"]:
                tags.append(f"in {row['src_id']}")
            tag = f" [{'; '.join(tags)}]" if tags else ""
            out.append(f"  {row['line']}{tag} {row['excerpt']}")
    if len(rows) > start + size:
        out.append(f"note: {len(rows) - start - size} more; use --page {page + 1}")
    out += notes
    out.append(f"generation {generation}")
    return "\n".join(out)


def outline_text(files: list[dict], generation: str) -> str:
    out = []
    for f in files:
        out.append(f"{f['path']} [{f['role']}] {f['lines']} lines")
        base = min((s["level"] for s in f["sections"]), default=1)
        for s in f["sections"]:
            out.append(f"{'  ' * (s['level'] - base + 1)}{s['start']}-{s['end']} {s['title']}")
    out.append(f"generation {generation}")
    return "\n".join(out)


def status_text(s: dict) -> str:
    roles = ", ".join(f"{k} {v}" for k, v in sorted(s["roles"].items()))
    binding = s["binding"]
    lines = [
        f"mode {s['mode']} · generation {s['generation']} · profile {s['profile']} ({binding['state']})",
        f"overlay {s['overlay'] or 'none'}",
        f"files {s['files']}: {roles}",
        f"verify {s['verify_ms']} ms · update {s['update_ms']} ms · reindexed {s['reindexed']} file(s)",
    ]
    if binding["mismatched"] or binding["missing"]:
        lines.append(f"binding: mismatched {binding['mismatched']} missing {binding['missing']}")
    for d in s["diagnostics"]:
        lines.append(f"diagnostic {d['code']} ({d['severity']}): {d['n']}")
    return "\n".join(lines)


def grouped_locations(items: list[tuple[str, str]]) -> list[str]:
    """[(path, 'line text')] → one line per file: 'file: a, b, c'."""
    out = []
    for path, group in groupby(sorted(items, key=lambda i: i[0]), key=lambda i: i[0]):
        out.append(f"  {path}: " + ", ".join(text for _, text in group))
    return out
