"""Maintenance commands: lint, impact, coverage, covers and diff.

These report deterministic evidence for the owning BMAD workflow. They never
claim semantic consistency or completion: an empty result is labelled with the
completeness of the scope it was computed over.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from . import render, tickets
from .queries import ROLE_ORDER, Queries

CITATION_PROBLEMS = ("unresolved", "ambiguous", "out-of-bounds", "historical")
SECOND_HOP_LIMIT = 8
VALIDATOR_TIMEOUT_S = 60
NOT_CHECKED = ("semantic consistency (contradictions without an ID edge), glossary synonym discipline and whether "
               "requirements are really fulfilled: these need the owning BMAD workflow's review")


@dataclass(slots=True)
class Finding:
    code: str
    severity: str          # high | medium | low | info
    path: str
    line: int
    detail: str
    source: str = "specdex"


@dataclass(slots=True)
class LintReport:
    scope: str
    findings: list[Finding] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    not_checked: str = NOT_CHECKED


def add_commands(sub) -> None:
    p = sub.add_parser("lint", help="mechanical integrity checks (duplicates, dangling refs, bounds, tokens, companions, replicas)")
    p.add_argument("--scope", default="record")
    p.add_argument("--no-validators", action="store_true", help="skip BMAD's own validators (lint_spine.py)")
    p = sub.add_parser("impact", help="what cites, binds, elaborates or covers an ID or a span")
    p.add_argument("target", help="ID, or path:start-end")
    p.add_argument("--scope", default="record")
    from . import coverage, diffing
    coverage.add_commands(sub)
    diffing.add_commands(sub)


def run(args, q: Queries) -> int:
    if args.command == "lint":
        report = lint(q, args.scope, validators=not args.no_validators)
        render_out(args, report, lint_text(report, q.index.generation))
        return 1 if any(f.severity == "high" for f in report.findings) else 0
    if args.command == "impact":
        result = impact(q, args.target, args.scope)
        render_out(args, result, impact_text(result, q.index.generation))
        return 0
    from . import coverage, diffing
    if args.command in coverage.COMMANDS:
        return coverage.run(args, q)
    return diffing.run(args, q)


def render_out(args, value, text: str) -> None:
    print(render.to_json(value) if args.json else text)


# -- lint -------------------------------------------------------------------------------------
def lint(q: Queries, scope: str, validators: bool = True) -> LintReport:
    roles = q.scope_roles(scope)
    report = LintReport(scope)
    in_scope = {p for p, f in q.files.items() if f["role"] in roles}
    for row in q.conn.execute("SELECT path, code, severity, line, detail FROM fdiag"):
        if row["path"] in in_scope:
            report.findings.append(Finding(row["code"], row["severity"], row["path"], row["line"], row["detail"]))
    for row in q.conn.execute("SELECT code, severity, path, line, detail FROM gdiag"):
        report.findings.append(Finding(row["code"], row["severity"], row["path"], row["line"], row["detail"]))
    report.findings += _citation_findings(q, in_scope)
    report.findings += _inherited_conflicts(q)
    if validators:
        report.findings += _run_validators(q, report)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    report.findings.sort(key=lambda f: (order.get(f.severity, 9), f.code, f.path, f.line))
    return report


def _citation_findings(q: Queries, in_scope: set[str]) -> list[Finding]:
    findings = []
    rows = q.conn.execute(
        "SELECT o.path, o.line, o.id, o.family, o.raw, o.via_range, o.status, s.temporal FROM occ o LEFT JOIN spans s ON s.sid=o.sid "
        "WHERE o.status IN (%s) ORDER BY o.path, o.line" % ",".join("?" * len(CITATION_PROBLEMS)), CITATION_PROBLEMS).fetchall()
    for row in rows:
        if row["path"] not in in_scope or (row["status"] == "historical" and row["temporal"] == "historical"):
            continue  # history may cite history
        what = {"unresolved": "dangling reference", "ambiguous": "ambiguous reference",
                "out-of-bounds": "positional reference past the end of its list",
                "historical": "cites an ID defined only in historical text"}[row["status"]]
        if row["family"] == "TOKEN":
            what = "unknown design-token path"
        detail = f"{what}: {row['id']}" + (f" (inside range {row['raw']})" if row["via_range"] else "")
        if row["status"] == "out-of-bounds":
            parent = row["id"].rsplit(".", 1)[0]
            count = q.conn.execute("SELECT n FROM poscount WHERE parent_id=?", (parent,)).fetchone()
            detail += f"; {parent} has {count['n'] if count else 0} item(s)"
        severity = "high" if row["status"] != "ambiguous" else "medium"
        findings.append(Finding(f"citation-{row['status']}", severity, row["path"], row["line"], detail))
    return findings


def _inherited_conflicts(q: Queries) -> list[Finding]:
    findings = []
    rows = q.conn.execute("SELECT o.path, o.line, o.id FROM occ o WHERE o.rule='inherited'").fetchall()
    for row in rows:
        local = q.conn.execute("SELECT line FROM defs WHERE id=? AND path=? AND effective='definition'", (row["id"], row["path"])).fetchone()
        if local:
            findings.append(Finding("inherited-conflict", "high", row["path"], row["line"],
                                    f"{row['id']} is inherited from the parent spine and also defined locally at line {local['line']}"))
    return findings


def _run_validators(q: Queries, report: LintReport) -> list[Finding]:
    """Run BMAD's own validators, but only the exact files the profile was built against (project files are
    executable code), and never against the live worktree when the index is a revision snapshot."""
    config = q.index.config
    findings = []
    for validator in config.validators:
        script = _find_skill_file(config, validator["command"])
        if script is None:
            report.validators.append(f"{validator['name']}: not installed")
            findings.append(Finding("validator-not-run", "medium", "", 0, f"{validator['name']}: not installed; its checks are missing"))
            continue
        unchecked = _why_not_run(config, q.index.mode, script[0], script[1])
        if unchecked:
            report.validators.append(f"{validator['name']}: not run ({unchecked})")
            findings.append(Finding("validator-not-run", "medium", "", 0, f"{validator['name']}: {unchecked}; its checks are missing"))
            continue
        for path, info in q.files.items():
            if info["artifact"] != validator["artifact"] or info["role"] not in ("record", "ambiguous"):
                continue
            command = _validator_command(validator["command"], script[1], (config.project_root / path).parent)
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=VALIDATOR_TIMEOUT_S)
                data = json.loads(done.stdout)
                findings_field = data.get("findings", []) if isinstance(data, dict) else None
                # lint_spine reports "ok": false whenever it has findings; only ok:false without findings is a failure.
                if (done.returncode != 0 or findings_field is None or data.get("error") or (data.get("ok") is False and not findings_field)
                        or not isinstance(findings_field, list) or not all(isinstance(item, dict) for item in findings_field)):
                    raise ValueError((data.get("error") if isinstance(data, dict) else None) or f"exit {done.returncode}, output {type(data).__name__}")
            except (OSError, subprocess.TimeoutExpired, ValueError) as error:  # JSONDecodeError is a ValueError
                report.validators.append(f"{validator['name']}: failed on {path} ({error})")
                findings.append(Finding("validator-failed", "medium", path, 0, f"{validator['name']} failed ({error}); its checks are missing"))
                continue
            report.validators.append(f"{validator['name']}: {path} ({data.get('total_findings', 0)} finding(s))")
            for item in data.get("findings", []):
                findings.append(Finding(f"{validator['name']}:{item.get('category')}", item.get("severity", "medium"), path,
                                        _line_of(item.get("location")), item.get("detail", ""), validator["name"]))
    return findings


def _validator_command(template: list[str], skill_root, workspace) -> list[str]:
    """The validator's command line. Python runs isolated (-I): the script's own folder, which is project files,
    must not shadow the standard library modules it imports; the hash pin covers only the script itself."""
    command = []
    for part in template:
        if part == "{python}":
            command += [sys.executable, "-I"]
        else:
            command.append(part.replace("{skill_root}", str(skill_root)).replace("{workspace}", str(workspace)))
    return command


def _why_not_run(config, mode: str, script, skill_root) -> str | None:
    if mode != "worktree":
        return "the index is a revision snapshot and validators read the live worktree"
    relative = script.relative_to(skill_root).as_posix()
    recorded = next((f["sha256"] for f in config.binding.get("files", []) if f["path"] == relative), None)
    if recorded is None:
        return "the profile records no hash for it"
    if hashlib.sha256(script.read_bytes()).hexdigest() != recorded:
        return "the installed file differs from the one the profile was built against"
    return None


def _find_skill_file(config, command: list[str]):
    for part in command:
        if "{skill_root}" not in part:
            continue
        relative = part.split("{skill_root}/", 1)[1]
        for root in config.binding.get("skill_roots", []):
            candidate = config.project_root / root
            if (candidate / relative).is_file():
                return candidate / relative, candidate
    return None


def _line_of(location) -> int:
    if isinstance(location, int):
        return location
    if isinstance(location, str):
        digits = "".join(ch if ch.isdigit() else " " for ch in location).split()
        return int(digits[0]) if digits else 0
    return 0


def lint_text(report: LintReport, generation: str) -> str:
    counts = defaultdict(int)
    for f in report.findings:
        counts[f.severity] += 1
    head = f"lint (scope {report.scope}): " + (", ".join(f"{k} {v}" for k, v in counts.items()) or "no findings")
    out = [head]
    for f in report.findings:
        where = f"{f.path}:{f.line}" if f.line else f.path
        out.append(f"{f.severity:6} {f.code:24} {where} {f.detail}")
    out += [f"validator {v}" for v in report.validators]
    out.append(f"not checked: {report.not_checked}")
    out.append(f"generation {generation}")
    return "\n".join(out)


# -- impact ------------------------------------------------------------------------------------
def impact(q: Queries, target: str, scope: str) -> dict:
    roles = q.scope_roles(scope)
    if ":" in target and not q.index.config.id_regex.fullmatch(target):
        ids = _ids_defined_in(q, target)
    else:
        ids = [q.resolve(target).query]
    return {"target": target, "scope": scope, "ids": [_impact_one(q, ident, roles) for ident in ids]}


def _ids_defined_in(q: Queries, ref: str) -> list[str]:
    path_part, _, lines = ref.rpartition(":")
    path = q._one_path(path_part)
    start, _, end = lines.partition("-")
    a, b = int(start), int(end or start)
    rows = q.conn.execute("SELECT DISTINCT d.id FROM defs d JOIN spans s ON s.sid=d.sid WHERE d.path=? AND d.effective='definition' "
                          "AND s.start<=? AND s.end>=? AND d.shape!='positional'", (path, b, a)).fetchall()
    return [r["id"] for r in rows]


def _impact_one(q: Queries, ident: str, roles: tuple[str, ...]) -> dict:
    resolution = q.resolve(ident)
    incoming = _incoming(q, [ident], roles)
    children = [r["id"] for r in q.conn.execute("SELECT DISTINCT id FROM defs WHERE parent_id=?", (ident,))]
    child_edges = _incoming(q, children, roles) if children else []
    hops = []
    for src in sorted({e["src_id"] for e in incoming if e["src_id"] and e["src_id"] != ident})[:SECOND_HOP_LIMIT]:
        edges = _incoming(q, [src], roles)
        by_kind = defaultdict(int)
        for e in edges:
            by_kind[e["kind"]] += 1
        hops.append({"via": src, "edges": len(edges), "by_kind": dict(by_kind)})
    return {"id": ident, "status": resolution.status,
            "definitions": [h.ref() for h in resolution.definitions],
            "incoming": incoming, "children": child_edges, "second_hop": hops}


def _incoming(q: Queries, ids: list[str], roles: tuple[str, ...]) -> list[dict]:
    """Every edge into `ids`; tickets that cover them are always included, since a change can invalidate them."""
    if not ids:
        return []
    rows = q.conn.execute(
        "SELECT o.path, o.line, o.id, o.kind, o.src_id, o.via_range, o.raw, o.status, f.role FROM occ o JOIN files f ON f.path=o.path "
        "WHERE o.id IN (%s) AND o.kind!='defines' AND f.role IN (%s) ORDER BY o.path, o.line"
        % (",".join("?" * len(ids)), ",".join("?" * len(roles))), (*ids, *roles)).fetchall()
    unique = {}
    for r in [dict(row) for row in rows] + tickets.covers_rows(q, ids):
        unique.setdefault((r["path"], r["line"], r["id"], r["kind"]), r)
    return sorted(unique.values(), key=lambda r: (ROLE_ORDER.get(r["role"], 9), r["kind"], r["path"], r["line"]))


def impact_text(result: dict, generation: str) -> str:
    out = []
    for item in result["ids"]:
        defined = ", ".join(item["definitions"])
        out.append(f"impact {item['id']}: {item['status']}" + (f" (defined {defined})" if defined else ""))
        groups = defaultdict(list)
        for e in item["incoming"]:
            groups[e["kind"]].append(e)
        for kind in ("binds", "covers", "elaborates", "mentions"):
            edges = groups.get(kind, [])
            if edges:
                out.append(f" {kind} ({len(edges)}):")
                out += render.grouped_locations([(e["path"], _edge_label(e)) for e in edges])
        if item["children"]:
            out.append(f" positional children cited ({len(item['children'])}):")
            out += render.grouped_locations([(e["path"], f"{e['line']} {e['id']}") for e in item["children"]])
        for hop in item["second_hop"]:
            kinds = ", ".join(f"{k} {v}" for k, v in sorted(hop["by_kind"].items()))
            out.append(f" second hop via {hop['via']}: {hop['edges']} edge(s) ({kinds})")
        if not item["incoming"] and not item["children"]:
            out.append(" no incoming edges in this scope")
    out.append(f"generation {generation}")
    return "\n".join(out)


def _edge_label(edge: dict) -> str:
    extra = []
    if edge["src_id"]:
        extra.append(edge["src_id"])
    if edge["via_range"]:
        extra.append(f"in {edge['raw']}")
    return f"{edge['line']}" + (f" ({', '.join(extra)})" if extra else "")
