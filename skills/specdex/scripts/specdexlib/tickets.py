"""BMAD ticket tree adapter (read-only): bmad-ticket, and the bmad-preview-ticketing tree it replaced.

A container is a `<type>-<slug>/` folder with a same-named file and a `tickets.toml`;
an initiative lists `[[epic]]` tables, or `[[entry]]` tables when it has no epics,
and an epic lists `[[entry]]` tables. A leaf file (frontmatter `type` story, spike or
bug) joins the entry with its `id`; as in bmad-ticket's tickets.py, a leaf file no entry
lists is a ticket of its own, keyed by its file stem when it has no id. Each container's
requirement source is, in order: its own `## Requirements` section, a referenced numbered
source (a `prd —` or `spec —` References line), or a spec in a `spec-*` folder inside it;
an ID of a spec inside an epic's own folder is the epic's to assign and maps to a parent
ID. Standalone leaves in the backlog folders have no container: their `covers` cite the
specs of record directly. Under an active initiative only its tree and the backlog are
checked. Dropped work stays in the tree (`status: dropped` in a plan or a container file,
`tracker_status: dropped` in a leaf file) and is never coverage. BMAD's tickets.py never
validates `covers`; this module does, without changing anything.
"""
from __future__ import annotations

import json
import posixpath
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field

from .config import glob_to_regex
from .queries import Queries

ID = r"[A-Z][A-Za-z]*-?\d+(?:\.\d+)?"
REQUIREMENT_LINE = re.compile(rf"^\s*[-*]\s+(?:\*\*)?(?P<id>{ID})(?:\*\*)?(?:\s*\((?P<parent>[^)]*)\))?")
REFERENCE_LINE = re.compile(r"^\s*[-*]\s+(?P<type>[a-z][\w-]*)\s+—\s+(?P<location>[^,\s]+)")
NUMBERED_SOURCE_TYPES = ("prd", "spec")
LEAF_TYPES = ("story", "spike", "bug")
DROPPED = "dropped"
LEAF, EPIC, STANDALONE = "leaf", "epic", "standalone"
REACHED = ("resolved", "local")  # chain states that end in an ID; every other state is a covers problem


@dataclass(slots=True)
class Ticket:
    ref: str                  # for display: "<epic id>.<id>", an epic's id, "<backlog folder>.<id or stem>" or a file
                              # stem; prefixed with its container's folder name when it repeats
    key: str                  # unique: "<container folder>/<id or stem>", or an epic record's own folder
    kind: str                 # leaf | epic (an initiative's [[epic]] record) | standalone (a backlog leaf)
    container: str            # folder of the owning container
    title: str
    covers: list[str]
    toml_path: str
    ident: str | None = None  # its id in tickets.toml or the leaf file; None for a leaf file without one
    epic_folder: str | None = None  # an epic record: the folder its slug names
    file: str | None = None   # leaf file, which is the truth over tickets.toml content fields
    file_covers: list[str] | None = None  # None when the file has no covers list: the entry's apply
    status: str | None = None  # its plan's status; None when it has no plan
    dropped: bool = False

    @property
    def leaf(self) -> bool:
        return self.kind != EPIC

    @property
    def planned(self) -> bool:
        """A leaf with neither a file nor a plan yet: expected work, not a defect."""
        return self.kind == LEAF and self.file is None and self.status is None

    @property
    def effective_covers(self) -> list[str]:
        return self.file_covers if self.file_covers is not None else self.covers


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
    status: str | None = None


@dataclass(slots=True)
class Chain:
    ticket: str               # the ticket's display ref
    key: str                  # the ticket's unique key
    covered_id: str
    state: str                # resolved | local | unresolved | not-in-container-covers | upstream-unresolved | ambiguous-source
    target: str | None        # the population ID the chain reaches (e.g. FR-7)
    detail: str
    target_path: str | None = None  # the document defining a document-scoped target: coverage keys it by both


@dataclass(slots=True)
class Tree:
    containers: dict[str, Container] = field(default_factory=dict)
    tickets: list[Ticket] = field(default_factory=list)
    problems: list[tuple[str, str, int, str]] = field(default_factory=list)  # code, path, line, detail


@dataclass(frozen=True, slots=True)
class LeafFile:
    path: str
    ident: str | None
    covers: list[str] | None  # None when its frontmatter has no covers list
    frontmatter: dict

    @property
    def stem(self) -> str:
        return posixpath.splitext(posixpath.basename(self.path))[0]

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or posixpath.basename(self.path))


def document_scoped(q: Queries, family: str) -> bool:
    return getattr(q.index.config.families.get(family), "scope", "project") == "document"


def load_tree(q: Queries) -> Tree:
    tree = Tree()
    backlog = glob_to_regex(q.index.config.backlog) if q.index.config.backlog else None
    breakdowns = _read_breakdowns(q, tree, backlog)
    for folder, data in breakdowns.items():
        for epic in data.get("epic", []):
            tree.tickets.append(_epic_record(q, tree, tree.containers[folder], epic))
    for container in list(tree.containers.values()):
        parent = posixpath.dirname(container.folder)
        container.parent = container.parent or (parent if container.kind == "epic" and parent in tree.containers else None)
        _add_leaves(q, tree, container, breakdowns.get(container.folder, {}).get("entry", []))
    _add_backlog(q, tree, backlog)
    _drop_under_dropped_containers(tree)
    _qualify_repeated_refs(tree.tickets)
    return tree


def _read_breakdowns(q: Queries, tree: Tree, backlog: re.Pattern | None) -> dict[str, dict]:
    """Every tickets.toml in scope makes its folder a container; a backlog's only reserves `next_id`."""
    scope = q.index.config.current_scope
    breakdowns = {}
    for path in sorted(p for p, f in q.files.items()
                       if f["artifact"] == "tickets-toml" and (scope is None or p.startswith(scope + "/"))):
        folder = posixpath.dirname(path)
        if backlog and backlog.match(folder):
            continue
        try:
            data = tomllib.loads("\n".join(q.lines(path)))
        except tomllib.TOMLDecodeError as error:
            tree.problems.append(("ticket-toml-invalid", path, 0, str(error)))
            continue
        name = posixpath.basename(folder)
        kind = "initiative" if name.startswith("initiative-") or "epic" in data else "epic"
        tree.containers[folder] = _container(q, folder, kind, path)
        breakdowns[folder] = data
    return breakdowns


def _container(q: Queries, folder: str, kind: str, toml_path: str) -> Container:
    file = f"{folder}/{posixpath.basename(folder)}.md"
    container = Container(folder, kind, file if file in q.files else None, toml_path)
    if container.file:
        _read_container_file(q, container)
    return container


def _epic_record(q: Queries, tree: Tree, initiative: Container, epic: dict) -> Ticket:
    """An initiative's [[epic]] table: a ticket whose covers resolve against the initiative, owning the folder its slug names."""
    ident = str(epic.get("id"))
    folder = f"{initiative.folder}/{epic.get('slug', '')}"
    if folder not in tree.containers:  # an epic not yet incepted has no tickets.toml
        tree.containers[folder] = _container(q, folder, "epic", "")
    tree.containers[folder].epic_id, tree.containers[folder].parent = ident, initiative.folder
    return Ticket(ident, folder, EPIC, initiative.folder, epic.get("title", ""), list(epic.get("covers", [])),
                  initiative.toml_path, ident, epic_folder=folder)


def _add_leaves(q: Queries, tree: Tree, container: Container, entries: list[dict]) -> None:
    """Each [[entry]] joined to the leaf file carrying its id, then each leaf file no entry lists."""
    files = _leaf_files(q, container.folder)
    by_id = {leaf.ident: leaf for leaf in files if leaf.ident is not None}
    plans = _plans(q, container.folder)
    listed = set()
    for entry in entries:
        ident = str(entry.get("id"))
        listed.add(ident)
        ticket = Ticket(_leaf_ref(container, ident), f"{container.folder}/{ident}", LEAF, container.folder,
                        entry.get("title", ""), list(entry.get("covers", [])), container.toml_path, ident)
        _join(ticket, by_id.get(ident), plans)
        tree.tickets.append(ticket)
    for leaf in files:
        if leaf.ident in listed:
            continue
        ref = _leaf_ref(container, leaf.ident) if leaf.ident else leaf.stem
        ticket = Ticket(ref, f"{container.folder}/{leaf.ident or leaf.stem}", LEAF, container.folder, leaf.title,
                        leaf.covers or [], container.toml_path, leaf.ident)
        _join(ticket, leaf, plans)
        tree.tickets.append(ticket)


def _leaf_ref(container: Container, ident: str) -> str:
    return f"{container.epic_id}.{ident}" if container.epic_id else ident


def _add_backlog(q: Queries, tree: Tree, backlog: re.Pattern | None) -> None:
    """Standalone leaves in every backlog folder (`backlog/`, `backlog-<slug>/`): no epic, so each file is the whole ticket."""
    if backlog is None:
        return
    folders = sorted({posixpath.dirname(p) for p, f in q.files.items()
                      if f["artifact"] == "ticket-leaf" and backlog.match(posixpath.dirname(p))})
    for folder in folders:
        plans = _plans(q, folder)
        for leaf in _leaf_files(q, folder):
            name = leaf.ident or leaf.stem
            ticket = Ticket(f"{posixpath.basename(folder)}.{name}", f"{folder}/{name}", STANDALONE, folder, leaf.title,
                            leaf.covers or [], leaf.path, leaf.ident)
            _join(ticket, leaf, plans)
            tree.tickets.append(ticket)


def _read_container_file(q: Queries, container: Container) -> None:
    frontmatter = _frontmatter(q, container.file)
    covers = frontmatter.get("covers")
    container.covers = list(covers) if isinstance(covers, list) else []
    container.status = frontmatter.get("status")
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


def _frontmatter(q: Queries, path: str) -> dict:
    row = q.conn.execute("SELECT frontmatter FROM files WHERE path=?", (path,)).fetchone()
    return json.loads(row["frontmatter"]) if row and row["frontmatter"] else {}


def _leaf_files(q: Queries, folder: str) -> list[LeafFile]:
    """bmad-ticket's leaves in a folder: files whose frontmatter `type` is story, spike or bug."""
    leaves = []
    for path in sorted(p for p, info in q.files.items() if info["artifact"] == "ticket-leaf" and posixpath.dirname(p) == folder):
        frontmatter = _frontmatter(q, path)
        if frontmatter.get("type") not in LEAF_TYPES:
            continue
        ident, covers = frontmatter.get("id"), frontmatter.get("covers")
        leaves.append(LeafFile(path, None if ident in (None, "") else str(ident),
                               [str(c) for c in covers] if isinstance(covers, list) else None, frontmatter))
    return leaves


def _plans(q: Queries, folder: str) -> dict[str, dict]:
    """A folder's plan frontmatter by its `ticket`: an entry's id, or a leaf file's stem (a backlog plan)."""
    plans: dict[str, dict] = {}
    for path in sorted(p for p, info in q.files.items() if info["artifact"] == "ticket-plan" and posixpath.dirname(p) == folder):
        frontmatter = _frontmatter(q, path)
        if "ticket" in frontmatter:
            plans.setdefault(str(frontmatter["ticket"]), frontmatter)
    return plans


def _join(ticket: Ticket, leaf: LeafFile | None, plans: dict[str, dict]) -> None:
    """Attach a ticket's leaf file and plan. Its state is bmad-ticket's: the file's `tracker_status`, else the plan's
    `status`, else (no plan) the file's own `status`."""
    names = [ticket.ident] + ([leaf.stem] if leaf else [])
    plan = next((plans[name] for name in names if name in plans), None)
    own = leaf.frontmatter if leaf else {}
    if leaf:
        ticket.file, ticket.file_covers = leaf.path, leaf.covers
    ticket.status = plan.get("status") if plan else None
    ticket.dropped = (own.get("tracker_status") or (own if plan is None else plan).get("status")) == DROPPED


def _drop_under_dropped_containers(tree: Tree) -> None:
    """A container whose file says `status: dropped` drops everything under it."""
    for ticket in tree.tickets:
        folder = ticket.epic_folder or ticket.container
        while folder in tree.containers and not ticket.dropped:
            ticket.dropped = tree.containers[folder].status == DROPPED
            folder = tree.containers[folder].parent


def _qualify_repeated_refs(tickets: list[Ticket]) -> None:
    """A short ref repeats when an unlisted epic folder's entry 1 sits beside epic 1, or two initiatives both have an
    epic 1; its container's folder name tells them apart."""
    repeats = Counter(ticket.ref for ticket in tickets)
    for ticket in tickets:
        if repeats[ticket.ref] > 1:
            ticket.ref = f"{posixpath.basename(ticket.container)}/{ticket.ref}"


def chains(q: Queries, tree: Tree) -> list[Chain]:
    """Resolve every ticket's covers through its container's requirement source up to a defined ID. Dropped work is
    the record of a decision, never coverage, so it has no chains."""
    result = []
    for ticket in tree.tickets:
        if ticket.dropped:
            continue
        container = tree.containers.get(ticket.container)  # epics resolve against their initiative, entries against their epic
        for covered in ticket.effective_covers:
            if ticket.kind == STANDALONE:
                result.append(_direct_chain(q, ticket, covered))
            else:
                result.append(_container_chain(q, tree, ticket, covered, container))
    return result


def _make_chain(ticket: Ticket, covered: str, state: str, target: str | None, detail: str, target_path: str | None = None) -> Chain:
    return Chain(ticket.ref, ticket.key, covered, state, target, detail, target_path)


def _direct_chain(q: Queries, ticket: Ticket, covered: str) -> Chain:
    """A backlog leaf cites the specs of record directly."""
    resolution = q.resolve(covered)
    if resolution.status == "defined":
        return _resolved(q, ticket, covered, covered, resolution.definitions[0].path, "defined in the specs of record")
    if resolution.status.startswith("ambiguous"):
        return _make_chain(ticket, covered, "ambiguous-source", covered, f"{covered} has several current definitions")
    return _make_chain(ticket, covered, "unresolved", None, f"{covered} is not defined in the specs of record")


def _container_chain(q: Queries, tree: Tree, ticket: Ticket, covered: str, container: Container | None) -> Chain:
    if container is None:
        return _make_chain(ticket, covered, "unresolved", None, "no container")
    upstream = _upstream(tree, container)
    if covered in container.requirements:
        parent, line = container.requirements[covered]
        where = f"{container.file}:{line}"
        if parent is not None:
            return _mapped_chain(q, tree, ticket, covered, parent, where, container)
        # The line reuses a parent ID, or (platform baseline) cites only a source section.
        target, path = _defined_upstream(q, tree, covered, upstream, container) or (None, None)
        if target and container.covers and covered not in container.covers:
            return _make_chain(ticket, covered, "not-in-container-covers", target, f"{container.file} does not list {covered} in covers")
        return _resolved(q, ticket, covered, target, path, where + ("" if target else " (no parent id)"))
    definition = _source_defining(q, covered, container)
    if definition and container.kind == "epic" and definition[0].startswith(container.folder + "/"):
        return _local_chain(q, tree, ticket, covered, definition, container)
    found = (covered, definition[0]) if definition else None
    detail = f"defined in {', '.join(container.sources) or 'container spec'}"
    if found is None and upstream is not None:
        found, detail = _defined_upstream(q, tree, covered, upstream, container), "parent id reused"
    if found is None:
        return _make_chain(ticket, covered, "unresolved", None, f"{covered} is not in the requirement source of {container.folder}")
    if container.covers and covered not in container.covers:  # a direct upstream ID must stay inside what its container owns
        return _make_chain(ticket, covered, "not-in-container-covers", found[0], f"{container.file or container.folder} does not list {covered} in covers")
    return _resolved(q, ticket, covered, *found, detail)


def _mapped_chain(q: Queries, tree: Tree, ticket: Ticket, covered: str, parent: str, where: str, container: Container) -> Chain:
    """A local ID whose line names its parent ID: the parent must be one its container owns, defined upstream."""
    if container.covers and parent not in container.covers:
        return _make_chain(ticket, covered, "not-in-container-covers", parent, f"{covered} maps to {parent}, which {container.file} does not list in covers")
    found = _defined_upstream(q, tree, parent, _upstream(tree, container), container)
    if found:
        return _resolved(q, ticket, covered, *found, f"{where} → {parent}")
    return _make_chain(ticket, covered, "upstream-unresolved", parent, f"{covered} maps to {parent}, which no upstream source defines")


def _local_chain(q: Queries, tree: Tree, ticket: Ticket, covered: str, definition: tuple[str, int], container: Container) -> Chain:
    """An ID of a spec inside an epic's own folder is the epic's to assign: the epic's covers keep the parent IDs it maps
    to. bmad-ticket writes that map on the line (`E1 (R1)`), so a definition line naming a parent ID is followed;
    otherwise the ID is local and its parent is unknown, which is not a defect."""
    path, line = definition
    match = REQUIREMENT_LINE.match(q.lines(path)[line - 1])
    parent = (match.group("parent") or "").strip() if match else ""
    if re.fullmatch(ID, parent):
        return _mapped_chain(q, tree, ticket, covered, parent, f"{path}:{line}", container)
    return _make_chain(ticket, covered, "local", covered, f"defined in {path}", path if _scoped_id(q, covered) else None)


def _resolved(q: Queries, ticket: Ticket, covered: str, target: str | None, path: str | None, detail: str) -> Chain:
    """A chain ends in one definition; an ID with several current definitions makes the coverage unknown."""
    scoped = target is not None and _scoped_id(q, target)
    if target and not scoped and q.resolve(target).status.startswith("ambiguous"):
        return _make_chain(ticket, covered, "ambiguous-source", target, f"{target} has several current definitions")
    return _make_chain(ticket, covered, "resolved", target, detail, path if scoped else None)


def _scoped_id(q: Queries, ident: str) -> bool:
    row = q.conn.execute("SELECT family FROM defs WHERE id=? LIMIT 1", (ident,)).fetchone()
    return row is not None and document_scoped(q, row["family"])


def covers_rows(q: Queries, ids: list[str]) -> list[dict]:
    """Ticket chains reaching any of `ids`, shaped like refs rows (kind "covers")."""
    tree = load_tree(q)
    by_key = {t.key: t for t in tree.tickets}
    rows = []
    for chain in chains(q, tree):
        if chain.state not in REACHED or chain.target not in ids:
            continue
        ticket = by_key[chain.key]
        path, line = _covers_location(q, ticket)
        rows.append({"path": path, "line": line, "col": 0, "id": chain.target, "raw": chain.covered_id, "via_range": 0,
                     "kind": "covers", "src_id": f"ticket {ticket.ref}", "rule": "ticket-chain", "status": "resolved",
                     "role": q.files[path]["role"], "temporal": "current", "ids": {chain.target},
                     "excerpt": f"ticket {ticket.ref} “{ticket.title}” covers {chain.covered_id} → {chain.target}"})
    return rows


def _covers_location(q: Queries, ticket: Ticket) -> tuple[str, int]:
    """Where a ticket's covers are written: its leaf file's frontmatter when that has a covers list, else its
    [[entry]] or [[epic]] block in tickets.toml (keys in any order, a value may carry a trailing comment)."""
    if ticket.file is not None and ticket.file_covers is not None:
        return ticket.file, _covers_line([(n, line.strip()) for n, line in enumerate(q.lines(ticket.file), start=1)])
    table = "[[epic]]" if ticket.kind == EPIC else "[[entry]]"
    own_id = re.compile(rf"id\s*=\s*[\"']?{re.escape(ticket.ident or '')}[\"']?\s*(?:#.*)?")
    for header, block in _toml_blocks(q.lines(ticket.toml_path)):
        if header.startswith(table) and any(own_id.fullmatch(text) for _, text in block):
            return ticket.toml_path, _covers_line(block)
    return ticket.toml_path, 1


def _toml_blocks(lines: list[str]) -> list[tuple[str, list[tuple[int, str]]]]:
    blocks: list[tuple[str, list[tuple[int, str]]]] = []
    for number, line in enumerate(lines, start=1):
        text = line.strip()
        if text.startswith("[["):
            blocks.append((text, []))
        if blocks:
            blocks[-1][1].append((number, text))
    return blocks


def _covers_line(block: list[tuple[int, str]]) -> int:
    covers = [number for number, text in block if re.match(r"covers\s*[:=]", text)]
    return covers[0] if covers else block[0][0]


def _upstream(tree: Tree, container: Container) -> Container | None:
    return tree.containers.get(container.parent) if container.parent else None


def _defined_upstream(q: Queries, tree: Tree, ident: str, upstream: Container | None, child: Container) -> tuple[str, str | None] | None:
    """The ID a chain ends in, and the source defining it (None for a Requirements line that reuses a parent's ID)."""
    if upstream is None:
        return _defined_in_sources(q, ident, child)
    if ident in upstream.requirements:
        parent, _ = upstream.requirements[ident]
        return _defined_upstream(q, tree, parent, _upstream(tree, upstream), upstream) if parent else (ident, None)
    return _defined_in_sources(q, ident, upstream)


def _defined_in_sources(q: Queries, ident: str, container: Container) -> tuple[str, str] | None:
    definition = _source_defining(q, ident, container)
    return (ident, definition[0]) if definition else None


def _source_defining(q: Queries, ident: str, container: Container) -> tuple[str, int] | None:
    """The path and line where a container's requirement sources define `ident`."""
    paths = [p.strip("/") for p in container.sources]
    paths += [p for p, f in q.files.items()
              if p.startswith(container.folder + "/spec-") and (p.endswith("/SPEC.md") or f["artifact"] == "spec")]
    for path in paths:
        row = q.conn.execute("SELECT line FROM defs WHERE id=? AND path=? AND effective='definition'", (ident, path)).fetchone()
        if row:
            return path, row["line"]
    return None
