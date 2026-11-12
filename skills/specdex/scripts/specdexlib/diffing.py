"""What changed between two generations: IDs, positional lists and sections.

Positional fingerprints catch the quiet failure of FR-n.k citations: inserting
or removing a bullet mid-list makes later citations point at different text
under the same ID.
"""
from __future__ import annotations

import difflib
import posixpath
from collections import defaultdict

from . import render
from .index import open_index
from .queries import Queries
from .sources import SourceError, run_git

WORKTREE = "WORKTREE"
SCOPE_MARK = " @ "  # "AD-1 @ <folder>": a document-scoped ID in diff output
HISTORY_LIMIT = 40  # one git pickaxe run per added ID; IDs beyond this are reported as unchecked
ID_END = r"([^[:alnum:]_.-]|[.][^0-9]|[.]?$)"  # POSIX ERE: not followed by more ID characters or ".digit"


def add_commands(sub) -> None:
    p = sub.add_parser("diff", help="IDs, positional lists and sections changed between two revisions")
    p.add_argument("old", help="git revision")
    p.add_argument("new", nargs="?", default=WORKTREE, help=f"git revision or {WORKTREE} (default)")


def run(args, q: Queries) -> int:
    from .cli import load_config  # each side keeps the profile its own layout selects

    def side(revision: str | None) -> Queries:
        return Queries(open_index(load_config(q.index.config.project_root, args.profile, args.overlay, revision), revision, args.db))

    old = side(args.old)
    new = q if args.new == WORKTREE and q.index.mode == "worktree" else side(None if args.new == WORKTREE else args.new)
    report = diff(old, new)
    report["history"] = _history(q.index.config.project_root, args.old, report["added"])
    print(render.to_json(report) if args.json else diff_text(report))
    return 0


def _definitions(q: Queries) -> dict[str, dict]:
    """Definitions keyed by ID, or "ID @ folder" for document-scoped families, so two spines' AD-1 stay apart.
    "folder" is the scope's full folder: "folder" names a namespace, and basenames can repeat."""
    rows = q.conn.execute(
        "SELECT d.id, d.family, d.scope, d.path, d.shape, d.parent_id, d.ordinal, s.start, s.end FROM defs d JOIN spans s ON s.sid=d.sid "
        "JOIN files f ON f.path=d.path WHERE d.effective='definition' AND f.role IN ('record','ambiguous')").fetchall()
    result: dict[str, dict] = {}
    for r in sorted(rows, key=lambda r: (r["path"], r["start"])):
        text = " ".join(q.text(r["path"], r["start"], r["end"]).split())
        scope = "" if r["scope"] == "project" else f"{SCOPE_MARK}{posixpath.dirname(r['scope'])}"
        parent = r["parent_id"] and f"{r['parent_id']}{scope}"
        key = f"{r['id']}{scope}"
        if key in result:  # an ID defined twice (lint reports the duplicate): a change to either definition is a change
            result[key]["text"] += " ¶ " + text
            continue
        result[key] = {"id": r["id"], "path": r["path"], "start": r["start"], "end": r["end"], "text": text,
                                       "shape": r["shape"], "parent": parent, "ordinal": r["ordinal"]}
    return result


def _citations(q: Queries, key: str) -> list[str]:
    """Lines citing a diff key; a scoped key ("AD-1 @ folder") counts only citations inside that folder or resolved to it."""
    ident, _, folder = key.partition(SCOPE_MARK)
    rows = q.conn.execute(
        "SELECT DISTINCT o.path, o.line, d.path AS target_path FROM occ o JOIN files f ON f.path=o.path LEFT JOIN defs d ON d.did=o.target "
        "WHERE o.id=? AND o.kind!='defines' AND f.role IN ('record','ambiguous') ORDER BY o.path, o.line", (ident,)).fetchall()
    def in_scope(row) -> bool:
        return not folder or posixpath.dirname(row["target_path"] or row["path"]) == folder
    return list(dict.fromkeys(f"{r['path']}:{r['line']}" for r in rows if in_scope(r)))


def diff(old: Queries, new: Queries) -> dict:
    a, b = _definitions(old), _definitions(new)
    plain_a = {k: v for k, v in a.items() if v["shape"] != "positional"}
    plain_b = {k: v for k, v in b.items() if v["shape"] != "positional"}
    added = sorted(set(plain_b) - set(plain_a))
    removed = sorted(set(plain_a) - set(plain_b))
    changed = sorted(k for k in set(plain_a) & set(plain_b) if plain_a[k]["text"] != plain_b[k]["text"])
    report = {
        "old": old.index.mode, "new": new.index.mode,
        "added": [{"id": k, "at": f"{plain_b[k]['path']}:{plain_b[k]['start']}"} for k in added],
        "removed": [{"id": k, "was": f"{plain_a[k]['path']}:{plain_a[k]['start']}", "still_cited": _citations(new, k)} for k in removed],
        "changed": [{"id": k, "old": f"{plain_a[k]['path']}:{plain_a[k]['start']}-{plain_a[k]['end']}",
                     "new": f"{plain_b[k]['path']}:{plain_b[k]['start']}-{plain_b[k]['end']}"} for k in changed],
        "positional": _positional(a, b, new),
        "sections": _sections(old, new),
    }
    return report


def _history(root, revision: str, added: list[dict]) -> dict:
    """An added ID that the history of its file already contains may be a reused retired ID: report the newest
    commit that changed its occurrence count. Evidence for the owning workflow, never proof either way."""
    checked = added[:HISTORY_LIMIT]
    seen = []
    for item in checked:
        path = item["at"].rpartition(":")[0]
        ident = item["id"].split(SCOPE_MARK)[0]
        pattern = f"(^|[^[:alnum:]_-]){ident.replace('.', '[.]')}{ID_END}"
        try:
            commit = run_git(root, "log", "-1", "--format=%h %as", "--pickaxe-regex", f"-S{pattern}", revision, "--", path).decode().strip()
        except SourceError as error:
            return {"checked": 0, "unchecked": len(added), "seen": [], "error": str(error)}
        if commit:
            item["seen_in_history"] = commit
            seen.append(item["id"])
    return {"checked": len(checked), "unchecked": len(added) - len(checked), "seen": seen}


def _children(defs: dict[str, dict]) -> dict[str, list[str]]:
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for ident, info in defs.items():
        if info["shape"] == "positional":
            groups[info["parent"]].append((info["ordinal"], info["text"]))
    return {parent: [text for _, text in sorted(items)] for parent, items in groups.items()}


def _positional(a: dict, b: dict, new: Queries) -> list[dict]:
    old_lists, new_lists = _children(a), _children(b)
    findings = []
    for parent in sorted(set(old_lists) | set(new_lists)):
        before, after = old_lists.get(parent, []), new_lists.get(parent, [])
        if before == after:
            continue
        ops = [op for op in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes() if op[0] != "equal"]
        kind = _positional_kind(ops, len(before))
        if kind == "edited in place":
            positions = sorted({k + 1 for tag, i1, i2, _, _ in ops for k in range(i1, i2)})
        elif kind == "appended":
            positions = []
        else:  # shifted: every position from the first insertion or deletion onwards may now name other text
            first = min(i1 for tag, i1, i2, _, _ in ops) + 1
            positions = list(range(first, max(len(before), len(after)) + 1))
        items = []
        for k in positions:
            old_text = before[k - 1] if k <= len(before) else None
            new_text = after[k - 1] if k <= len(after) else None
            if old_text != new_text:
                bare, _, folder = parent.partition(SCOPE_MARK)
                ident = f"{bare}.{k}" + (f"{SCOPE_MARK}{folder}" if folder else "")
                items.append({"id": ident, "old": (old_text or "—")[:90], "new": (new_text or "—")[:90], "cited_at": _citations(new, ident)})
        findings.append({"parent": parent, "old_count": len(before), "new_count": len(after), "kind": kind, "items": items})
    return findings


def _positional_kind(ops: list, old_count: int) -> str:
    if all(tag == "insert" and i1 == old_count for tag, i1, _, _, _ in ops):
        return "appended"
    if all(tag == "replace" and (i2 - i1) == (j2 - j1) for tag, i1, i2, j1, j2 in ops):
        return "edited in place"
    return "shifted (later positional citations may now name different text)"


def _sections(old: Queries, new: Queries) -> list[dict]:
    def own_texts(q: Queries) -> dict[tuple[str, str], str]:
        result = {}
        for row in q.conn.execute("SELECT c.path, c.hpath, c.body FROM chunks c JOIN files f ON f.path=c.path WHERE f.role IN ('record','ambiguous')"):
            key = (row["path"], row["hpath"])
            result[key] = result.get(key, "") + "\n" + row["body"]
        return result
    before, after = own_texts(old), own_texts(new)
    changes = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            state = "added" if key not in before else "removed" if key not in after else "changed"
            changes.append({"path": key[0], "section": key[1], "state": state})
    return changes


def diff_text(report: dict) -> str:
    out = [f"diff {report['old']} → {report['new']}"]
    out.append(f" IDs added {len(report['added'])}, removed {len(report['removed'])}, changed {len(report['changed'])}")
    for item in report["added"]:
        history = f" — already in this file's history (last changed in {item['seen_in_history']}): check it is not a reused retired ID" \
            if "seen_in_history" in item else ""
        out.append(f"  + {item['id']} at {item['at']}{history}")
    if report.get("history", {}).get("unchecked"):
        out.append(f"  note: history not checked for {report['history']['unchecked']} added ID(s) beyond the first {HISTORY_LIMIT}")
    for item in report["removed"]:
        cited = f"; still cited at {', '.join(item['still_cited'])}" if item["still_cited"] else ""
        out.append(f"  - {item['id']} (was {item['was']}){cited}")
    by_file: dict[str, list[str]] = defaultdict(list)
    for item in report["changed"]:
        old_path, _, old_lines = item["old"].rpartition(":")
        new_path, _, new_lines = item["new"].rpartition(":")
        moved = "" if old_path == new_path else f" (moved from {old_path})"
        by_file[new_path].append(f"{item['id']} {old_lines}→{new_lines}{moved}")
    for path, entries in sorted(by_file.items()):
        out.append(f"  ~ {path}: " + "; ".join(entries))
    for p in report["positional"]:
        out.append(f" positional {p['parent']}: {p['old_count']} → {p['new_count']} item(s), {p['kind']}")
        for item in p["items"]:
            cited = f" — cited at {', '.join(item['cited_at'])}" if item["cited_at"] else ""
            out.append(f"   {item['id']}: was “{item['old']}” now “{item['new']}”{cited}")
    out.append(f" sections changed {len(report['sections'])}")
    for s in report["sections"][:60]:
        out.append(f"  {s['state']:7} {s['section']}")
    if len(report["sections"]) > 60:
        out.append(f"  … {len(report['sections']) - 60} more")
    return "\n".join(out)
