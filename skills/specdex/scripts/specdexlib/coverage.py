"""Declared coverage: join a required population to explicit trace edges.

States per requirement: declared (with the evidence), missing, unknown (a
broken or ambiguous chain could reach it), n/a. Declared coverage is evidence
for the owning workflow, never a claim that the work is complete.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from . import layout, render, tickets
from .cli import EXIT_USAGE
from .diffing import SCOPE_MARK
from .queries import Queries

COMMANDS = ("coverage", "covers")
UX_ARTIFACTS = ("ux-experience", "ux-design")
RECORD_ROLES = ("record", "ambiguous")
UNDEFINED_STATES = ("unresolved", "upstream-unresolved")  # what every chain ends in when no spec of record exists
BROKEN_LEAF = "an unresolved leaf chain"
UNMAPPED_LEAF = "a leaf citing a local id whose parent map is not checked"
FULLY_INDEXED = "fully indexed"


def add_commands(sub) -> None:
    p = sub.add_parser("coverage", help="declared coverage of requirements by tickets, architecture or UX")
    p.add_argument("--by", choices=("tickets", "architecture", "ux"), required=True)
    p.add_argument("--family", action="append", help="requirement family (default: the coverage setting)")
    p.add_argument("--only", choices=("declared", "missing", "unknown", "gaps"), help="filter rows ('gaps' = missing + unknown)")
    sub.add_parser("covers", help="validate every ticket's covers chain against its requirement source")


def run(args, q: Queries) -> int:
    if args.command == "covers":
        report = covers(q)
        print(render.to_json(report) if args.json else covers_text(report, q.index.generation))
        return 1 if report["problems"] else 0
    families = args.family or q.index.config.coverage.get(args.by)
    if not families:  # an empty population would read as a clean result
        print(f"specdex: coverage --by {args.by} counts no requirement family: set coverage.{args.by} under [workflow] "
              "in _bmad/custom/specdex.toml, or pass --family", file=sys.stderr)
        return EXIT_USAGE
    report = coverage(q, args.by, families)
    # Nothing counted, or counted over a scope not fully indexed, is no clean result.
    unsure = not report["rows"] or report["scope"] != FULLY_INDEXED
    if args.only:
        wanted = ("missing", "unknown") if args.only == "gaps" else (args.only,)
        report["rows"] = [r for r in report["rows"] if r["state"] in wanted]
    print(render.to_json(report) if args.json else coverage_text(report, q.index.generation))
    return 1 if unsure or any(r["state"] in ("missing", "unknown") for r in report["rows"]) else 0


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
        # A document-scoped ID (CAP-1 of one spec) is its own requirement; architecture and UX edges name IDs only.
        scoped = tickets.document_scoped(q, member["family"])
        found = (scoped and evidence.get((member["path"], member["id"]))) or evidence.get(member["id"], {})
        state = "declared" if found.get("declared") else "unknown" if found.get("unknown") else "missing"
        row = {"id": member["id"], "state": state, "declared": sorted(found.get("declared", [])),
               "partial": sorted(found.get("partial", [])), "unknown": sorted(found.get("unknown", []))}
        if scoped:
            row["path"] = member["path"]
        rows.append(row)
    counts = defaultdict(int)
    for row in rows:
        counts[row["state"]] += 1
    complete = q.scope_complete(RECORD_ROLES)
    return {"by": by, "families": families, "counts": dict(counts), "rows": rows,
            "scope": FULLY_INDEXED if complete is None else f"incomplete: {complete}"}


def _architecture_edges(q: Queries) -> dict:
    """A spine binds requirement IDs: population IDs directly, or its ticket's R ids, which reach population IDs
    through the same Requirements lines a ticket chain follows (the spine's run folder sits in that ticket)."""
    evidence: dict = defaultdict(lambda: defaultdict(set))
    rows = q.conn.execute(
        "SELECT o.id, o.family, o.src_id, o.rule, o.status, o.path, o.line FROM occ o JOIN files f ON f.path=o.path "
        "WHERE o.kind='binds' AND f.role='record' AND f.artifact='architecture-spine'").fetchall()
    tree = tickets.load_tree(q) if any(_ticket_owned(q, row["family"]) for row in rows) else None
    for row in rows:
        kind, label = ("declared", row["src_id"]) if row["rule"] == "binds-marker" else ("partial", "spine frontmatter binds")
        if tree is not None and _ticket_owned(q, row["family"]):
            for reach in tickets.trace(q, tree, tickets.container_holding(tree, row["path"]), row["id"]):
                key = (reach.target_path, reach.target) if reach.target_path else reach.target
                if reach.state in tickets.REACHED and reach.target:
                    evidence[key][kind].add(label)
                elif reach.target:
                    evidence[key]["unknown"].add(f"{row['path']}:{row['line']} {row['id']}: {reach.state}")
        elif row["status"] == "ambiguous":
            evidence[row["id"]]["unknown"].add(f"{row['path']}:{row['line']}")
        else:
            evidence[row["id"]][kind].add(label)
    return evidence


def _ticket_owned(q: Queries, family: str) -> bool:
    """A family a ticket defines (R ids)."""
    owners = getattr(q.index.config.families.get(family), "owners", ())
    return any(owner in layout.CONTAINER_TYPES for owner in owners)


def _ux_edges(q: Queries) -> dict[str, dict[str, set]]:
    evidence: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    rows = q.conn.execute(
        "SELECT d.id, d.path, d.line FROM defs d JOIN files f ON f.path=d.path WHERE d.effective='elaboration' AND f.role='record' "
        "AND f.artifact IN (%s)" % ",".join("?" * len(UX_ARTIFACTS)), UX_ARTIFACTS).fetchall()
    for row in rows:
        evidence[row["id"]]["declared"].add(f"{row['path'].rsplit('/', 1)[-1]}:{row['line']}")
    return evidence


def _ticket_edges(q: Queries) -> dict:
    evidence: dict = defaultdict(lambda: defaultdict(set))
    tree = tickets.load_tree(q)
    by_key = {t.key: t for t in tree.tickets}
    all_chains = tickets.chains(q, tree)
    uncertain: dict[str, str] = {}  # container folder -> why the IDs its epic claims are unknown
    for chain in all_chains:
        ticket = by_key[chain.key]
        label = chain.ticket + (" (planned)" if ticket.planned else "")
        if ticket.leaf and chain.state == "local":
            uncertain.setdefault(ticket.container, UNMAPPED_LEAF)
        elif ticket.leaf and chain.state != "resolved":
            uncertain[ticket.container] = BROKEN_LEAF  # a broken chain outranks an unmapped local ID
        if chain.state in tickets.REACHED and chain.target:
            evidence[_edge_key(chain)]["declared" if ticket.leaf else "partial"].add(label if ticket.leaf else f"epic {label}")
        elif chain.target:
            evidence[_edge_key(chain)]["unknown"].add(f"{label}: {chain.state}")
    # An epic that claims an ID while one of its leaf chains does not reach a parent ID makes the ID unknown, never missing.
    for chain in all_chains:
        ticket = by_key[chain.key]
        reason = None if ticket.leaf else uncertain.get(ticket.epic_folder)
        key = _edge_key(chain) if chain.target else chain.covered_id
        if reason and not evidence[key].get("declared"):
            evidence[key]["unknown"].add(f"epic {ticket.ref} has {reason}")
    return evidence


def _edge_key(chain: tickets.Chain):
    """A document-scoped target is keyed by its defining document too, so CAP-1 of one spec never declares another's."""
    return (chain.target_path, chain.target) if chain.target_path else chain.target


def covers(q: Queries) -> dict:
    tree = tickets.load_tree(q)
    all_chains = tickets.chains(q, tree)
    live = [t for t in tree.tickets if not t.dropped]
    by_key = {t.key: t for t in tree.tickets}
    problems = [{"ticket": c.ticket, "covers": c.covered_id, "state": c.state, "detail": c.detail,
                 **dict(zip(("path", "line"), tickets.covers_location(q, by_key[c.key])))}
                for c in all_chains if c.state not in tickets.REACHED]
    unchecked = _no_specs_of_record(q)
    if unchecked and all_chains:  # every chain would end "not defined"; that says nothing about the tickets
        problems = [p for p in problems if p["state"] not in UNDEFINED_STATES]
        problems.append({"ticket": None, "covers": None, "state": "scope-incomplete", "detail": unchecked})
    drift = []
    for ticket in live:
        if ticket.file is not None and ticket.file_covers is not None and sorted(ticket.file_covers) != sorted(ticket.covers):
            drift.append({"ticket": ticket.ref, "file": ticket.file, "file_covers": ticket.file_covers, "entry_covers": ticket.covers})
    for code, path, line, detail in tree.problems:
        problems.append({"ticket": None, "covers": None, "state": code, "detail": f"{path}:{line} {detail}", "path": path, "line": line})
    local = [{"ticket": c.ticket, "covers": c.covered_id, "detail": c.detail} for c in all_chains if c.state == "local"]
    return {"tickets": len(tree.tickets), "chains": len(all_chains), "problems": problems, "drift": drift,
            "planned": [t.ref for t in live if t.planned], "dropped": [t.ref for t in tree.tickets if t.dropped], "local": local,
            "note": None if tree.tickets else "no ticket tree in the indexed scope (not a defect)"}


def _no_specs_of_record(q: Queries) -> str | None:
    """Why no cover can reach a definition: no file in the indexed scope is a spec of record."""
    if any(f["role"] in RECORD_ROLES for f in q.files.values()):
        return None
    return q.scope_complete(("record",))


def covers_text(report: dict, generation: str) -> str:
    out = [f"covers: {report['tickets']} ticket(s), {report['chains']} chain(s), {len(report['problems'])} problem(s), {len(report['drift'])} drifted file(s)"]
    if report["note"]:
        out.append(f"note: {report['note']}")
    for p in report["problems"]:
        subject = f"ticket {p['ticket']} covers {p['covers']} — " if p["ticket"] else ""
        out.append(f" {p['state']}: {subject}{p['detail']}")
    for d in report["drift"]:
        out.append(f" drift: ticket {d['ticket']} file {d['file']} covers {d['file_covers']} vs tickets.toml {d['entry_covers']} (the file is the truth)")
    for item in report["local"]:
        out.append(f" local id, parent map not checked (not a defect): ticket {item['ticket']} covers {item['covers']} — {item['detail']}")
    if report["planned"]:
        out.append(f" planned (no file yet, not a defect): {', '.join(report['planned'])}")
    if report["dropped"]:
        out.append(f" dropped (kept as a record, not coverage): {', '.join(report['dropped'])}")
    out.append(f"generation {generation}")
    return "\n".join(out)


def coverage_text(report: dict, generation: str) -> str:
    counts = ", ".join(f"{k} {v}" for k, v in sorted(report["counts"].items()))
    out = [f"coverage by {report['by']} of {', '.join(report['families'])}: {counts or 'empty population'} ({report['scope']})"]
    for row in report["rows"]:
        detail = row["declared"] or row["unknown"] or row["partial"]
        label = f"{row['id']}{SCOPE_MARK}{row['path']}" if "path" in row else row["id"]
        out.append(f" {label:8} {row['state']:9} {', '.join(detail)}")
    out.append(f"generation {generation}")
    return "\n".join(out)
