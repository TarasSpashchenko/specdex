"""BMAD preview ticket tree adapter (read-only).

A container is a `<type>-<slug>/` folder with a same-named file and a
`tickets.toml`; initiatives list `[[epic]]`, epics list `[[entry]]`. Each
container's requirement source is, in order: its own `## Requirements` section,
a referenced numbered source (a `prd —` or `spec —` References line), or a
`spec-*/SPEC.md` in its folder. BMAD's tickets.py never validates `covers`;
this module does, without changing anything.
"""
from __future__ import annotations

import json
import posixpath
import re
import tomllib
from dataclasses import dataclass, field

from .queries import Queries

REQUIREMENT_LINE = re.compile(r"^\s*[-*]\s+(?:\*\*)?(?P<id>[A-Z][A-Za-z]*-?\d+(?:\.\d+)?)(?:\*\*)?(?:\s*\((?P<parent>[^)]*)\))?")
REFERENCE_LINE = re.compile(r"^\s*[-*]\s+(?P<type>[a-z][\w-]*)\s+—\s+(?P<location>[^,\s]+)")
NUMBERED_SOURCE_TYPES = ("prd", "spec")


@dataclass(slots=True)
class Ticket:
    ref: str                  # "<epic id>.<entry id>" or the epic id
    container: str            # folder of the owning container
    title: str
    covers: list[str]
    toml_path: str
    file: str | None = None   # pulled leaf file, which is the truth over tickets.toml content fields
    file_covers: list[str] | None = None
    status: str | None = None

    @property
    def planned(self) -> bool:
        """A leaf with neither a file nor a plan yet: expected work, not a defect."""
        return "." in self.ref and self.file is None and self.status is None


@dataclass(slots=True)
class Container:
    folder: str
    kind: str                 # initiative | epic
    file: str | None
    toml_path: str
    covers: list[str] = field(default_factory=list)
    requirements: dict[str, tuple[str | None, int]] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    parent: str | None = None
    epic_id: str | None = None


@dataclass(slots=True)
class Chain:
    ticket: str
    covered_id: str
    state: str                # resolved | unresolved | not-in-container-covers | upstream-unresolved
    target: str | None        # the population ID the chain reaches (e.g. FR-7)
    detail: str


@dataclass(slots=True)
class Tree:
    containers: dict[str, Container] = field(default_factory=dict)
    tickets: list[Ticket] = field(default_factory=list)
    problems: list[tuple[str, str, int, str]] = field(default_factory=list)  # code, path, line, detail


def load_tree(q: Queries) -> Tree:
    tree = Tree()
    tomls = sorted(p for p, f in q.files.items() if f["artifact"] == "tickets-toml")
    for path in tomls:
        try:
            data = tomllib.loads("\n".join(q.lines(path)))
        except tomllib.TOMLDecodeError as error:
            tree.problems.append(("ticket-toml-invalid", path, 0, str(error)))
            continue
        folder = posixpath.dirname(path)
        name = posixpath.basename(folder)
        kind = "initiative" if "epic" in data else "epic"
        file = f"{folder}/{name}.md"
        container = Container(folder, kind, file if file in q.files else None, path)
        if container.file:
            _read_container_file(q, container)
        tree.containers[folder] = container
        if kind == "initiative":
            for epic in data.get("epic", []):
                epic_folder = f"{folder}/{epic.get('slug', '')}"
                tree.tickets.append(Ticket(str(epic.get("id")), folder, epic.get("title", ""), list(epic.get("covers", [])), path))
                tree.containers.setdefault(epic_folder, Container(epic_folder, "epic", None, "", parent=folder))
                tree.containers[epic_folder].epic_id = str(epic.get("id"))
                tree.containers[epic_folder].parent = folder
    for folder, container in tree.containers.items():
        if container.kind != "epic" or not container.toml_path:
            continue
        data = tomllib.loads("\n".join(q.lines(container.toml_path)))
        parent = posixpath.dirname(folder)
        container.parent = container.parent or (parent if parent in tree.containers else None)
        leaves = _leaf_files(q, folder)
        for entry in data.get("entry", []):
            ident = str(entry.get("id"))
            ref = f"{container.epic_id}.{ident}" if container.epic_id else ident
            ticket = Ticket(ref, folder, entry.get("title", ""), list(entry.get("covers", [])), container.toml_path)
            leaf = leaves.get(ident)
            if leaf:
                ticket.file, ticket.file_covers = leaf
            ticket.status = _plan_status(q, folder, ident)
            tree.tickets.append(ticket)
    return tree


def _read_container_file(q: Queries, container: Container) -> None:
    row = q.conn.execute("SELECT frontmatter FROM files WHERE path=?", (container.file,)).fetchone()
    frontmatter = json.loads(row["frontmatter"]) if row and row["frontmatter"] else {}
    covers = frontmatter.get("covers")
    container.covers = list(covers) if isinstance(covers, list) else []
    lines = q.lines(container.file)
    section = None
    for number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section == "requirements":
            match = REQUIREMENT_LINE.match(line)
            if match:
                container.requirements[match.group("id")] = (match.group("parent").strip() if match.group("parent") else None, number)
        elif section == "references":
            match = REFERENCE_LINE.match(line)
            if match and match.group("type") in NUMBERED_SOURCE_TYPES:
                container.sources.append(match.group("location").strip("`"))


def _leaf_files(q: Queries, folder: str) -> dict[str, tuple[str, list[str]]]:
    leaves = {}
    for path, info in q.files.items():
        if info["artifact"] != "ticket-leaf" or posixpath.dirname(path) != folder:
            continue
        row = q.conn.execute("SELECT frontmatter FROM files WHERE path=?", (path,)).fetchone()
        frontmatter = json.loads(row["frontmatter"]) if row and row["frontmatter"] else {}
        if "id" in frontmatter:
            covers = frontmatter.get("covers")
            leaves[str(frontmatter["id"])] = (path, list(covers) if isinstance(covers, list) else [])
    return leaves


def _plan_status(q: Queries, folder: str, ident: str) -> str | None:
    for path, info in q.files.items():
        if info["artifact"] != "ticket-plan" or posixpath.dirname(path) != folder:
            continue
        row = q.conn.execute("SELECT frontmatter FROM files WHERE path=?", (path,)).fetchone()
        frontmatter = json.loads(row["frontmatter"]) if row and row["frontmatter"] else {}
        if str(frontmatter.get("ticket")) == ident:
            return frontmatter.get("status")
    return None


def chains(q: Queries, tree: Tree) -> list[Chain]:
    """Resolve every ticket's covers through its container's requirement source up to a defined ID."""
    result = []
    for ticket in tree.tickets:
        covers = ticket.file_covers if ticket.file is not None else ticket.covers
        container = tree.containers.get(ticket.container)  # epics resolve against their initiative, entries against their epic
        for covered in covers:
            result.append(_chain(q, tree, ticket.ref, covered, container))
    return result


def _chain(q: Queries, tree: Tree, ticket: str, covered: str, container: Container | None) -> Chain:
    if container is None:
        return Chain(ticket, covered, "unresolved", None, "no container")
    upstream = tree.containers.get(container.parent) if container.parent else None
    if covered in container.requirements:
        parent, line = container.requirements[covered]
        if parent is None:  # the line reuses a parent ID, or (platform baseline) cites only a source section
            target = _defined_upstream(q, tree, covered, upstream, container)
            if target and container.covers and covered not in container.covers:
                return Chain(ticket, covered, "not-in-container-covers", target, f"{container.file} does not list {covered} in covers")
            return _resolved(q, ticket, covered, target, f"{container.file}:{line}" + ("" if target else " (no parent id)"))
        if container.covers and parent not in container.covers:
            return Chain(ticket, covered, "not-in-container-covers", parent, f"{covered} maps to {parent}, which {container.file} does not list in covers")
        target = _defined_upstream(q, tree, parent, upstream, container)
        if target:
            return _resolved(q, ticket, covered, target, f"{container.file}:{line} → {parent}")
        return Chain(ticket, covered, "upstream-unresolved", parent, f"{covered} maps to {parent}, which no upstream source defines")
    target = _defined_in_sources(q, covered, container)
    detail = f"defined in {', '.join(container.sources) or 'container spec'}"
    if not target and upstream is not None:
        target, detail = _defined_upstream(q, tree, covered, upstream, container), "parent id reused"
    if not target:
        return Chain(ticket, covered, "unresolved", None, f"{covered} is not in the requirement source of {container.folder}")
    if container.covers and covered not in container.covers:  # a direct upstream ID must stay inside what its container owns
        return Chain(ticket, covered, "not-in-container-covers", target, f"{container.file or container.folder} does not list {covered} in covers")
    return _resolved(q, ticket, covered, target, detail)


def _resolved(q: Queries, ticket: str, covered: str, target: str | None, detail: str) -> Chain:
    """A chain ends in one definition; an ID with several current definitions makes the coverage unknown."""
    family = q.conn.execute("SELECT family FROM defs WHERE id=? LIMIT 1", (target,)).fetchone() if target else None
    scoped = family is not None and getattr(q.index.config.families.get(family["family"]), "scope", "project") == "document"
    if target and not scoped and q.resolve(target).status.startswith("ambiguous"):
        return Chain(ticket, covered, "ambiguous-source", target, f"{target} has several current definitions")
    return Chain(ticket, covered, "resolved", target, detail)


def covers_rows(q: Queries, ids: list[str]) -> list[dict]:
    """Resolved ticket chains reaching any of `ids`, shaped like refs rows (kind "covers")."""
    tree = load_tree(q)
    by_ref = {t.ref: t for t in tree.tickets}
    rows = []
    for chain in chains(q, tree):
        if chain.state != "resolved" or chain.target not in ids:
            continue
        ticket = by_ref[chain.ticket]
        path = ticket.file or ticket.toml_path
        line = _covers_line(q, path, ticket.ref.rsplit(".", 1)[-1], ticket.file is not None)
        rows.append({"path": path, "line": line, "col": 0, "id": chain.target, "raw": chain.covered_id, "via_range": 0,
                     "kind": "covers", "src_id": f"ticket {ticket.ref}", "rule": "ticket-chain", "status": "resolved",
                     "role": q.files[path]["role"], "temporal": "current", "ids": {chain.target},
                     "excerpt": f"ticket {ticket.ref} “{ticket.title}” covers {chain.covered_id} → {chain.target}"})
    return rows


def _covers_line(q: Queries, path: str, entry_id: str, is_leaf: bool) -> int:
    """The `covers` line of a leaf file's frontmatter, or of the matching [[entry]]/[[epic]] block in tickets.toml
    (keys may come in any order inside a block)."""
    lines = q.lines(path)
    blocks = [[]] if is_leaf else []
    for number, line in enumerate(lines, start=1):
        if not is_leaf and line.strip().startswith("[["):
            blocks.append([])
        if blocks:
            blocks[-1].append((number, line.strip()))
    own_id = re.compile(rf"id\s*=\s*[\"']?{re.escape(entry_id)}[\"']?")
    for block in blocks:
        if is_leaf or any(own_id.fullmatch(text) for _, text in block):
            covers = [number for number, text in block if re.match(r"covers\s*[:=]", text)]
            return covers[0] if covers else block[0][0]
    return 1


def _defined_upstream(q: Queries, tree: Tree, ident: str, upstream: Container | None, child: Container) -> str | None:
    if upstream is None:
        return _defined_in_sources(q, ident, child)
    if ident in upstream.requirements:
        parent, _ = upstream.requirements[ident]
        return _defined_upstream(q, tree, parent, tree.containers.get(upstream.parent) if upstream.parent else None, upstream) if parent else ident
    return _defined_in_sources(q, ident, upstream)


def _defined_in_sources(q: Queries, ident: str, container: Container) -> str | None:
    paths = [p.strip("/") for p in container.sources]
    paths += [p for p in q.files if p.startswith(container.folder + "/spec-") and p.endswith("/SPEC.md")]
    for path in paths:
        row = q.conn.execute("SELECT id FROM defs WHERE id=? AND path=? AND effective='definition'", (ident, path)).fetchone()
        if row:
            return row["id"]
    return None
