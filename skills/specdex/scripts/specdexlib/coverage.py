"""Declared coverage: join a required population to explicit trace edges.

States per requirement: declared (with the evidence), missing, unknown (a
broken or ambiguous chain could reach it), n/a. Declared coverage is evidence
for the owning workflow, never a claim that the work is complete.
"""
from __future__ import annotations

from collections import defaultdict

from . import render, tickets
from .queries import Queries

COMMANDS = ("coverage", "covers")
UX_ARTIFACTS = ("ux-experience", "ux-design")


def add_commands(sub) -> None:
    p = sub.add_parser("coverage", help="declared coverage of requirements by tickets, architecture or UX")
    p.add_argument("--by", choices=("tickets", "architecture", "ux"), required=True)
    p.add_argument("--family", action="append", help="requirement family (default: the overlay's coverage setting)")
    p.add_argument("--only", choices=("declared", "missing", "unknown", "gaps"), help="filter rows ('gaps' = missing + unknown)")
    sub.add_parser("covers", help="validate every ticket's covers chain against its requirement source")


def run(args, q: Queries) -> int:
    if args.command == "covers":
        report = covers(q)
        print(render.to_json(report) if args.json else covers_text(report, q.index.generation))
        return 1 if report["problems"] else 0
    report = coverage(q, args.by, args.family)
    if args.only:
        wanted = ("missing", "unknown") if args.only == "gaps" else (args.only,)
        report["rows"] = [r for r in report["rows"] if r["state"] in wanted]
    print(render.to_json(report) if args.json else coverage_text(report, q.index.generation))
    return 1 if any(r["state"] in ("missing", "unknown") for r in report["rows"]) else 0


def population(q: Queries, families: list[str]) -> list[dict]:
    rows = q.conn.execute(
        "SELECT d.id, d.family, d.path, d.line, s.temporal FROM defs d JOIN spans s ON s.sid=d.sid JOIN files f ON f.path=d.path "
        "WHERE d.effective='definition' AND d.shape!='positional' AND f.role='record' AND d.family IN (%s)" % ",".join("?" * len(families)),
        families).fetchall()
    def key(r):
        tail = r["id"].rsplit("-", 1)[-1]
        return (r["family"], int(tail) if tail.isdigit() else 0, r["id"])
    return [dict(r) for r in sorted(rows, key=key) if r["temporal"] != "historical"]


def coverage(q: Queries, by: str, families: list[str] | None) -> dict:
    families = families or q.index.config.coverage.get(by) or []
    members = population(q, families)
    if by == "architecture":
        evidence = _architecture_edges(q)
    elif by == "ux":
        evidence = _ux_edges(q)
    else:
        evidence = _ticket_edges(q)
    rows = []
    for member in members:
        found = evidence.get(member["id"], {})
        state = "declared" if found.get("declared") else "unknown" if found.get("unknown") else "missing"
        rows.append({"id": member["id"], "state": state, "declared": sorted(found.get("declared", [])),
                     "partial": sorted(found.get("partial", [])), "unknown": sorted(found.get("unknown", []))})
    counts = defaultdict(int)
    for row in rows:
        counts[row["state"]] += 1
    complete = q.scope_complete(("record", "ambiguous"))
    return {"by": by, "families": families, "counts": dict(counts), "rows": rows,
            "scope": "fully indexed" if complete is None else f"incomplete: {complete}"}


def _architecture_edges(q: Queries) -> dict[str, dict[str, set]]:
    evidence: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    rows = q.conn.execute(
        "SELECT o.id, o.src_id, o.rule, o.status, o.path, o.line FROM occ o JOIN files f ON f.path=o.path "
        "WHERE o.kind='binds' AND f.role='record' AND f.artifact='architecture-spine'").fetchall()
    for row in rows:
        if row["status"] == "ambiguous":
            evidence[row["id"]]["unknown"].add(f"{row['path']}:{row['line']}")
        elif row["rule"] == "binds-marker":
            evidence[row["id"]]["declared"].add(row["src_id"])
        else:
            evidence[row["id"]]["partial"].add("spine frontmatter binds")
    return evidence


def _ux_edges(q: Queries) -> dict[str, dict[str, set]]:
    evidence: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    rows = q.conn.execute(
        "SELECT d.id, d.path, d.line FROM defs d JOIN files f ON f.path=d.path WHERE d.effective='elaboration' AND f.role='record' "
        "AND f.artifact IN (%s)" % ",".join("?" * len(UX_ARTIFACTS)), UX_ARTIFACTS).fetchall()
    for row in rows:
        evidence[row["id"]]["declared"].add(f"{row['path'].rsplit('/', 1)[-1]}:{row['line']}")
    return evidence


def _ticket_edges(q: Queries) -> dict[str, dict[str, set]]:
    evidence: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    tree = tickets.load_tree(q)
    by_ref = {t.ref: t for t in tree.tickets}
    broken_containers = set()
    for chain in tickets.chains(q, tree):
        ticket = by_ref[chain.ticket]
        is_leaf = "." in chain.ticket
        label = chain.ticket + (" (planned)" if ticket.planned else "")
        if chain.state != "resolved" and is_leaf:
            broken_containers.add(ticket.container)
        if chain.state == "resolved" and chain.target:
            evidence[chain.target]["declared" if is_leaf else "partial"].add(label if is_leaf else f"epic {label}")
        elif chain.target:
            evidence[chain.target]["unknown"].add(f"{label}: {chain.state}")
    # An epic that claims an ID while one of its leaf chains is broken makes the ID unknown, never missing.
    for ticket in tree.tickets:
        if "." in ticket.ref:
            continue
        folder = next((f for f, c in tree.containers.items() if c.epic_id == ticket.ref), None)
        if folder in broken_containers:
            for covered in ticket.covers:
                if not evidence[covered].get("declared"):
                    evidence[covered]["unknown"].add(f"epic {ticket.ref} has an unresolved leaf chain")
    return evidence


def covers(q: Queries) -> dict:
    tree = tickets.load_tree(q)
    all_chains = tickets.chains(q, tree)
    problems = [{"ticket": c.ticket, "covers": c.covered_id, "state": c.state, "detail": c.detail} for c in all_chains if c.state != "resolved"]
    drift = []
    for ticket in tree.tickets:
        if ticket.file is not None and ticket.file_covers is not None and sorted(ticket.file_covers) != sorted(ticket.covers):
            drift.append({"ticket": ticket.ref, "file": ticket.file, "file_covers": ticket.file_covers, "entry_covers": ticket.covers})
    for code, path, line, detail in tree.problems:
        problems.append({"ticket": None, "covers": None, "state": code, "detail": f"{path}:{line} {detail}"})
    planned = [t.ref for t in tree.tickets if t.planned]
    return {"tickets": len(tree.tickets), "chains": len(all_chains), "problems": problems, "drift": drift, "planned": planned,
            "note": None if tree.tickets else "no ticket tree in the indexed scope (not a defect)"}


def covers_text(report: dict, generation: str) -> str:
    out = [f"covers: {report['tickets']} ticket(s), {report['chains']} chain(s), {len(report['problems'])} problem(s), {len(report['drift'])} drifted file(s)"]
    if report["note"]:
        out.append(f"note: {report['note']}")
    for p in report["problems"]:
        out.append(f" {p['state']}: ticket {p['ticket']} covers {p['covers']} — {p['detail']}")
    for d in report["drift"]:
        out.append(f" drift: ticket {d['ticket']} file {d['file']} covers {d['file_covers']} vs tickets.toml {d['entry_covers']} (the file is the truth)")
    if report["planned"]:
        out.append(f" planned (no file yet, not a defect): {', '.join(report['planned'])}")
    out.append(f"generation {generation}")
    return "\n".join(out)


def coverage_text(report: dict, generation: str) -> str:
    counts = ", ".join(f"{k} {v}" for k, v in sorted(report["counts"].items()))
    out = [f"coverage by {report['by']} of {', '.join(report['families'])}: {counts or 'empty population'} ({report['scope']})"]
    for row in report["rows"]:
        detail = row["declared"] or row["unknown"] or row["partial"]
        out.append(f" {row['id']:8} {row['state']:9} {', '.join(detail)}")
    out.append(f"generation {generation}")
    return "\n".join(out)
