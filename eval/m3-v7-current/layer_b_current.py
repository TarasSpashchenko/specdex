# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""M3 Layer B on tamagai-v7-current: M1's harness (eval/m1-tamagai/layer_b.py) with current-layout ticket cases.

Default run (results-layer-b.json): M2's ticket cases B07-B09 re-targeted to a ticket tree in BMad's current layout
inside initiative-tamagai, and three new cases, each with a clean control:
  B14 an epic's Requirements line loses its parent link;
  B15 the PRD leaves the initiative's `sources:` while its References line still names it;
  B16 an FR is edited inside a shard of the PRD sharded with bmad-shard-pro.
The tree is checked once with BMad's own tickets.py (`status`), recorded under `tree_validation`.
`--full` (results-layer-b-full.json): M2's whole case set (layer_b.CASES) on this corpus, with latency.

Usage: python3 layer_b_current.py [--full] [--only ID ...] [--out FILE]   (uv is needed for tickets.py and shard_tool.py)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CORPUS_DEF = HERE / "tamagai_v7_current_def.py"
sys.path.insert(0, str(HERE.parent / "m1-tamagai"))
sys.argv[1:1] = ["--corpus-def", str(CORPUS_DEF)]  # layer_b reads its corpus definition from the command line on import
import layer_b as lb  # noqa: E402
from layer_b import Case, Lab, Outcome, Workspace  # noqa: E402

C = lb.C
TICKETS_PY = REPO / "_bmad" / "method" / "scripts" / "tickets.py"
SHARD_TOOL = REPO / ".agents" / "skills" / "bmad-shard-pro" / "scripts" / "shard_tool.py"
RESULTS = HERE / "results-layer-b.json"
FULL_RESULTS = HERE / "results-layer-b-full.json"

# -- the ticket tree, BMad's current layout ---------------------------------------------------------------------
EPIC_SLUG = "epic-parent-deletion"
EPIC_DIR = f"{C.TICKETS_DIR}/{EPIC_SLUG}"
EPIC_FILE = f"{EPIC_DIR}/{EPIC_SLUG}.md"
EPIC_TOML = f"{EPIC_DIR}/tickets/tickets.toml"
DELETE_STORY = f"{EPIC_DIR}/tickets/story-delete-everything.md"
STATES_STORY = f"{EPIC_DIR}/tickets/story-show-deletion-states.md"
LINKING_STORY = f"{EPIC_DIR}/tickets/story-show-linking-states.md"
PRD_SOURCES = f"sources: [{C.PRD}]"
PARENT_LINE = "- R2 (parent R1):"   # B14: the epic line story 1.2 covers


def entry(ident: int, title: str, covers: str, verify: str) -> str:
    return f"""[[entry]]
id = {ident}
type = "story"
title = "{title}"
description = "{title} in the parent area, as the epic's requirement {covers} says."
verify = "{verify}"
covers = ["{covers}"]
after = []
hitl = false
risk = "medium"
"""


DELETE_ENTRY = entry(1, "Delete everything", "R1", "After Delete everything the device holds no family data and the request is queued.")
STATES_ENTRY = entry(2, "Show deletion states", "R2", "Offline, failed and accepted requests each show their own confirmation.")
LINKING_ENTRY = entry(3, "Show linking states", "R3", "Linking, revoking consent and unlinking each show the state the PRD's table gives.")


def story(ident: int, title: str, covers: str, extra: str = "") -> str:
    return f"""---
id: {ident}
type: story
title: "{title}"
parent: {EPIC_SLUG}
covers: [{covers}]
after: []
{extra}hitl: false
risk: medium
---

# {title}

## Description

{title} in the parent area.

## Requirements

Verify: see the entry's verify line.

## References

- parent — {EPIC_FILE}
"""


TICKET_TREE = {
    C.INITIATIVE_FILE: f"""---
type: initiative
title: "Parents control and erase their family's data"
{PRD_SOURCES}
companions: []
after: []
status: in-progress
risk: medium
---

# Parents control and erase their family's data

## Description

A parent links the device, gives or revokes consent, and erases what Tamagai holds about the family.

## Outcome

Parents trust the parent area with their family's data.

## Requirements

- R1 (FR-71): A parent deletes everything Tamagai holds about the family, on the device and on our servers.
- R2 (prd FR-68): Linking and consent states follow the PRD's state table.

## References

- prd — {C.PRD}, section 4.10 Parent area
""",
    f"{C.TICKETS_DIR}/tickets.toml": f"""[[epic]]
id = 1
slug = "{EPIC_SLUG}"
title = "Parents erase everything"
description = "A parent erases the family's data and sees which deletion state it is in."
covers = ["R1", "R2"]
""",
    EPIC_FILE: f"""---
type: epic
title: "Parents erase everything"
parent: {C.INITIATIVE_NAME}
covers: [R1, R2]
sources: [{C.INITIATIVE_FILE}]
companions: []
after: []
status: in-progress
risk: medium
---

# Parents erase everything

## Description

A parent erases the family's data and sees which deletion state it is in.

## Outcome

Parents see their family's data gone and know whether our servers have accepted the request.

## Requirements

- R1 (parent R1): "Delete everything" removes the family's on-device data and requests deletion of the linked-parent record.
{PARENT_LINE} The confirmation tells local deletion, a request not yet accepted and an accepted request apart.
- R3 (parent R2): The parent area shows the linking and consent state the PRD's state table gives.

## References

- parent — {C.INITIATIVE_FILE}, section Requirements
""",
    EPIC_TOML: DELETE_ENTRY + "\n" + STATES_ENTRY + "\n" + LINKING_ENTRY,
    DELETE_STORY: story(1, "Delete everything", "R1", "refined: true\n"),
    f"{EPIC_DIR}/tickets/story-delete-everything-plan.md": """---
title: 'Delete everything'
type: feature
ticket: 1
created: '2026-11-11'
status: in-progress
---

## Intent

Delete everything removes the family's on-device data and queues the linked-parent request.
""",
    STATES_STORY: story(2, "Show deletion states", "R2"),
    LINKING_STORY: story(3, "Show linking states", "R3"),
}


def ticket_workspace(lab: Lab, name: str) -> Workspace:
    ws = lab.workspace(name)
    for path, text in TICKET_TREE.items():
        ws.write(path, text)
    return ws


def tickets_status(ws: Workspace) -> dict:
    """BMad's own reading of the tree: tickets.py status on the initiative folder."""
    done = subprocess.run(["uv", "run", "--quiet", str(TICKETS_PY), "--project-root", str(ws.root), "status", str(ws.path(C.INITIATIVE))],
                          capture_output=True, text=True)
    try:
        output = json.loads(done.stdout)
    except json.JSONDecodeError:
        output = done.stdout
    return {"command": f"uv run _bmad/method/scripts/tickets.py --project-root <workspace> status {C.INITIATIVE}",
            "exit": done.returncode, "stderr": done.stderr.strip(), "status": output}


def problems_of(ws: Workspace, ticket: str) -> list[dict]:
    return [p for p in ws.sdx("covers")["problems"] if p["ticket"] == ticket]


def ticket_findings(ws: Workspace, ticket: str) -> list[dict]:
    return [f for f in ws.lint() if f["code"].startswith("ticket-") and f["detail"].startswith(f"ticket {ticket} ")]


def fr_states(ws: Workspace, *ids: str) -> dict[str, str]:
    rows = ws.sdx("coverage", "--by", "tickets", "--family", "FR")["rows"]
    return {row["id"]: row["state"] for row in rows if row["id"] in ids}


# -- M2's ticket cases, re-targeted ------------------------------------------------------------------------------
def unresolved_covers(lab: Lab) -> Outcome:
    ws = ticket_workspace(lab, "unresolved-covers")
    control = not ws.sdx("covers")["problems"]
    ws.replace(EPIC_TOML, 'covers = ["R3"]', 'covers = ["R9"]')
    ws.replace(LINKING_STORY, "covers: [R3]", "covers: [R9]")
    problems = [p for p in problems_of(ws, "1.3") if p["covers"] == "R9" and p["state"] == "unresolved"]
    return Outcome(control, bool(problems), problems[0]["detail"] if problems else "not flagged")


def refined_file_drift(lab: Lab) -> Outcome:
    ws = ticket_workspace(lab, "refined-drift")
    control = not ws.sdx("covers")["drift"]
    ws.replace(DELETE_STORY, "covers: [R1]", "covers: [R1, R2]")
    drift = [d for d in ws.sdx("covers")["drift"] if d["ticket"] == "1.1"]
    return Outcome(control, bool(drift), f"drift: file {drift[0]['file_covers']} vs entry {drift[0]['entry_covers']}" if drift else "not flagged")


def planned_without_file(lab: Lab) -> Outcome:
    """Control: FR-68's epic requirement R3 has no entry, so FR-68 is a gap. Mutation: a planned entry (no file, no plan) covers R3."""
    ws = ticket_workspace(lab, "planned-ticket")
    ws.path(LINKING_STORY).unlink()
    ws.write(EPIC_TOML, DELETE_ENTRY + "\n" + STATES_ENTRY)
    before = ws.sdx("covers")
    control = not before["planned"] and not before["problems"] and "FR-68" in lb.ticket_gaps(ws)
    ws.write(EPIC_TOML, TICKET_TREE[EPIC_TOML])
    after = ws.sdx("covers")
    gap = "FR-68" in lb.ticket_gaps(ws)
    detected = after["planned"] == ["1.3"] and not after["problems"] and not gap
    return Outcome(control, detected, f"planned {after['planned']}; problems {len(after['problems'])}; FR-68 still a gap: {gap}")


# -- new in M3 ---------------------------------------------------------------------------------------------------
def lost_parent(lab: Lab) -> Outcome:
    """`- R2 (parent R1): …` becomes `- R2: …`. BMad's ticket template has every line of an epic with covers name a
    parent id or a source section; this line names neither, so story 1.2's R2 reaches nothing and must be flagged.
    `- R2 (Scope): …` would be no defect (a requirement at the epic's own altitude, `local`, coverage unknown): it is
    recorded as the contrast, not gated. Story 1.1 still reaches FR-71, so FR-71's coverage is not the signal."""
    ws = ticket_workspace(lab, "lost-parent")
    control = not problems_of(ws, "1.2") and not ticket_findings(ws, "1.2") and not ws.sdx("covers")["local"]
    ws.replace(EPIC_FILE, PARENT_LINE, "- R2:")
    report = ws.sdx("covers")
    flagged = [p for p in report["problems"] if (p["ticket"], p["covers"]) == ("1.2", "R2")]
    local = [item["detail"] for item in report["local"] if item["ticket"] == "1.2"]
    findings = ticket_findings(ws, "1.2")
    ws.replace(EPIC_FILE, "- R2:", "- R2 (Scope):")
    section = ws.sdx("covers")
    return Outcome(control, bool(flagged) and bool(findings),
                   f"'- R2:': covers problems {[(p['state'], p['detail']) for p in flagged]}, local {local}, lint {[f['code'] for f in findings]}; "
                   f"contrast '- R2 (Scope):': problems {len(section['problems'])}, local {[i['ticket'] for i in section['local']]}")


def prd_leaves_sources(lab: Lab) -> Outcome:
    """The initiative's `sources:` loses the PRD; its `prd —` References line still names it, which is a pointer,
    not a requirement source. Every chain through the PRD (1, 1.1, 1.2 to FR-71; 1, 1.3 to FR-68) must be flagged
    and neither FR may read as declared or missing."""
    ws = ticket_workspace(lab, "prd-leaves-sources")
    states = fr_states(ws, "FR-68", "FR-71")
    control = not ws.sdx("covers")["problems"] and states == {"FR-68": "declared", "FR-71": "declared"}
    ws.replace(C.INITIATIVE_FILE, PRD_SOURCES, "sources: []")
    flagged = {(p["ticket"], p["covers"], p["state"]) for p in ws.sdx("covers")["problems"]}
    expected = {("1", "R1"), ("1", "R2"), ("1.1", "R1"), ("1.2", "R2"), ("1.3", "R3")}
    findings = [f for f in ws.lint() if f["code"] == "ticket-upstream-unresolved"]
    after = fr_states(ws, "FR-68", "FR-71")
    detected = ({(t, c) for t, c, s in flagged if s == "upstream-unresolved"} == expected and len(findings) == len(expected)
                and set(after.values()) == {"unknown"})
    return Outcome(control, detected, f"control FR states {states}; flagged {sorted(flagged)}; lint ticket-upstream-unresolved {len(findings)}; FR states {after}")


# -- B16: an FR edited inside a shard ----------------------------------------------------------------------------
SHARD_IDS = ("FR-1", "FR-42", "FR-68", "FR-71", "FR-88", "FR-108")
FR_EDIT = ("FR-71", f"{C.PRD_DIR}/parent-area-and-profiles.md",
           "A parent can delete a word card, a toy, a keepsake, a diary entry,", "a voice clip,")
CONTRAST_EDIT = ("FR-42", f"{C.PRD_DIR}/teaching-and-show-and-tell.md",   # recorded, not gated: an FR the PRD's index never lists
                 'Pip plays a generic "a person!" reaction.', "Pip waves.")
LOCATION_KEYS = {"path", "line", "col", "start", "end", "hpath"}


def uv_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", "--quiet", str(SHARD_TOOL), *args], capture_output=True, text=True)


def sharded_prd(base: Path) -> tuple[Path, dict]:
    """The corpus PRD sharded by bmad-shard-pro's shard_tool.py, built once in a folder holding the PRD alone (the
    corpus folder's other files are not shards, and two of them have frontmatter `check` cannot parse)."""
    folder = base / Path(C.PRD_DIR).name
    folder.mkdir(parents=True)
    shutil.copy2(C.CORPUS / C.PRD, folder)
    plan = {"source": str(folder / Path(C.PRD).name), "folder": str(folder), "title": C.PRD_SHARD_TITLE, "lookup": C.PRD_SHARD_LOOKUP,
            "groups": [{"heading": heading, "shards": [{"file": f, "title": t, "summary": s, "start": a, "end": b} for f, t, s, a, b in shards]}
                       for heading, shards in C.PRD_SHARD_GROUPS]}
    (base / "shard-plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    built = uv_tool("build", str(base / "shard-plan.json"))
    if built.returncode:
        raise RuntimeError(f"shard_tool build exited {built.returncode}: {built.stderr.strip() or built.stdout}")
    checked = uv_tool("check", str(folder), "--rebuild")
    report = json.loads(checked.stdout)
    return folder, {"exit": checked.returncode, "failures": report.get("failures", []), "warnings": len(report.get("warnings", []))}


def without_locations(value):
    """An answer with its paths and lines left out; lists are compared as multisets."""
    if isinstance(value, dict):
        return {k: without_locations(v) for k, v in value.items() if k not in LOCATION_KEYS}
    if isinstance(value, list):
        return sorted((without_locations(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def shard_answers(ws: Workspace) -> dict:
    return {ident: without_locations({"resolve": ws.sdx("resolve", ident), "refs": ws.sdx("refs", ident)["lines"]}) for ident in SHARD_IDS}


def diff_is_empty(report: dict) -> bool:
    return not any(report[key] for key in ("added", "removed", "changed", "positional", "sections"))


def id_changes(report: dict) -> dict[str, list[str]]:
    """A diff's ID keys: added, removed and changed IDs, and the parents of changed positional lists."""
    return {key: [item["id"] for item in report[key]] for key in ("added", "removed", "changed")} | \
        {"positional": [item["parent"] for item in report["positional"]]}


def edit_fr(ws: Workspace, edit: tuple[str, str, str, str]) -> tuple[list[str], bool]:
    """Edit an FR's text in its shard; the IDs `diff HEAD` reports changed, and whether `get` returns the new text."""
    ident, shard, old, addition = edit
    ws.replace(shard, old, f"{old} {addition}")
    changed = id_changes(ws.sdx("diff", "HEAD"))["changed"]
    return changed, addition in "\n".join(hit["text"] for hit in ws.sdx("get", ident)["hits"])


def sharded_fr_edit(lab: Lab) -> Outcome:
    ws = lab.workspace("sharded-fr-edit", git=True)
    unsharded = shard_answers(ws)
    folder, check = sharded_prd(lab.base / "sharded-prd")
    ws.path(C.PRD).unlink()
    shutil.copytree(folder, ws.path(C.PRD_DIR), dirs_exist_ok=True)
    ws.commit("shard the PRD")
    differing = [ident for ident in SHARD_IDS if shard_answers(ws)[ident] != unsharded[ident]]
    sharding = {key: ids for key, ids in id_changes(ws.sdx("diff", "HEAD~1")).items() if ids}  # sharding itself: expected none
    control = check["exit"] == 0 and diff_is_empty(ws.sdx("diff", "HEAD")) and not differing
    changed, new_text = edit_fr(ws, FR_EDIT)
    contrast, contrast_text = edit_fr(ws, CONTRAST_EDIT)
    return Outcome(control, changed == [FR_EDIT[0]] and new_text,
                   f"shard_tool check --rebuild exit {check['exit']} ({check['warnings']} warnings); answers differing from the unsharded PRD: {differing}; "
                   f"ID diff of the sharding commit: {sharding}; "
                   f"{FR_EDIT[0]} edited: diff HEAD changed {changed}, get has the new text: {new_text}; "
                   f"then {CONTRAST_EDIT[0]} edited too: changed {contrast}, get has the new text: {contrast_text}")


CASES = [
    Case("B07", "deterministic", "unresolved covers source (tickets/ layout)", unresolved_covers),
    Case("B08", "deterministic", "refined file versus stale entry (tickets/ layout)", refined_file_drift),
    Case("B09", "deterministic", "planned ticket without a file (tickets/ layout)", planned_without_file),
    Case("B14", "deterministic", "epic Requirements line loses its parent", lost_parent),
    Case("B15", "deterministic", "PRD leaves the initiative's sources", prd_leaves_sources),
    Case("B16", "deterministic", "FR edited inside a shard", sharded_fr_edit),
]


# -- runner ------------------------------------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus-def", type=Path, help=argparse.SUPPRESS)  # set above, for layer_b
    parser.add_argument("--full", action="store_true", help="M2's whole case set, with latency")
    parser.add_argument("--only", nargs="*", help="case ids to run (no results file is written)")
    parser.add_argument("--out", type=Path, help=f"report file (default: {RESULTS.name}, or {FULL_RESULTS.name} with --full)")
    args = parser.parse_args()
    cases = lb.CASES if args.full else CASES
    selected = [c for c in cases if not args.only or c.id in args.only]
    with tempfile.TemporaryDirectory(prefix="specdex-layer-b-current-") as tmp:
        lab = Lab(Path(tmp))
        with ThreadPoolExecutor(lb.WORKERS) as pool:
            results = list(pool.map(lambda case: lb.run_case(lab, case), selected))
        extra = {"latency": lb.latency(lab)} if args.full else {"tree_validation": tickets_status(ticket_workspace(lab, "tree-validation"))}
    for r in results:
        print(f"{r['id']:4} {'PASS' if r['passed'] else 'FAIL'}  {r['title']}: {r['detail']}")
    report = {"corpus": C.NAME, "summary": lb.summarize(results), **extra, "cases": results}
    shown = {key: value for key, value in report.items() if key != "cases"}
    if "tree_validation" in shown:  # the status output is in the report file
        shown["tree_validation"] = {key: value for key, value in shown["tree_validation"].items() if key != "status"}
    print(json.dumps(shown, indent=1))
    if not args.only:
        (args.out or (FULL_RESULTS if args.full else RESULTS)).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    validated = args.full or report["tree_validation"]["exit"] == 0
    return 0 if validated and all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
