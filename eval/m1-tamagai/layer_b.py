# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Layer B: maintenance mutations, identity cases, freshness checks and latency.

Every case runs on its own copy of the frozen corpus with its own index file.
A detection case passes only when its control (the copy before the mutation) is
clean for the check and the mutated copy is flagged, so pre-existing noise can
never count as a detection. Results go to results/layer-b.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LAUNCHER = REPO / "skills" / "specdex" / "scripts" / "specdex.py"
CORPUS = REPO / "eval" / "corpora" / "tamagai-2026-10-04"
OVERLAY = HERE / "overlay.toml"
RESULTS = HERE / "results" / "layer-b.json"

PA = "_bmad-output/planning-artifacts"
PRD_DIR = f"{PA}/prds/prd-tamagai-2026-09-29"
PRD = f"{PRD_DIR}/prd.md"
ADDENDUM = f"{PRD_DIR}/addendum.md"
DESIGN = f"{PA}/ux-designs/ux-tamagai-2026-09-30/DESIGN.md"
EXPERIENCE = f"{PA}/ux-designs/ux-tamagai-2026-09-30/EXPERIENCE.md"
SPINE_DIR = f"{PA}/architecture/architecture-tamagai-2026-10-03"
SPINE = f"{SPINE_DIR}/ARCHITECTURE-SPINE.md"
SHARED_EXPERIENCE = "_bmad-output/shared/EXPERIENCE.md"

WARM_CALLS = 30
P95 = 0.95
SLO_WARM_P95_S = 0.5
SLO_REBUILD_S = 5.0
WORKERS = 6


@dataclass(slots=True)
class Outcome:
    control_clean: bool
    detected: bool
    detail: str

    @property
    def passed(self) -> bool:
        return self.control_clean and self.detected


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    group: str      # deterministic | agent-only | identity | freshness
    title: str
    run: Callable[["Lab"], Outcome]


class Workspace:
    """A private copy of the corpus, its own overlay copy and its own index file."""

    def __init__(self, base: Path, name: str, overlay: bool = True, git: bool = False) -> None:
        home = base / name
        self.root = home / "project"
        shutil.copytree(CORPUS, self.root, symlinks=True)
        self.db = home / "index.sqlite"
        self.overlay = home / "overlay.toml" if overlay else None
        if self.overlay:
            shutil.copy(OVERLAY, self.overlay)
        if git:
            self.git("init", "-q")
            self.commit("frozen corpus")

    # -- specdex ------------------------------------------------------------------------------
    def command(self, *args: str, as_json: bool = True) -> list[str]:
        cmd = [sys.executable, str(LAUNCHER), "--project", str(self.root), "--db", str(self.db)]
        if self.overlay:
            cmd += ["--overlay", str(self.overlay)]
        return cmd + (["--json"] if as_json else []) + list(args)

    def sdx(self, *args: str):
        proc = subprocess.run(self.command(*args), capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"specdex {' '.join(args)} exited {proc.returncode}: {proc.stderr.strip()}")
        return json.loads(proc.stdout)

    def text(self, *args: str) -> str:
        return subprocess.run(self.command(*args, as_json=False), capture_output=True, text=True).stdout

    def lint(self, scope: str = "record") -> list[dict]:
        return self.sdx("lint", "--scope", scope, "--no-validators")["findings"]

    def search_paths(self, query: str, scope: str = "all") -> list[str]:
        return [hit["path"] for hit in self.sdx("search", query, "--scope", scope, "-k", "10")["hits"]]

    def file_row(self, path: str) -> dict | None:
        with sqlite3.connect(self.db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM files WHERE path=?", (path,)).fetchone()
        return dict(row) if row else None

    # -- files ----------------------------------------------------------------------------------
    def path(self, rel: str) -> Path:
        return self.root / rel

    def read(self, rel: str) -> str:
        return self.path(rel).read_text(encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        self.path(rel).parent.mkdir(parents=True, exist_ok=True)
        self.path(rel).write_text(text, encoding="utf-8")

    def replace(self, rel: str, old: str, new: str) -> None:
        text = self.read(rel)
        if text.count(old) != 1:
            raise ValueError(f"{rel}: expected exactly one {old!r}")
        self.write(rel, text.replace(old, new))

    def append(self, rel: str, addition: str) -> int:
        """Append lines; return the line number of the first appended non-blank line."""
        text = self.read(rel)
        if not text.endswith("\n"):
            text += "\n"
        first = text.count("\n") + 1 + (len(addition) - len(addition.lstrip("\n")))
        self.write(rel, text + addition)
        return first

    def line_of(self, rel: str, prefix: str) -> int:
        matches = [n for n, line in enumerate(self.read(rel).splitlines(), 1) if line.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"{rel}: expected one line starting {prefix!r}, found {len(matches)}")
        return matches[0]

    def delete_line(self, rel: str, prefix: str) -> str:
        lines = self.read(rel).splitlines(keepends=True)
        number = self.line_of(rel, prefix)
        removed = lines.pop(number - 1)
        self.write(rel, "".join(lines))
        return removed

    def insert_line(self, rel: str, number: int, line: str) -> None:
        lines = self.read(rel).splitlines(keepends=True)
        lines.insert(number - 1, line if line.endswith("\n") else line + "\n")
        self.write(rel, "".join(lines))

    def add_overlay(self, toml: str) -> None:
        with self.overlay.open("a", encoding="utf-8") as handle:
            handle.write("\n" + toml + "\n")

    def add_records(self, *paths: str) -> None:
        text = self.overlay.read_text(encoding="utf-8")
        entries = "".join(f'  "{p}",\n' for p in paths)
        self.overlay.write_text(text.replace("records = [\n", "records = [\n" + entries, 1), encoding="utf-8")

    # -- git --------------------------------------------------------------------------------
    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), "-c", "user.name=layer-b", "-c", "user.email=layer-b@example.invalid", *args],
                              capture_output=True, text=True, check=True).stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)


class Lab:
    def __init__(self, base: Path) -> None:
        self.base = base

    def workspace(self, name: str, overlay: bool = True, git: bool = False) -> Workspace:
        return Workspace(self.base, name, overlay, git)


def codes(findings: list[dict], code: str) -> list[dict]:
    return [f for f in findings if f["code"] == code]


def positional_entry(report: dict, parent: str) -> dict | None:
    return next((p for p in report["positional"] if p["parent"] == parent), None)


# -- deterministic maintenance mutations ------------------------------------------------------------
def range_hidden_citation(lab: Lab) -> Outcome:
    ws = lab.workspace("range-hidden")

    def range_citations() -> set[int]:
        rows = ws.sdx("refs", "FR-42")["lines"]
        return {r["line"] for r in rows if r["path"] == EXPERIENCE and r["via_range"]}

    before = range_citations()
    line = ws.append(EXPERIENCE, "\nThis flow also serves FR-40–44.\n")
    after = range_citations()
    impact_lines = {e["line"] for e in ws.sdx("impact", "FR-42")["ids"][0]["incoming"] if e["path"] == EXPERIENCE}
    return Outcome(line not in before, line in after and line in impact_lines,
                   f"EXPERIENCE.md:{line} 'FR-40–44' listed by refs FR-42: {line in after}; by impact: {line in impact_lines}")


def dropped_positional(lab: Lab) -> Outcome:
    ws = lab.workspace("dropped-positional", git=True)
    control = positional_entry(ws.sdx("diff", "HEAD"), "FR-88") is None
    ws.delete_line(PRD, "- The talk allowance is counted on the device per child profile.")
    entry = positional_entry(ws.sdx("diff", "HEAD"), "FR-88") or {}
    repointed = [i for i in entry.get("items", []) if i["id"] == "FR-88.3" and i["cited_at"]]
    detected = entry.get("kind", "").startswith("shifted") and bool(repointed)
    cited = len(repointed[0]["cited_at"]) if repointed else 0
    return Outcome(control, detected, f"FR-88 {entry.get('old_count')}→{entry.get('new_count')} {entry.get('kind')}; FR-88.3 re-pointed, cited at {cited} line(s)")


def changed_positional(lab: Lab) -> Outcome:
    ws = lab.workspace("changed-positional", git=True)
    control = positional_entry(ws.sdx("diff", "HEAD"), "FR-88") is None
    ws.replace(PRD, "- The credential never appears in logs next to purchase data.", "- The credential never appears in logs or traces next to purchase data.")
    entry = positional_entry(ws.sdx("diff", "HEAD"), "FR-88") or {}
    ids = [i["id"] for i in entry.get("items", [])]
    return Outcome(control, entry.get("kind") == "edited in place" and ids == ["FR-88.4"], f"FR-88 {entry.get('kind')}; items {ids}")


SPEC_TEMPLATE = """---
title: 'Spec {name}'
type: spec
status: draft
---

# Spec {name}

## Capabilities

- **CAP-1** — {capability}
- **CAP-2** — Reports progress; it depends on CAP-1.
"""
SPEC_A = "_bmad-output/specs/spec-alpha/SPEC.md"
SPEC_B = "_bmad-output/specs/spec-beta/SPEC.md"
SPECS_README = "_bmad-output/specs/README.md"


def same_id_scopes(lab: Lab) -> Outcome:
    ws = lab.workspace("same-id-scopes")
    control = not ws.sdx("resolve", "CAP-1")["status"].startswith("ambiguous")
    ws.write(SPEC_A, SPEC_TEMPLATE.format(name="alpha", capability="Exports a family archive."))
    ws.write(SPEC_B, SPEC_TEMPLATE.format(name="beta", capability="Imports a family archive."))
    ws.write(SPECS_README, "# Specs\n\nThe export path needs CAP-1.\n")
    ws.add_records(SPEC_A, SPEC_B)
    resolution = ws.sdx("resolve", "CAP-1")
    rows = {(r["path"], r["line"]): r["status"] for r in ws.sdx("refs", "CAP-1", "--scope", "all")["lines"]}
    inside = [status for (path, _), status in rows.items() if path in (SPEC_A, SPEC_B)]
    outside = rows.get((SPECS_README, 3))
    flagged = [f for f in codes(ws.lint("all"), "citation-ambiguous") if f["path"] == SPECS_README]
    detected = (resolution["status"].startswith("ambiguous") and len(resolution["definitions"]) == 2
                and inside == ["resolved", "resolved"] and outside == "ambiguous" and bool(flagged))
    return Outcome(control, detected, f"resolve CAP-1: {resolution['status']} ({len(resolution['definitions'])} defs); "
                                      f"in-folder citations {inside}; README citation {outside}; lint flagged {len(flagged)}")


EPIC_SPINE = f"{PA}/architecture/architecture-epic-pairing/ARCHITECTURE-SPINE.md"
EPIC_TEXT = """---
name: 'Pairing epic'
type: architecture-spine
altitude: epic
status: draft
binds: ['AD-3', 'AD-34']
companions: []
---

# Architecture Spine — Pairing epic

## Inherited Invariants

| Inherited | From parent | Binds here |
| --- | --- | --- |
| AD-3 | architecture-tamagai-2026-10-03 | pairing screens |
| AD-34 | architecture-tamagai-2026-10-03 | parent actions |

## Invariants & Rules

### AD-1 — Pairing codes expire

- **Binds:** pairing
- **Prevents:** stale codes
- **Rule:** a pairing code lives ten minutes (AD-1 is local to this epic).
"""


def inherited_ad(lab: Lab) -> Outcome:
    ws = lab.workspace("inherited-ad")
    ws.write(EPIC_SPINE, EPIC_TEXT)
    ws.add_records(EPIC_SPINE)
    row = ws.line_of(EPIC_SPINE, "| AD-3 |")
    local = ws.line_of(EPIC_SPINE, "- **Rule:** a pairing code")
    inherited = [r for r in ws.sdx("refs", "AD-3")["lines"] if r["path"] == EPIC_SPINE and r["line"] == row]
    resolution = ws.sdx("resolve", "AD-3")
    local_status = {r["line"]: r["status"] for r in ws.sdx("refs", "AD-1")["lines"] if r["path"] == EPIC_SPINE}.get(local)
    findings = ws.lint()
    clean = (bool(inherited) and inherited[0]["status"] == "resolved" and inherited[0]["rule"] == "inherited"
             and resolution["status"] == "defined" and len(resolution["definitions"]) == 1 and resolution["definitions"][0]["path"] == SPINE
             and local_status == "resolved"
             and not [f for f in codes(findings, "duplicate-definition") if f["path"] == EPIC_SPINE]
             and not codes(findings, "inherited-conflict"))
    ws.append(EPIC_SPINE, "\n### AD-3 — Local pairing override\n\n- **Rule:** pairing screens may skip the parent check.\n")
    conflicts = [f for f in codes(ws.lint(), "inherited-conflict") if f["path"] == EPIC_SPINE and f["line"] == row]
    return Outcome(clean, bool(conflicts), f"AD-3 row resolves to parent: {bool(inherited) and inherited[0]['status']}; "
                                           f"local AD-1 citation {local_status}; redefinition flagged: {bool(conflicts)}")


def missing_companion(lab: Lab) -> Outcome:
    ws = lab.workspace("missing-companion")
    control = not codes(ws.lint(), "missing-companion")
    ws.path(f"{SPINE_DIR}/CHANGE-REQUESTS.md").unlink()
    found = [f for f in codes(ws.lint(), "missing-companion") if f["path"] == SPINE]
    return Outcome(control, bool(found), found[0]["detail"] if found else "not flagged")


INITIATIVE = "_bmad-output/initiative-tamagai-mvp"
EPIC_DIR = f"{INITIATIVE}/epic-parent-deletion"
EPIC_TICKETS = f"{EPIC_DIR}/tickets.toml"
STORY = f"{EPIC_DIR}/story-delete-everything.md"
LINKING_STORY = f"{EPIC_DIR}/story-show-linking-states.md"
DELETE_ENTRY = """[[entry]]
id = 1
type = "story"
title = "Delete everything"
covers = ["E1"]
"""
LINKING_ENTRY = """
[[entry]]
id = 2
type = "story"
title = "Show linking states"
covers = ["E2"]
"""
TICKET_TREE = {
    f"{INITIATIVE}/initiative-tamagai-mvp.md": f"""---
type: initiative
title: "Parents control and erase their family's data"
parent: none
covers: [FR-68, FR-71]
status: in-progress
---

# Parents control and erase their family's data

## References

- prd — {PRD}, section 4.10 Parent area
""",
    f"{INITIATIVE}/tickets.toml": """[[epic]]
id = 1
slug = "epic-parent-deletion"
title = "Parents erase everything"
covers = ["FR-68", "FR-71"]
""",
    f"{EPIC_DIR}/epic-parent-deletion.md": """---
type: epic
title: "Parents erase everything"
parent: initiative-tamagai-mvp
covers: [FR-68, FR-71]
---

# Parents erase everything

## Requirements

- E1 (FR-71): Delete everything removes the family's data and queues the linked-parent request. (PRD, 4.10)
- E2 (FR-68): Linking states are shown to the parent. (PRD, 4.10)

## References

- parent — _bmad-output/initiative-tamagai-mvp/initiative-tamagai-mvp.md
""",
    EPIC_TICKETS: DELETE_ENTRY + LINKING_ENTRY,
    STORY: """---
id: 1
type: story
title: "Delete everything"
parent: epic-parent-deletion
covers: [E1]
refined: true
---

# Delete everything
""",
    LINKING_STORY: """---
id: 2
type: story
title: "Show linking states"
parent: epic-parent-deletion
covers: [E2]
---

# Show linking states
""",
}


def ticket_workspace(lab: Lab, name: str) -> Workspace:
    ws = lab.workspace(name)
    for path, text in TICKET_TREE.items():
        ws.write(path, text)
    return ws


def unresolved_covers(lab: Lab) -> Outcome:
    ws = ticket_workspace(lab, "unresolved-covers")
    control = not ws.sdx("covers")["problems"]
    ws.replace(EPIC_TICKETS, 'covers = ["E2"]', 'covers = ["E9"]')
    ws.replace(LINKING_STORY, "covers: [E2]", "covers: [E9]")
    problems = [p for p in ws.sdx("covers")["problems"] if p["ticket"] == "1.2" and p["covers"] == "E9"]
    return Outcome(control, bool(problems), problems[0]["detail"] if problems else "not flagged")


def refined_file_drift(lab: Lab) -> Outcome:
    ws = ticket_workspace(lab, "refined-drift")
    control = not ws.sdx("covers")["drift"]
    ws.replace(STORY, "covers: [E1]", "covers: [E1, E2]")
    drift = [d for d in ws.sdx("covers")["drift"] if d["ticket"] == "1.1"]
    return Outcome(control, bool(drift), f"drift: file {drift[0]['file_covers']} vs entry {drift[0]['entry_covers']}" if drift else "not flagged")


def ticket_gaps(ws: Workspace) -> list[str]:
    return [row["id"] for row in ws.sdx("coverage", "--by", "tickets", "--family", "FR", "--only", "gaps")["rows"]]


def planned_without_file(lab: Lab) -> Outcome:
    """Control: FR-68's requirement E2 has no entry, so FR-68 is a gap. Mutation: a planned entry (no file, no plan) covers E2."""
    ws = ticket_workspace(lab, "planned-ticket")
    ws.path(LINKING_STORY).unlink()
    ws.write(EPIC_TICKETS, DELETE_ENTRY)
    before = ws.sdx("covers")
    control = not before["planned"] and not before["problems"] and "FR-68" in ticket_gaps(ws)
    ws.write(EPIC_TICKETS, DELETE_ENTRY + LINKING_ENTRY)
    after = ws.sdx("covers")
    gap = "FR-68" in ticket_gaps(ws)
    detected = after["planned"] == ["1.2"] and not after["problems"] and not gap
    return Outcome(control, detected, f"planned {after['planned']}; problems {len(after['problems'])}; FR-68 still a gap: {gap}")


def reused_retired_id(lab: Lab) -> Outcome:
    ws = lab.workspace("reused-retired-id", git=True)
    row = ws.line_of(PRD, "| OQ-26 |")
    ws.delete_line(PRD, "| OQ-26 |")
    ws.commit("retire OQ-26")
    ws.insert_line(PRD, row, "| OQ-27 | Which onboarding video length keeps parents watching? | Store assets | Parent interviews |")
    ws.insert_line(PRD, row, "| OQ-26 | Which monthly price do parents accept for the server tier? | Pricing | Price survey |")
    added = {item["id"]: item for item in ws.sdx("diff", "HEAD")["added"]}
    reused, fresh = added.get("OQ-26", {}), added.get("OQ-27", {})
    return Outcome("OQ-27" in added and "seen_in_history" not in fresh, "seen_in_history" in reused,
                   f"OQ-26 history: {reused.get('seen_in_history')}; never-used OQ-27 history: {fresh.get('seen_in_history')}")


def same_size_restored_time(lab: Lab) -> Outcome:
    ws = lab.workspace("same-size-edit")
    generation = ws.sdx("status")["generation"]
    control = PRD not in ws.search_paths("tokem")
    path = ws.path(PRD)
    stat = path.stat()
    text = ws.read(PRD)
    edited = text.replace("rotating anonymous token", "rotating anonymous tokem", 1)
    assert len(edited.encode()) == len(text.encode())
    ws.write(PRD, edited)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after = ws.sdx("status")
    detected = after["generation"] != generation and PRD in ws.search_paths("tokem")
    return Outcome(control, detected, f"size and mtime unchanged; generation {generation} → {after['generation']}, reindexed {after['reindexed']}")


SECOND_PRD_DIR = f"{PA}/prds/prd-tamagai-2026-10-05"
UNIQUE_TO_COPY = "\n#### FR-999: Export the family archive\n\nDefined only in the copied PRD folder.\n"


def ambiguous_current(lab: Lab) -> Outcome:
    """Two PRD folders, no overlay: a shared ID (FR-71) and an ID only the copy defines (FR-999) are both ambiguous."""
    ws = lab.workspace("ambiguous-current", overlay=False)

    def prd_ambiguity() -> list[dict]:
        return [f for f in codes(ws.lint(), "ambiguous-current") if "prds/" in f["path"]]

    control = ws.sdx("resolve", "FR-71")["status"] == "defined" and ws.sdx("resolve", "FR-999")["status"] != "defined" and not prd_ambiguity()
    shutil.copytree(ws.path(PRD_DIR), ws.path(SECOND_PRD_DIR))
    ws.append(f"{SECOND_PRD_DIR}/prd.md", UNIQUE_TO_COPY)
    shared, unique = ws.sdx("resolve", "FR-71")["status"], ws.sdx("resolve", "FR-999")["status"]
    flagged = prd_ambiguity()
    return Outcome(control, shared.startswith("ambiguous") and unique.startswith("ambiguous") and bool(flagged),
                   f"resolve FR-71: {shared}; resolve FR-999 (copy only): {unique}; ambiguous-current flagged: {bool(flagged)}")


# -- agent-only ------------------------------------------------------------------------------------
def lint_limitation_message(lab: Lab) -> Outcome:
    """A semantic contradiction has no tool edge. This checks only that lint prints its limitation message
    instead of reading as clean; detecting the contradiction is left to an agent and is not measured here."""
    ws = lab.workspace("lint-limitation")
    ws.append(ADDENDUM, "\nThe server credential stays valid for seven days so that offline weekends keep working.\n")
    report = ws.sdx("lint", "--no-validators")
    states_limit = "semantic consistency" in report.get("not_checked", "") and "not checked:" in ws.text("lint", "--no-validators")
    mentions = [f for f in report["findings"] if f["path"] == ADDENDUM and "seven days" in f["detail"]]
    return Outcome(True, states_limit, f"contradiction flagged by the tool: {bool(mentions)} (expected no); lint states what it does not check: {states_limit}")


# -- identity ------------------------------------------------------------------------------------
DESIGN_EXPORT = f"{PA}/exports/DESIGN.md"


def identical_documents(lab: Lab) -> Outcome:
    ws = lab.workspace("identical-documents")
    before = ws.sdx("resolve", "colors.pip-cream")
    ws.write(DESIGN_EXPORT, ws.read(DESIGN))
    copies = [f for f in codes(ws.lint("all"), "copy-candidate") if DESIGN_EXPORT in f["path"] and DESIGN in f["path"]]
    after = ws.sdx("resolve", "colors.pip-cream")
    export = ws.file_row(DESIGN_EXPORT) or {}
    kept_distinct = export.get("extracted") == 1 and export.get("role") not in ("record", "ambiguous")
    unchanged = after["status"] == before["status"] == "defined" and [d["path"] for d in after["definitions"]] == [DESIGN]
    return Outcome(True, bool(copies) and kept_distinct and unchanged,
                   f"copy-candidate: {bool(copies)}; copy indexed separately as {export.get('role')}; colors.pip-cream still defined only in DESIGN.md: {unchanged}")


def declare_replica(ws: Workspace) -> None:
    ws.add_overlay(f'[[replica]]\npaths = ["{EXPERIENCE}", "{SHARED_EXPERIENCE}"]')


def single_definition(ws: Workspace, ident: str, path: str) -> bool:
    """Defined once at `path`, and no definition or elaboration comes from the shared copy."""
    resolution = ws.sdx("resolve", ident)
    places = [h["path"] for h in resolution["definitions"] + resolution.get("elaborations", [])]
    return resolution["status"] == "defined" and resolution["definitions"][0]["path"] == path and SHARED_EXPERIENCE not in places


def equal_replicas(lab: Lab) -> Outcome:
    ws = lab.workspace("equal-replicas")
    ws.write(SHARED_EXPERIENCE, ws.read(EXPERIENCE))
    declare_replica(ws)
    findings = ws.lint("all")
    row = ws.file_row(SHARED_EXPERIENCE) or {}
    noise = [f for f in findings if f["code"] in ("copy-candidate", "replica-drift", "duplicate-definition") and SHARED_EXPERIENCE in f["path"]]
    alias = row.get("extracted") == 0 and row.get("canonical") == EXPERIENCE and row.get("role") == "record"
    return Outcome(True, alias and not noise and single_definition(ws, "UJ-1", PRD),
                   f"alias of EXPERIENCE.md: {alias}; copy/drift/duplicate findings: {len(noise)}")


def drifting_replicas(lab: Lab) -> Outcome:
    ws = lab.workspace("drifting-replicas")
    ws.write(SHARED_EXPERIENCE, ws.read(EXPERIENCE))
    declare_replica(ws)
    control = not [f for f in codes(ws.lint("all"), "replica-drift") if f["path"] == SHARED_EXPERIENCE]
    ws.append(SHARED_EXPERIENCE, "\nA local note added only to the replica.\n")
    drift = [f for f in codes(ws.lint("all"), "replica-drift") if f["path"] == SHARED_EXPERIENCE]
    return Outcome(control, bool(drift) and single_definition(ws, "UJ-1", PRD), f"replica-drift flagged: {bool(drift)}")


def shared_symlink(lab: Lab) -> Outcome:
    ws = lab.workspace("shared-symlink")
    link = ws.path(SHARED_EXPERIENCE)
    link.parent.mkdir(parents=True)
    link.symlink_to(os.path.relpath(ws.path(EXPERIENCE), link.parent))
    findings = ws.lint("all")
    row = ws.file_row(SHARED_EXPERIENCE) or {}
    noise = [f for f in findings if f["code"] in ("copy-candidate", "duplicate-definition") and SHARED_EXPERIENCE in f["path"]]
    alias = row.get("is_link") == 1 and row.get("extracted") == 0 and row.get("canonical") == EXPERIENCE
    return Outcome(True, alias and not noise and single_definition(ws, "UJ-1", PRD), f"symlink is an alias: {alias}; copy/duplicate findings: {len(noise)}")


# -- freshness ------------------------------------------------------------------------------------
def dirty_edit(lab: Lab) -> Outcome:
    ws = lab.workspace("dirty-edit")
    control = PRD not in ws.search_paths("zebracorn")
    ws.append(PRD, "\nZebracorn audit marker for the freshness check.\n")
    return Outcome(control, PRD in ws.search_paths("zebracorn"), "uncommitted edit visible on the next call without a rebuild command")


def inserted_lines(lab: Lab) -> Outcome:
    ws = lab.workspace("inserted-lines")
    before = ws.sdx("resolve", "FR-88")
    start = before["definitions"][0]["start"]
    heading = ws.line_of(PRD, "# PRD")
    for _ in range(3):
        ws.insert_line(PRD, heading + 1, "Inserted line for the freshness check.")
    ws.replace(PRD, "- The credential never appears in logs next to purchase data.\n",
               "- The credential never appears in logs next to purchase data.\n- Rotation failures are retried once.\n")
    after = ws.sdx("resolve", "FR-88")
    moved = after["definitions"][0]["start"] == start + 3
    counted = before.get("children") == 4 and after.get("children") == 5
    return Outcome(True, moved and counted, f"FR-88 start {start} → {after['definitions'][0]['start']}; positional items {before.get('children')} → {after.get('children')}")


def delete_and_rename(lab: Lab) -> Outcome:
    ws = lab.workspace("delete-rename")
    victim, mover = f"{SPINE_DIR}/CHANGE-REQUESTS.md", EXPERIENCE
    renamed = f"{PA}/ux-designs/ux-tamagai-2026-09-30/EXPERIENCE-renamed.md"
    phrase_victim, phrase_mover = "Change requests from architecture", "Tamagai experience spec"
    control = victim in ws.search_paths(phrase_victim) and mover in ws.search_paths(phrase_mover)
    ws.path(victim).unlink()
    ws.path(mover).rename(ws.path(renamed))
    gone = victim not in ws.search_paths(phrase_victim)
    paths = ws.search_paths(phrase_mover)
    moved = renamed in paths and mover not in paths
    missing = [f for f in codes(ws.lint(), "missing-record") if f["path"] == EXPERIENCE]
    return Outcome(control, gone and moved and bool(missing), f"deleted file gone: {gone}; renamed file found at new path: {moved}; overlay record missing flagged: {bool(missing)}")


BROKEN_YAML_TARGET = f"{SPINE_DIR}/ARCHITECTURE-OVERVIEW.md"


def invalid_yaml(lab: Lab) -> Outcome:
    ws = lab.workspace("invalid-yaml")
    control = not [f for f in codes(ws.lint(), "parse-gap") if f["path"] == BROKEN_YAML_TARGET]
    ws.insert_line(BROKEN_YAML_TARGET, 2, "broken: [unclosed")  # line 1 opens the frontmatter
    gaps = [f for f in codes(ws.lint(), "parse-gap") if f["path"] == BROKEN_YAML_TARGET]
    searchable = BROKEN_YAML_TARGET in ws.search_paths("architecture overview", scope="record")
    return Outcome(control, bool(gaps) and searchable, f"parse-gap flagged: {bool(gaps)}; body still searchable: {searchable}")


def branch_change(lab: Lab) -> Outcome:
    ws = lab.workspace("branch-change", git=True)
    control = PRD not in ws.search_paths("quokkaline")
    ws.git("checkout", "-q", "-b", "feature")
    ws.append(PRD, "\nQuokkaline appears only on the feature branch.\n")
    ws.commit("feature edit")
    on_feature = PRD in ws.search_paths("quokkaline")
    ws.git("checkout", "-q", "-")
    back = PRD not in ws.search_paths("quokkaline")
    snapshot = subprocess.run(ws.command("--rev", "feature", "search", "quokkaline", "--scope", "all"), capture_output=True, text=True).stdout
    return Outcome(control, on_feature and back and "prd.md" in snapshot,
                   f"feature branch seen: {on_feature}; back on the first branch: {back}; --rev feature snapshot sees it: {'prd.md' in snapshot}")


def two_readers(lab: Lab) -> Outcome:
    """Control: the generation before the edit. Detection: both concurrent readers return one new generation."""
    ws = lab.workspace("two-readers")
    before = ws.sdx("status")["generation"]
    ws.append(PRD, "\nA concurrent-reader marker line.\n")
    procs = [subprocess.Popen(ws.command("status"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = [(p.wait(), *p.communicate()) for p in procs]
    generations = {json.loads(out)["generation"] for code, out, _ in results if code == 0}
    ok = all(code == 0 for code, _, _ in results) and len(generations) == 1 and before not in generations
    return Outcome(bool(before), ok, f"exit codes {[r[0] for r in results]}; generation {before} → {sorted(generations)}")


CASES = [
    Case("B01", "deterministic", "range-hidden citation", range_hidden_citation),
    Case("B02", "deterministic", "dropped positional consequence", dropped_positional),
    Case("B03", "deterministic", "changed positional consequence", changed_positional),
    Case("B04", "deterministic", "two same-ID scopes", same_id_scopes),
    Case("B05", "deterministic", "inherited AD and local redefinition", inherited_ad),
    Case("B06", "deterministic", "missing required companion", missing_companion),
    Case("B07", "deterministic", "unresolved covers source", unresolved_covers),
    Case("B08", "deterministic", "refined file versus stale entry", refined_file_drift),
    Case("B09", "deterministic", "planned ticket without a file", planned_without_file),
    Case("B10", "deterministic", "reused retired ID", reused_retired_id),
    Case("B11", "deterministic", "same-size restored-time edit", same_size_restored_time),
    Case("B12", "deterministic", "ambiguous current artifact", ambiguous_current),
    Case("B13", "agent-only", "agent-only: lint states its semantic-check limit (limitation message only, no detection)", lint_limitation_message),
    Case("I1", "identity", "identical independent documents", identical_documents),
    Case("I2", "identity", "declared equal replicas", equal_replicas),
    Case("I3", "identity", "declared drifting replicas", drifting_replicas),
    Case("I4", "identity", "shared symlink target", shared_symlink),
    Case("F1", "freshness", "dirty worktree edit", dirty_edit),
    Case("F2", "freshness", "inserted lines and bullets", inserted_lines),
    Case("F3", "freshness", "delete and rename", delete_and_rename),
    Case("F4", "freshness", "invalid YAML frontmatter", invalid_yaml),
    Case("F5", "freshness", "branch change", branch_change),
    Case("F6", "freshness", "two simultaneous readers", two_readers),
]


# -- latency ------------------------------------------------------------------------------------
WARM_QUERIES = [("resolve", "FR-88"), ("get", "prd §4"), ("refs", "FR-71"), ("search", "offline deletion outbox"),
                ("get", "AD-34"), ("refs", "UJ-3", "--scope", "all"), ("search", "talk allowance per child")]
TYPICAL_EDIT_LINES = 20


def timed(ws: Workspace, *args: str) -> tuple[float, dict]:
    started = time.perf_counter()
    data = ws.sdx(*args)
    return time.perf_counter() - started, data


def latency(lab: Lab) -> dict:
    ws = lab.workspace("latency")
    rebuild_s, cold = timed(ws, "status")
    warm = [timed(ws, *WARM_QUERIES[n % len(WARM_QUERIES)])[0] for n in range(WARM_CALLS)]
    lines = ws.read(PRD).splitlines(keepends=True)
    first = ws.line_of(PRD, "#### FR-88")
    for n in range(first, first + TYPICAL_EDIT_LINES):
        lines[n] = lines[n].rstrip("\n") + " (edited)\n"
    ws.write(PRD, "".join(lines))
    incremental_s, after = timed(ws, "status")
    p95 = statistics.quantiles(warm, n=100)[int(P95 * 100) - 1]
    return {"full_rebuild_s": round(rebuild_s, 3), "full_rebuild_update_ms": cold["update_ms"],
            "warm_p95_s": round(p95, 3), "warm_median_s": round(statistics.median(warm), 3), "warm_calls": WARM_CALLS,
            "incremental_s": round(incremental_s, 3), "incremental_update_ms": after["update_ms"], "incremental_reindexed": after["reindexed"],
            "slo": {"warm_p95_s": SLO_WARM_P95_S, "full_rebuild_s": SLO_REBUILD_S},
            "within_slo": p95 <= SLO_WARM_P95_S and rebuild_s <= SLO_REBUILD_S}


# -- runner ---------------------------------------------------------------------------------------
def run_case(lab: Lab, case: Case) -> dict:
    try:
        outcome = case.run(lab)
        return {"id": case.id, "group": case.group, "title": case.title, "passed": outcome.passed, **asdict(outcome)}
    except Exception as error:  # a crashing case is a failed case, never a silent skip
        return {"id": case.id, "group": case.group, "title": case.title, "passed": False, "control_clean": False,
                "detected": False, "detail": f"error: {type(error).__name__}: {error}"}


def summarize(results: list[dict]) -> dict:
    def tally(group: str) -> str:
        members = [r for r in results if r["group"] == group]
        return f"{sum(r['passed'] for r in members)}/{len(members)}"
    false_clean = [r["id"] for r in results if r["group"] == "deterministic" and r["control_clean"] and not r["detected"]]
    return {group: tally(group) for group in ("deterministic", "agent-only", "identity", "freshness")} | {"false_clean": false_clean}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="case ids to run")
    parser.add_argument("--no-latency", action="store_true")
    args = parser.parse_args()
    selected = [c for c in CASES if not args.only or c.id in args.only]
    with tempfile.TemporaryDirectory(prefix="specdex-layer-b-") as tmp:
        lab = Lab(Path(tmp))
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(lambda case: run_case(lab, case), selected))
        timing = None if args.no_latency else latency(lab)
    for r in results:
        print(f"{r['id']:4} {'PASS' if r['passed'] else 'FAIL'}  {r['title']}: {r['detail']}")
    report = {"summary": summarize(results), "latency": timing, "cases": results}
    print(json.dumps({"summary": report["summary"], "latency": timing}, indent=1))
    if not args.only:
        RESULTS.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
