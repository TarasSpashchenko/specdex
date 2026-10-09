"""Whole-corpus derivation: roles, effective definitions and citation resolution.

An ID's scope is its namespace owner. A citation resolves only when exactly one
effective definition answers it; several candidates give "ambiguous", none gives
"unresolved" (or "out-of-bounds" for a positional ID whose parent exists).
Equal content hashes never merge two documents.
"""
from __future__ import annotations

import json
import posixpath
import re
import sqlite3
from collections import defaultdict

from .config import Config, glob_to_regex

RECORD_LIKE = ("record", "ambiguous")
SCOPED_KINDS = ("rationale", "ticket")   # current only inside the active initiative (backlog tickets excepted)
LOCAL_MARKDOWN_LINK = re.compile(r"\]\((?:\./)?([^)/#\s]+\.md)(?:#[^)]*)?\)")


def derive(conn: sqlite3.Connection, config: Config, skipped_sources: list[tuple[str, str]] = ()) -> None:
    conn.execute("DELETE FROM defs")
    conn.execute("DELETE FROM gdiag")
    conn.execute("DELETE FROM occ WHERE derived=1")
    files = {row["path"]: dict(row) for row in conn.execute(
        "SELECT path, sha256, identity, is_link, artifact, kind, scope_kind, extracted, frontmatter FROM files")}
    diags: list[tuple[str, str, str, int, str]] = list(config.diagnostics)
    roles, companion_of = _assign_roles(conn, config, files, diags)
    _canonicalize(conn, config, files, roles)
    _write_roles(conn, config, files, roles, companion_of)
    _layout_and_copies(config, files, diags)
    _sharded_documents(conn, files, diags)
    _effective_definitions(conn, config, files, roles, diags)
    _bare_tokens(conn, config)
    _resolve_occurrences(conn, config)
    diags += [("source-skipped", "high", path, 0, why) for path, why in skipped_sources]
    conn.executemany("INSERT INTO gdiag(code, severity, path, line, detail) VALUES(?,?,?,?,?)", diags)


# -- roles ------------------------------------------------------------------------------
def _assign_roles(conn, config: Config, files: dict, diags: list) -> tuple[dict[str, str], dict[str, str]]:
    roles: dict[str, str] = {}
    owners = [p for p, f in files.items() if f["extracted"] and f["kind"] == "owner"]
    for path in config.records:
        if path not in files:
            diags.append(("missing-record", "high", path, 0, "the records setting names a file that does not exist"))
    listed = {p for p in config.records if p in files}
    decided = {files[p]["artifact"] for p in listed}  # the records setting decides the types it names
    for path in owners:
        if files[path]["artifact"] in decided:
            roles[path] = "record" if path in listed else "noncurrent"
    candidates = [p for p in owners if p not in roles]
    if config.current_scope is not None:  # the active initiative decides; owners elsewhere are not current
        roles.update({p: "noncurrent" for p in candidates if not _in_scope(config, p)})
        candidates = [p for p in candidates if _in_scope(config, p)]
    by_type: dict[str, list[str]] = defaultdict(list)
    for path in candidates:
        by_type[files[path]["artifact"]].append(path)
    for artifact, paths in by_type.items():
        if len(paths) == 1 or all(files[p]["scope_kind"] == "document" for p in paths):
            roles.update({p: "record" for p in paths})  # document-scoped owners (specs, spines) stand side by side
        else:
            for path in paths:
                roles[path] = "ambiguous"
            diags.append(("ambiguous-current", "high", ", ".join(sorted(paths)), 0,
                          f"{len(paths)} candidate {artifact} documents and no record selection; their IDs resolve to 'ambiguous'"))
    companion_of: dict[str, str] = {}
    for row in conn.execute("SELECT path, value, line FROM companions"):
        if roles.get(row["path"]) not in RECORD_LIKE:
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(row["path"]), row["value"]))
        if target in files:
            roles[target] = roles[row["path"]]
            companion_of[target] = row["path"]
        else:
            diags.append(("missing-companion", "high", row["path"], row["line"], f"required companion {row['value']} not found"))
    for path, info in files.items():
        if path in roles or not info["extracted"]:
            continue
        roles[path] = _supporting_role(config, path, info["kind"])
    return roles, companion_of


def _supporting_role(config: Config, path: str, kind: str) -> str:
    """Memlogs and tickets keep their kind; otherwise the project's role settings outrank the profile's
    rationale and trail defaults. Profile rationale and tickets of another initiative are not current."""
    if kind not in ("memlog", "ticket"):
        for rule in config.roles:
            if rule.regex.match(path):
                return rule.role
    if kind in SCOPED_KINDS and not _in_scope(config, path) and not (kind == "ticket" and _in_backlog(config, path)):
        return "noncurrent"
    return kind if kind in ("rationale", "trail", "memlog", "ticket") else "unverified"


def _in_scope(config: Config, path: str) -> bool:
    return config.current_scope is None or path.startswith(config.current_scope + "/")


def _in_backlog(config: Config, path: str) -> bool:
    return bool(config.backlog) and glob_to_regex(config.backlog + "/**").match(path) is not None


def _canonicalize(conn, config: Config, files: dict, roles: dict) -> None:
    """Aliases (symlinks, equal declared replicas) take their canonical copy's role."""
    by_identity = {f["identity"]: p for p, f in files.items() if f["extracted"]}
    replica_primary = {member: group[0] for group in config.replicas for member in group[1:]}
    for path, info in files.items():
        if info["extracted"]:
            continue
        canonical = replica_primary.get(path) or by_identity.get(info["identity"])
        info["canonical"] = canonical
        roles[path] = roles.get(canonical, "unverified") if canonical else "unverified"


def _write_roles(conn, config: Config, files: dict, roles: dict, companion_of: dict) -> None:
    superseded = {s.path: s for s in config.superseded}
    rows = []
    for path, info in files.items():
        entry = superseded.get(path)
        note = None
        if entry:
            note = f"superseded by {entry.by}" + (f" except {', '.join(entry.except_sections)}" if entry.except_sections else "")
        rows.append((roles.get(path, "unverified"), info.get("canonical"), companion_of.get(path), entry.by if entry else None, note, path))
    conn.executemany("UPDATE files SET role=?, canonical=?, companion_of=?, superseded_by=?, authority_note=? WHERE path=?", rows)


def _layout_and_copies(config: Config, files: dict, diags: list) -> None:
    for probe in config.layout_unsupported:
        regex = glob_to_regex(probe["glob"])
        hits = sorted(p for p in files if regex.match(p))
        if hits:
            diags.append(("unsupported-layout", "high", hits[0], 0, f"{probe['reason']}: {len(hits)} file(s); not indexed by this profile's rules"))
    by_sha: dict[str, list[str]] = defaultdict(list)
    for path, info in files.items():
        if info["extracted"]:
            by_sha[info["sha256"]].append(path)
    for paths in by_sha.values():
        if len(paths) > 1:
            diags.append(("copy-candidate", "info", ", ".join(sorted(paths)), 0,
                          "byte-identical documents kept distinct (no ownership evidence); declare replicas in the project settings to merge"))
    primary_sha = {}
    for group in config.replicas:
        if group[0] in files:
            primary_sha[group[0]] = files[group[0]]["sha256"]
            for member in group[1:]:
                if member not in files:
                    diags.append(("replica-missing", "high", member, 0, f"declared replica of {group[0]} not found"))
                elif files[member]["sha256"] != primary_sha[group[0]]:
                    diags.append(("replica-drift", "high", member, 0, f"declared replica of {group[0]} differs from it"))


def _sharded_documents(conn, files: dict, diags: list) -> None:
    """The v6→v7 migration keeps a sharded document's sections beside its old index, which becomes the main file.
    A main owner file linking to sibling files that no rule indexes is that shape: its IDs would be silently lost."""
    for path, info in files.items():
        folder = posixpath.dirname(path)
        if info["kind"] != "owner" or posixpath.splitext(posixpath.basename(path))[0] != posixpath.basename(folder):
            continue
        text = conn.execute("SELECT text FROM files WHERE path=?", (path,)).fetchone()["text"] or ""
        unread = sorted({f"{folder}/{name}" for name in LOCAL_MARKDOWN_LINK.findall(text)}
                        & {p for p, f in files.items() if f["artifact"] == "unknown"})
        if unread:
            diags.append(("unsupported-layout", "high", path, 0, f"sharded document: {len(unread)} linked section file(s) beside it "
                          f"({', '.join(posixpath.basename(p) for p in unread)}) are not indexed by this profile's rules"))


# -- definitions ----------------------------------------------------------------------------
def _effective_definitions(conn, config: Config, files: dict, roles: dict, diags: list) -> None:
    candidates = [dict(r) for r in conn.execute("SELECT c.*, s.temporal, s.disposition FROM cand c JOIN spans s ON s.sid=c.sid")]
    owned = [c for c in candidates if c["role"] == "definition" and roles.get(c["path"]) in RECORD_LIKE]
    rank: dict[int, int] = {}
    for c in owned:
        family = config.families.get(c["family"])
        artifact = files[c["path"]]["artifact"]
        rank[c["cid"]] = family.owners.index(artifact) if family and artifact in family.owners else 99
    best: dict[str, int] = {}
    for c in owned:
        if c["shape"] != "positional":
            best[c["id"]] = min(best.get(c["id"], 99), rank[c["cid"]])
    demoted_parents = {(c["path"], c["id"]) for c in owned if c["shape"] != "positional" and rank[c["cid"]] > best[c["id"]]}
    rows = []
    for c in owned:
        family = config.families.get(c["family"])
        scope = "project" if not family or family.scope == "project" else c["path"]
        if c["shape"] == "positional":
            demoted = (c["path"], c["parent_id"]) in demoted_parents
        else:
            demoted = rank[c["cid"]] > best[c["id"]]
        rows.append((c["id"], c["family"], scope, c["path"], c["line"], c["sid"], c["shape"],
                     _effective(c, demoted), c["parent_id"], c["ordinal"]))
    for c in candidates:
        if c["role"] == "elaboration" and roles.get(c["path"]) in RECORD_LIKE:
            rows.append((c["id"], c["family"], "project", c["path"], c["line"], c["sid"], c["shape"], "elaboration", None, None))
    unique = list(dict.fromkeys(rows))
    conn.executemany("INSERT INTO defs(id, family, scope, path, line, sid, shape, effective, parent_id, ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", unique)
    seen: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for ident, _family, scope, path, line, _sid, shape, effective, _p, _o in unique:
        if effective == "definition" and shape != "positional":
            seen[(ident, scope)].append((path, line))
    for (ident, scope), places in seen.items():
        if len(places) > 1:
            where = "; ".join(f"{p}:{l}" for p, l in places)
            for path, line in places:
                diags.append(("duplicate-definition", "high", path, line, f"{ident} is defined {len(places)} times in scope {scope}: {where}"))


def _effective(candidate: dict, demoted: bool) -> str:
    """A definition kept only as history (a retired or declined section) no longer answers current citations.
    A change-request row with a recorded decision still defines its ID: the record is history, the ID is not."""
    if candidate["temporal"] == "historical" and not candidate["disposition"]:
        return "historical"
    return "elaboration" if demoted else "definition"


def _bare_tokens(conn, config: Config) -> None:
    if not config.token_bare_backtick:
        return
    leaves: dict[str, list[str]] = defaultdict(list)
    for row in conn.execute("SELECT id FROM defs WHERE family='TOKEN' AND effective='definition'"):
        leaves[row["id"].rsplit(".", 1)[-1]].append(row["id"])
    rows, elaborations = [], []
    for row in conn.execute("SELECT b.path, b.line, b.col, b.word, b.sid, s.kind, f.artifact, f.text FROM backtick b "
                            "JOIN spans s ON s.sid=b.sid JOIN files f ON f.path=b.path"):
        targets = leaves.get(row["word"], [])
        if len(targets) != 1:
            continue
        kind = "mentions"
        if row["kind"] == "row" and row["artifact"] == "ux-design" and _in_first_cell(row["text"], row["line"], row["col"]):
            kind = "elaborates"
            elaborations.append((targets[0], "TOKEN", "project", row["path"], row["line"], row["sid"], "row-token", "elaboration", None, None))
        rows.append((row["path"], row["line"], row["col"], "TOKEN", targets[0], f"`{row['word']}`", 0, row["sid"], kind, None, "bare-backtick", 1))
    conn.executemany("INSERT INTO occ(path, line, col, family, id, raw, via_range, sid, kind, src_id, rule, derived) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.executemany("INSERT INTO defs(id, family, scope, path, line, sid, shape, effective, parent_id, ordinal) VALUES(?,?,?,?,?,?,?,?,?,?)", elaborations)


def _in_first_cell(text: str, line: int, col: int) -> bool:
    row = text.split("\n")[line - 1]
    first_pipe = row.find("|")
    second_pipe = row.find("|", first_pipe + 1)
    return first_pipe <= col < (second_pipe if second_pipe > 0 else len(row))


# -- citations --------------------------------------------------------------------------------
def _resolve_occurrences(conn, config: Config) -> None:
    by_id: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT d.did, d.id, d.family, d.scope, d.path, f.role FROM defs d JOIN files f ON f.path=d.path "
                            "WHERE d.effective='definition'"):
        by_id[row["id"]].append(row)
    defined = set(by_id)
    retired = {row["id"] for row in conn.execute("SELECT DISTINCT id FROM defs WHERE effective='historical'")}
    updates = []
    for occ in conn.execute("SELECT oid, path, id, family, rule FROM occ"):
        if occ["family"] == "SCOPE":
            updates.append((None, "textual", occ["oid"]))
            continue
        target, status = _resolve_one(config, occ, by_id.get(occ["id"], []), defined, retired)
        updates.append((target, status, occ["oid"]))
    conn.executemany("UPDATE occ SET target=?, status=? WHERE oid=?", updates)


def _resolve_one(config: Config, occ, candidates: list, defined: set[str], retired: set[str]) -> tuple[int | None, str]:
    family = config.families.get(occ["family"])
    if family and family.scope == "document" and len(candidates) > 1:
        folder = posixpath.dirname(occ["path"])
        if occ["rule"] == "inherited":
            narrowed = [c for c in candidates if c["path"] != occ["path"]]
        else:
            narrowed = [c for c in candidates if posixpath.dirname(c["path"]) == folder]
        candidates = narrowed or candidates
    if len(candidates) == 1 and candidates[0]["role"] != "ambiguous":
        return candidates[0]["did"], "resolved"
    if candidates:
        return None, "ambiguous"
    if "." in occ["id"] and occ["family"] != "TOKEN" and occ["id"].rsplit(".", 1)[0] in defined:
        return None, "out-of-bounds"
    return None, "historical" if occ["id"] in retired else "unresolved"


def frontmatter(row: sqlite3.Row) -> dict:
    return json.loads(row["frontmatter"]) if row["frontmatter"] else {}
