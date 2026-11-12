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

from . import extract, layout, store
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
    parents = layout.child_parents({row["path"]: row["text"] or "" for row in conn.execute(
        "SELECT path, text FROM files WHERE artifact='tickets-toml'")})
    scopes = current_folders(config, parents)
    store.set_meta(conn, "current_folders", json.dumps(scopes))
    shards = _shards(files)
    roles, companion_of = _assign_roles(conn, config, files, scopes, shards, diags)
    _canonicalize(conn, config, files, roles)
    _write_roles(conn, config, files, roles, companion_of, shards)
    _layout_and_copies(config, files, diags)
    _sharded_documents(conn, files, diags)
    _effective_definitions(conn, config, files, roles, shards, scopes, diags)
    _bare_tokens(conn, config)
    containers = layout.Containers(((p, f["artifact"]) for p, f in files.items() if f["extracted"]), parents)
    _resolve_occurrences(conn, config, containers)
    diags += [("source-skipped", "high", path, 0, why) for path, why in skipped_sources]
    conn.executemany("INSERT INTO gdiag(code, severity, path, line, detail) VALUES(?,?,?,?,?)", diags)


# -- roles ------------------------------------------------------------------------------
def current_folders(config: Config, parents: dict[str, str]) -> list[str] | None:
    """The active initiative and the parent initiatives above it; None when no initiative is active."""
    if config.current_scope is None:
        return None
    return [config.current_scope] + layout.ancestors(config.current_scope, parents)


def _assign_roles(conn, config: Config, files: dict, scopes: list[str] | None, shards: dict[str, str],
                  diags: list) -> tuple[dict[str, str], dict[str, str]]:
    roles: dict[str, str] = {}
    owners = [p for p, f in files.items() if f["extracted"] and f["kind"] == "owner" and p not in shards]
    for path in config.records:
        if path not in files:
            diags.append(("missing-record", "high", path, 0, "the records setting names a file that does not exist"))
    listed = {p for p in config.records if p in files}
    # The records setting decides the types it names: inside the active initiative and its parents, in the container of
    # each file it names (an epic's own PRD stays its record); a file named from elsewhere decides its type everywhere.
    everywhere = {files[p]["artifact"] for p in listed if not _in_scope(scopes, p) or scopes is None}
    in_container = {(files[p]["artifact"], _altitude(p)) for p in listed if scopes is not None and _in_scope(scopes, p)}
    for path in owners:
        if files[path]["artifact"] in everywhere or (files[path]["artifact"], _altitude(path)) in in_container:
            roles[path] = "record" if path in listed else "noncurrent"
    candidates = [p for p in owners if p not in roles]
    if scopes is not None:  # the active initiative and its parents decide; owners elsewhere are not current
        roles.update({p: "noncurrent" for p in candidates if not _in_scope(scopes, p)})
        candidates = [p for p in candidates if _in_scope(scopes, p)]
    # Under an active initiative each container (the initiative, a parent initiative, an epic) has its own record of
    # each type; with none, one document per type is the record.
    groups: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for path in candidates:
        groups[(files[path]["artifact"], _altitude(path) if scopes is not None else None)].append(path)
    for (artifact, _altitude_folder), paths in groups.items():
        if len(paths) == 1 or all(files[p]["scope_kind"] == "document" for p in paths):
            roles.update({p: "record" for p in paths})  # document-scoped owners (specs, spines) stand side by side
        else:
            for path in paths:
                roles[path] = "ambiguous"
            hint = f"; {config.ambiguous_hint}" if config.ambiguous_hint else ""
            diags.append(("ambiguous-current", "high", ", ".join(sorted(paths)), 0,
                          f"{len(paths)} candidate {artifact} documents and no record selection; their IDs resolve to 'ambiguous'{hint}"))
    companion_of: dict[str, str] = {}
    for row in conn.execute("SELECT path, value, line FROM companions"):
        if roles.get(row["path"]) not in RECORD_LIKE:
            continue
        target = _companion_path(row["path"], row["value"], files)
        if target in files:
            roles[target] = roles[row["path"]]
            companion_of[target] = row["path"]
        else:
            diags.append(("missing-companion", "high", row["path"], row["line"], f"required companion {row['value']} not found"))
    for path, info in files.items():
        if path in roles or path in shards or not info["extracted"]:
            continue
        roles[path] = _supporting_role(config, scopes, path, info["kind"])
    for shard, main in shards.items():  # a shard is part of its document
        roles[shard] = roles.get(main) or _supporting_role(config, scopes, shard, files[shard]["kind"])
    return roles, companion_of


def _shards(files: dict) -> dict[str, str]:
    """bmad-shard-pro shards and the main file each is part of."""
    shards = {}
    for path, info in files.items():
        main = extract.part_of(path, frontmatter(info)) if info["extracted"] else None
        if main in files and main != path:
            shards[path] = main
    return shards


def _altitude(path: str) -> str:
    """The container a planning document belongs to: the folder holding its run folder."""
    return posixpath.dirname(posixpath.dirname(path))


def _companion_path(owner: str, value: str, files: dict) -> str:
    """A companion is named from its owner's folder or, as BMad's ticket frontmatter names it, from the project root."""
    beside = posixpath.normpath(posixpath.join(posixpath.dirname(owner), value))
    return beside if beside in files or value.strip("/") not in files else value.strip("/")


def _supporting_role(config: Config, scopes: list[str] | None, path: str, kind: str) -> str:
    """Memlogs and tickets keep their kind; otherwise the project's role settings outrank the profile's
    rationale and trail defaults. Profile rationale and tickets of another initiative are not current."""
    if kind not in ("memlog", "ticket"):
        for rule in config.roles:
            if rule.regex.match(path):
                return rule.role
    if kind in SCOPED_KINDS and not _in_scope(scopes, path) and not (kind == "ticket" and _in_backlog(config, path)):
        return "noncurrent"
    return kind if kind in ("rationale", "trail", "memlog", "ticket") else "unverified"


def _in_scope(scopes: list[str] | None, path: str) -> bool:
    return scopes is None or any(path.startswith(folder + "/") for folder in scopes)


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


def _write_roles(conn, config: Config, files: dict, roles: dict, companion_of: dict, shards: dict[str, str]) -> None:
    superseded = {s.path: s for s in config.superseded}
    rows = []
    for path, info in files.items():
        entry = superseded.get(path)
        note = None
        if entry:
            note = f"superseded by {entry.by}" + (f" except {', '.join(entry.except_sections)}" if entry.except_sections else "")
        rows.append((roles.get(path, "unverified"), info.get("canonical"), companion_of.get(path), entry.by if entry else None, note,
                     shards.get(path), path))
    conn.executemany("UPDATE files SET role=?, canonical=?, companion_of=?, superseded_by=?, authority_note=?, part_of=? WHERE path=?", rows)


def _reading_order(conn, shards: dict[str, str]) -> dict[str, tuple]:
    """Where each sharded file sits in its document: its main file, then the shards in the order the main file's
    map links them (bmad-shard-pro's reading order)."""
    order: dict[str, tuple] = {}
    for main in set(shards.values()):
        text = conn.execute("SELECT text FROM files WHERE path=?", (main,)).fetchone()["text"] or ""
        linked = [posixpath.normpath(posixpath.join(posixpath.dirname(main), name)) for name in LOCAL_MARKDOWN_LINK.findall(text)]
        order[main] = (main, 0)
        for path in (p for p, m in shards.items() if m == main):
            order[path] = (main, 1 + (linked.index(path) if path in linked else len(linked)), path)
    return order


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
def _effective_definitions(conn, config: Config, files: dict, roles: dict, shards: dict[str, str], scopes: list[str] | None,
                           diags: list) -> None:
    candidates = _main_file_rules(conn, files, shards, [dict(r) for r in conn.execute(
        "SELECT c.*, s.temporal, s.disposition FROM cand c JOIN spans s ON s.sid=c.sid")])
    owned = _recited_tables(conn, [c for c in candidates if c["role"] == "definition" and _owns(config, files, roles, c)],
                            _reading_order(conn, shards), scopes)
    # The highest-priority owner type defines an ID; a lower one elaborates it. Owners compete within one scope:
    # a document-scoped ID (an epic's R1) is its own document's whatever another document says.
    rank: dict[int, int] = {}
    scope: dict[int, str] = {}
    for c in owned:
        family = config.families.get(c["family"])
        artifact = files[c["path"]]["artifact"]
        rank[c["cid"]] = family.owners.index(artifact) if family and artifact in family.owners else 99
        scope[c["cid"]] = "project" if not family or family.scope == "project" else c["path"]
    best: dict[tuple[str, str], int] = {}
    for c in owned:
        if c["shape"] != "positional":
            key = (c["id"], scope[c["cid"]])
            best[key] = min(best.get(key, 99), rank[c["cid"]])
    demoted_parents = {(c["path"], c["id"]) for c in owned
                       if c["shape"] != "positional" and rank[c["cid"]] > best[(c["id"], scope[c["cid"]])]}
    rows = []
    for c in owned:
        if c["shape"] == "positional":
            demoted = (c["path"], c["parent_id"]) in demoted_parents
        else:
            demoted = rank[c["cid"]] > best[(c["id"], scope[c["cid"]])]
        rows.append((c["id"], c["family"], scope[c["cid"]], c["path"], c["line"], c["sid"], c["shape"],
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


def _main_file_rules(conn, files: dict, shards: dict[str, str], candidates: list[dict]) -> list[dict]:
    """A shard was read with every rule set; it keeps the one its main file calls for (engine when the main file carries
    `template`), and a bold lead reading as a sentence only when no part of the document defines its ID otherwise. An ID
    only a dropped candidate found on a line is cited there, not defined."""
    def wanted(main: str) -> str:
        return extract.ENGINE if isinstance(frontmatter(files[main]).get("template"), str) else extract.LEGACY

    ruled = [c for c in candidates if c["path"] not in shards or c["documents"] in ("any", wanted(shards[c["path"]]))]
    document = {path: shards.get(path, path) for path in files}
    plain = {(document[c["path"]], c["id"]) for c in ruled if c["role"] == "definition" and not c["sentence"]}
    kept = [c for c in ruled if not (c["sentence"] and (document[c["path"]], c["id"]) in plain)]
    defining = {(c["path"], c["line"], c["id"]) for c in kept if c["path"] in shards}
    dropped = {(c["path"], c["line"], c["id"]) for c in candidates if c["path"] in shards} - defining
    conn.executemany("UPDATE occ SET kind='mentions' WHERE path=? AND line=? AND id=? AND kind='defines' AND derived=0", sorted(dropped))
    # The index keeps a shard's extraction while only its main file changes: a definition dropped before may be kept now.
    conn.executemany("UPDATE occ SET kind='defines' WHERE oid=(SELECT oid FROM occ WHERE path=? AND line=? AND id=? AND via_range=0 "
                     "AND derived=0 ORDER BY col LIMIT 1) AND kind='mentions'", sorted(defining))
    return kept


def _owns(config: Config, files: dict, roles: dict, candidate: dict) -> bool:
    """Specs of record define IDs; so does a current ticket for a family it owns (a container's R ids)."""
    role = roles.get(candidate["path"])
    if role in RECORD_LIKE:
        return True
    family = config.families.get(candidate["family"])
    return role == "ticket" and family is not None and files[candidate["path"]]["artifact"] in family.owners


def _recited_tables(conn, owned: list[dict], order: dict[str, tuple], scopes: list[str] | None) -> list[dict]:
    """check_ids.py reads a table most of whose IDs were defined before it as references (a traceability table, an
    epic PRD's table of its parent's IDs). Documents are read parents first (a parent initiative's, then the active
    one's, then an epic's), the way BMad checks a document together with its parent's, a sharded one in its map's
    order; rows of a re-citing table are mentions, not definitions."""
    tops = list(reversed(scopes or []))  # the topmost parent initiative first

    def position(c: dict) -> tuple:
        document, *place = order.get(c["path"], (c["path"],))
        altitude = next((rank for rank, folder in enumerate(tops) if document.startswith(folder + "/")), len(tops))
        return (altitude, document.count("/"), document, *place, c["line"])
    ordered = sorted(owned, key=position)
    tables: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for candidate in ordered:
        if candidate["grp"] is not None:
            tables[(candidate["path"], candidate["grp"])].append(candidate)
    known: set[str] = set()
    kept, seen = [], set()
    for candidate in ordered:
        key = (candidate["path"], candidate["grp"])
        if candidate["grp"] is None:
            known.add(candidate["id"])
            kept.append(candidate)
        elif key not in seen:
            seen.add(key)
            rows = tables[key]
            recited = 2 * sum(row["id"] in known for row in rows) > len(rows)
            conn.executemany("UPDATE occ SET kind=? WHERE path=? AND line=? AND id=? AND kind IN ('defines', 'mentions') AND derived=0",
                             [("mentions" if recited else "defines", row["path"], row["line"], row["id"]) for row in rows])
            if not recited:
                known.update(row["id"] for row in rows)
                kept += rows
    return kept


def _effective(candidate: dict, demoted: bool) -> str:
    """A definition kept only as history (a retired or declined section, an ID marked withdrawn) no longer answers
    current citations. A change-request row with a recorded decision still defines its ID: the record is history,
    the ID is not."""
    if candidate["withdrawn"] or (candidate["temporal"] == "historical" and not candidate["disposition"]):
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
def _resolve_occurrences(conn, config: Config, containers: layout.Containers) -> None:
    by_id: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT d.did, d.id, d.family, d.scope, d.path, f.role FROM defs d JOIN files f ON f.path=d.path "
                            "WHERE d.effective='definition'"):
        by_id[row["id"]].append(row)
    defined = set(by_id)
    retired = {row["id"] for row in conn.execute("SELECT DISTINCT id FROM defs WHERE effective='historical'")}
    updates = []
    for occ in conn.execute("SELECT oid, path, id, family, rule, kind FROM occ"):
        if occ["family"] == "SCOPE":
            updates.append((None, "textual", occ["oid"]))
            continue
        target, status = _resolve_one(config, containers, occ, by_id.get(occ["id"], []), defined, retired)
        updates.append((target, status, occ["oid"]))
    conn.executemany("UPDATE occ SET target=?, status=? WHERE oid=?", updates)


def _resolve_one(config: Config, containers: layout.Containers, occ, candidates: list, defined: set[str],
                 retired: set[str]) -> tuple[int | None, str]:
    family = config.families.get(occ["family"])
    if family and family.scope == "document" and candidates:
        candidates = _citing_document_decides(containers, family, occ, candidates)
    if len(candidates) == 1 and candidates[0]["role"] != "ambiguous":
        return candidates[0]["did"], "resolved"
    if candidates:
        return None, "ambiguous"
    if "." in occ["id"] and occ["family"] != "TOKEN" and occ["id"].rsplit(".", 1)[0] in defined:
        return None, "out-of-bounds"
    return None, "historical" if occ["id"] in retired else "unresolved"


def _citing_document_decides(containers: layout.Containers, family, occ, candidates: list) -> list:
    """The definitions of a document-scoped ID that a citation names. A ticket's R id is its container's: a story
    or spine cites its container's requirement, a container file (covers, `parent R3`) its parent's. Other families
    (AD) take the citing document's own folder, else the nearest container up the tree that defines the ID (an epic
    spine before its initiative's); an inherited invariant never names its own document."""
    if any(owner in layout.CONTAINER_TYPES for owner in family.owners):
        level = containers.of(occ["path"])
        if level is not None and occ["path"] == containers.file(level) and occ["kind"] != "defines":
            level = containers.parent(level)
        return [c for c in candidates if level is not None and c["path"] == containers.file(level)]
    if len(candidates) == 1:
        return candidates
    if occ["rule"] == "inherited":
        candidates = [c for c in candidates if c["path"] != occ["path"]] or candidates
    else:
        same_folder = [c for c in candidates if posixpath.dirname(c["path"]) == posixpath.dirname(occ["path"])]
        if same_folder:
            return same_folder
    level = containers.of(occ["path"])
    while level is not None:
        nearest = [c for c in candidates if containers.of(c["path"]) == level]
        if nearest:
            return nearest
        level = containers.parent(level)
    return candidates


def frontmatter(row: sqlite3.Row) -> dict:
    return json.loads(row["frontmatter"]) if row["frontmatter"] else {}
