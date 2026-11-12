"""BMAD ticket tree adapter (read-only): bmad-agent-po's tree, in its current layout and the October v7 one.

A container is a `<type>-<slug>/` folder with a same-named file and a `tickets.toml`, which sits in the container's
`tickets/` folder with an initiative's epic folders and an epic's leaf files and plans (the October layout kept
them beside the container's file; see layout.py). An initiative lists `[[epic]]` tables, or `[[entry]]` tables when
it has no epics; an epic lists `[[entry]]` tables; a parent initiative lists `[[initiative]]` tables, its children,
initiative folders beside it. A leaf file (frontmatter `type` story, spike or bug) joins the entry with its `id`; as
in BMad's tickets.py, a leaf file no entry lists is a ticket of its own, keyed by its file stem when it has no id.

A container's `## Requirements` lines give each of its requirement IDs what it derives from, in parentheses:
`R1 (FR-2, FR-5)` source IDs, `R1 (prd FR-2)` a source ID in a source of that type, `R1 (parent R3)` or
`E1 (R3)` the parent container's requirement, anything else a source section (a requirement stated at its own
altitude, so a chain to it is `local`). Its requirement sources are its frontmatter `sources:` (paths from the
project root; an October ticket without them names them on `prd —` and `spec —` References lines) and a spec in a
`spec-*` folder inside it;
an ID defined in a source inside an epic's own folder is the epic's to assign. Standalone leaves in the backlog
folder have no container: their `covers` cite the specs of record directly. Under an active initiative only its
tree, its parent initiatives and the backlog are checked. Dropped work stays in the tree (`status: dropped` in a plan
or a container file, `tracker_status: dropped` in a leaf file) and is never coverage. BMAD's tickets.py never
validates `covers`; this module does, without changing anything.
"""
from __future__ import annotations

import json
import posixpath
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple

from . import layout
from .config import glob_to_regex
from .queries import Queries

ID = r"[A-Z][A-Za-z]*-?\d+(?:\.\d+)?"
REQUIREMENT_LINE = re.compile(rf"^\s*[-*]\s+(?:\*\*)?(?P<id>{ID})(?:\*\*)?(?:\s*\((?P<items>[^)]*)\))?")
REQUIREMENT_ITEM = re.compile(rf"^(?:(?P<parent>parent)\s+|(?P<type>[a-z][\w-]*)\s+)?(?P<id>{ID})$")
ITEM_RANGE = re.compile(rf"^(?:(?P<type>[a-z][\w-]*)\s+)?(?P<first>{ID})\s*(?:–|—|…|\.\.|-|to|through)\s*(?P<last>{ID})$")
ID_NUMBER = re.compile(r"(?P<prefix>.*?)(?P<number>\d+)")
MAX_RANGE = 200
REFERENCE_LINE = re.compile(r"^\s*[-*]\s+(?P<type>[a-z][\w-]*)\s+—\s+(?P<location>[^,\s]+)")
NUMBERED_SOURCE_TYPES = ("prd", "spec")
LEAF_TYPES = ("story", "spike", "bug")
DROPPED = "dropped"
PARENT = "parent"
LEAF, EPIC, CHILD, STANDALONE = "leaf", "epic", "initiative", "standalone"
REACHED = ("resolved", "local")  # chain states that end in an ID; every other state is a covers problem


@dataclass(slots=True)
class Ticket:
    ref: str                  # for display: "<epic id>.<id>", an epic's id, a child initiative's folder name,
                              # "<backlog folder>.<id or stem>" or a file stem; prefixed with its container's folder
                              # name when it repeats
    key: str                  # unique: "<container folder>/<id or stem>", or a record's own folder
    kind: str                 # leaf | epic (an [[epic]] record) | initiative (an [[initiative]] record) | standalone
    container: str            # folder of the owning container
    title: str
    covers: list[str]
    toml_path: str
    ident: str | None = None  # its id in tickets.toml or the leaf file; None for a leaf file without one
    epic_folder: str | None = None  # an [[epic]] or [[initiative]] record: the folder its slug names
    file: str | None = None   # leaf file, which is the truth over tickets.toml content fields
    file_covers: list[str] | None = None  # None when the file has no covers list: the entry's apply
    status: str | None = None  # its plan's status; None when it has no plan
    dropped: bool = False

    @property
    def leaf(self) -> bool:
        return self.kind in (LEAF, STANDALONE)

    @property
    def planned(self) -> bool:
        """A leaf with neither a file nor a plan yet: expected work, not a defect."""
        return self.kind == LEAF and self.file is None and self.status is None

    @property
    def effective_covers(self) -> list[str]:
        return self.file_covers if self.file_covers is not None else self.covers


@dataclass(frozen=True, slots=True)
class Item:
    """One item in a Requirements line's parentheses."""
    ident: str | None         # None: a source section
    via: str | None           # "parent", a source type ("prd"), or None
    text: str


@dataclass(slots=True)
class Requirement:
    line: int
    items: list[Item]


@dataclass(slots=True)
class Container:
    folder: str
    kind: str                 # initiative | epic
    file: str | None
    toml_path: str
    tickets_dir: str          # where its breakdown, epic folders, leaf files and plans sit
    covers: list[str] = field(default_factory=list)
    requirements: dict[str, Requirement] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    parent: str | None = None
    epic_id: str | None = None
    status: str | None = None
    declares_sources: bool = False  # its frontmatter has `sources:` (current BMad): only those hold its source IDs
    source_files: list[str] | None = None  # sources, their shards and spec folders, once looked up


class Reach(NamedTuple):
    """Where citing an ID leads: one population ID (or a problem) per path through the Requirements lines."""
    state: str                # resolved | local | unresolved | no-source | not-in-container-covers | upstream-unresolved | ambiguous-source
    target: str | None        # the population ID reached (e.g. FR-7)
    detail: str
    target_path: str | None = None  # the document defining a document-scoped target: coverage keys it by both


@dataclass(slots=True)
class Chain:
    ticket: str               # the ticket's display ref
    key: str                  # the ticket's unique key
    covered_id: str
    state: str
    target: str | None
    detail: str
    target_path: str | None = None


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


# -- the tree ------------------------------------------------------------------------------------
def load_tree(q: Queries) -> Tree:
    tree = Tree()
    backlog = glob_to_regex(q.index.config.backlog) if q.index.config.backlog else None
    breakdowns = _read_breakdowns(q, tree, backlog)
    _add_unsliced(q, tree)
    for folder, data in breakdowns.items():
        for epic in data.get("epic", []):
            tree.tickets.append(_epic_record(q, tree, tree.containers[folder], epic))
        for child in data.get("initiative", []):
            tree.tickets.append(_child_record(tree, tree.containers[folder], child))
    for container in list(tree.containers.values()):
        container.parent = container.parent or _enclosing(tree, container)
        _add_leaves(q, tree, container, breakdowns.get(container.folder, {}).get("entry", []))
    _add_backlog(q, tree, backlog)
    _drop_under_dropped_containers(tree)
    _qualify_repeated_refs(tree.tickets)
    return tree


def _read_breakdowns(q: Queries, tree: Tree, backlog: re.Pattern | None) -> dict[str, dict]:
    """Every tickets.toml in scope makes its container a container of the tree; a backlog's only reserves `next_id`."""
    scopes = q.current_folders
    breakdowns = {}
    for path in sorted(p for p, f in q.files.items() if f["artifact"] == "tickets-toml"
                       and (scopes is None or any(p.startswith(folder + "/") for folder in scopes))):
        folder = layout.container_of_breakdown(path)
        if backlog and backlog.match(folder):
            continue
        try:
            data = tomllib.loads("\n".join(q.lines(path)))
        except tomllib.TOMLDecodeError as error:
            tree.problems.append(("ticket-toml-invalid", path, 0, str(error)))
            continue
        tree.containers[folder] = _container(q, folder, _kind(q, folder, data), path)
        breakdowns[folder] = data
    return breakdowns


def _add_unsliced(q: Queries, tree: Tree) -> None:
    """A container file in scope with no breakdown yet (BMad writes the Requirements, then the spine, then slices) is
    still a container: its Requirements lines are what a spine binds."""
    scopes = q.current_folders
    for path in sorted(p for p, f in q.files.items() if f["artifact"] in layout.CONTAINER_TYPES and layout.is_main_file(p)
                       and (scopes is None or any(p.startswith(folder + "/") for folder in scopes))):
        folder = posixpath.dirname(path)
        if folder not in tree.containers:
            tree.containers[folder] = _container(q, folder, _kind(q, folder, {}), "")


def _kind(q: Queries, folder: str, data: dict) -> str:
    """The container file's `type`, else what its name and breakdown say."""
    declared = _frontmatter(q, layout.Containers.file(folder)).get("type")
    if declared in layout.CONTAINER_TYPES:
        return declared
    return "initiative" if posixpath.basename(folder).startswith("initiative-") or "epic" in data or "initiative" in data else "epic"


def _container(q: Queries, folder: str, kind: str, toml_path: str) -> Container:
    file = layout.Containers.file(folder)
    container = Container(folder, kind, file if file in q.files else None, toml_path, layout.tickets_dir(folder, q.files))
    if container.file:
        _read_container_file(q, container)
    return container


def _epic_record(q: Queries, tree: Tree, initiative: Container, epic: dict) -> Ticket:
    """An initiative's [[epic]] table: a ticket whose covers resolve against the initiative, owning the folder its slug names."""
    ident = str(epic.get("id"))
    folder = f"{initiative.tickets_dir}/{epic.get('slug', '')}"
    if folder not in tree.containers:  # an epic not yet incepted has no tickets.toml
        tree.containers[folder] = _container(q, folder, "epic", "")
    tree.containers[folder].epic_id, tree.containers[folder].parent = ident, initiative.folder
    return Ticket(ident, folder, EPIC, initiative.folder, epic.get("title", ""), list(epic.get("covers", [])),
                  initiative.toml_path, ident, epic_folder=folder)


def _child_record(tree: Tree, parent: Container, child: dict) -> Ticket:
    """A parent initiative's [[initiative]] table: a ticket whose covers resolve against the parent. Only the active
    child's own tree is read; the others are another initiative's work."""
    folder = posixpath.join(posixpath.dirname(parent.folder), str(child.get("slug", "")))
    if folder in tree.containers and folder != parent.folder:
        tree.containers[folder].parent = parent.folder
    return Ticket(posixpath.basename(folder), folder, CHILD, parent.folder, child.get("title", ""),
                  list(child.get("covers", [])), parent.toml_path, str(child.get("id")), epic_folder=folder)


def _enclosing(tree: Tree, container: Container) -> str | None:
    """An epic folder no breakdown lists still belongs to the container whose tickets folder holds it."""
    if container.kind != "epic":
        return None
    holder = posixpath.dirname(container.folder)
    return next((c.folder for c in tree.containers.values() if c is not container and c.tickets_dir == holder), None)


def _add_leaves(q: Queries, tree: Tree, container: Container, entries: list[dict]) -> None:
    """Each [[entry]] joined to the leaf file carrying its id, then each leaf file no entry lists."""
    files = _leaf_files(q, container.tickets_dir)
    by_id = {leaf.ident: leaf for leaf in files if leaf.ident is not None}
    plans = _plans(q, container.tickets_dir)
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
    """Standalone leaves in the backlog folder: no epic, so each file is the whole ticket."""
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
    container.covers = [str(c) for c in covers] if isinstance(covers, list) else []
    container.status = frontmatter.get("status")
    # BMad's tree check wants every source ID in a `sources:` file; an October ticket, which has none, names its
    # numbered sources on References lines.
    sources = frontmatter.get(q.index.config.fields.get("sources", "sources"))
    container.declares_sources = sources is not None
    for value in sources if isinstance(sources, list) else []:
        _add_source(container, _project_path(q, container.file, str(value)))
    section = None
    for number, line in enumerate(q.lines(container.file), start=1):
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section == "requirements":
            match = REQUIREMENT_LINE.match(line)
            if match:
                container.requirements[match.group("id")] = Requirement(number, _items(match.group("items")))
        elif section == "references" and sources is None:
            match = REFERENCE_LINE.match(line)
            if match and match.group("type") in NUMBERED_SOURCE_TYPES:
                _add_source(container, match.group("location").strip("`").strip("/"))


def _add_source(container: Container, path: str) -> None:
    if path not in container.sources:
        container.sources.append(path)


def _project_path(q: Queries, citing: str, value: str) -> str:
    """A path a ticket names: from the project root, as BMad writes `sources:`, else from the ticket's folder."""
    rooted = value.strip().strip("/")
    beside = posixpath.normpath(posixpath.join(posixpath.dirname(citing), value.strip()))
    return beside if rooted not in q.files and beside in q.files else rooted


def _items(text: str | None) -> list[Item]:
    items = []
    for part in (p.strip() for p in re.split(r"[,;]", text or "")):
        match = REQUIREMENT_ITEM.match(part)
        if match:
            items.append(Item(match.group("id"), PARENT if match.group("parent") else match.group("type"), part))
        elif ITEM_RANGE.match(part) and _range_items(ITEM_RANGE.match(part)):
            items += _range_items(ITEM_RANGE.match(part))
        elif part:  # a source section; `parent` alone names no parent id
            items.append(Item(None, PARENT if part.split()[0] == PARENT else None, part))
    return items


def _range_items(match: re.Match) -> list[Item]:
    """`FR-1–FR-3` or `prd FR-1 to FR-3`: every ID of the range, as check_ids.py reads one."""
    first, last = ID_NUMBER.fullmatch(match.group("first")), ID_NUMBER.fullmatch(match.group("last"))
    if not (first and last) or first.group("prefix") != last.group("prefix"):
        return []
    low, high = int(first.group("number")), int(last.group("number"))
    if not 0 < high - low <= MAX_RANGE:
        return []
    return [Item(f"{first.group('prefix')}{n}", match.group("type"), match.group(0)) for n in range(low, high + 1)]


def _frontmatter(q: Queries, path: str) -> dict:
    row = q.conn.execute("SELECT frontmatter FROM files WHERE path=?", (path,)).fetchone()
    return json.loads(row["frontmatter"]) if row and row["frontmatter"] else {}


def _leaf_files(q: Queries, folder: str) -> list[LeafFile]:
    """The leaves in a folder: files whose frontmatter `type` is story, spike or bug."""
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
    """Attach a ticket's leaf file and plan. Its state is BMad's: the file's `tracker_status`, else the plan's
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
        folder, seen = ticket.epic_folder or ticket.container, set()
        while folder in tree.containers and folder not in seen and not ticket.dropped:
            seen.add(folder)
            ticket.dropped = tree.containers[folder].status == DROPPED
            folder = tree.containers[folder].parent


def _qualify_repeated_refs(tickets: list[Ticket]) -> None:
    """A short ref repeats when an unlisted epic folder's entry 1 sits beside epic 1, or two initiatives both have an
    epic 1; its container's folder name tells them apart."""
    repeats = Counter(ticket.ref for ticket in tickets)
    for ticket in tickets:
        if repeats[ticket.ref] > 1:
            ticket.ref = f"{posixpath.basename(ticket.container)}/{ticket.ref}"


def container_holding(tree: Tree, path: str) -> Container | None:
    """The nearest container of the tree holding a file (a spine's run folder sits in its container)."""
    folder = posixpath.dirname(path)
    while folder:
        if folder in tree.containers:
            return tree.containers[folder]
        folder = posixpath.dirname(folder)
    return None


# -- chains -------------------------------------------------------------------------------------
def chains(q: Queries, tree: Tree) -> list[Chain]:
    """Resolve every ticket's covers through its container's Requirements lines up to defined IDs, one chain per ID
    reached. Dropped work is the record of a decision, never coverage, so it has no chains."""
    result = []
    for ticket in tree.tickets:
        if ticket.dropped:
            continue
        container = tree.containers.get(ticket.container)  # records resolve against their parent, entries their epic
        for covered in ticket.effective_covers:
            reaches = [_direct(q, covered)] if ticket.kind == STANDALONE else trace(q, tree, container, covered)
            result += [Chain(ticket.ref, ticket.key, covered, *reach) for reach in reaches]
    return result


def trace(q: Queries, tree: Tree, container: Container | None, ident: str, seen: frozenset = frozenset()) -> list[Reach]:
    """What citing `ident` under a container reaches: through the container's Requirements line for it, else the
    ID itself in the container's sources or upstream."""
    if container is None:
        return [Reach("unresolved", None, "no container")]
    if (container.folder, ident) in seen:
        return [Reach("upstream-unresolved", ident, f"{ident} in {container.file} leads back to itself")]
    seen = seen | {(container.folder, ident)}
    requirement = container.requirements.get(ident)
    if requirement is None:
        return [_unlisted(q, tree, container, ident, seen)]
    where = f"{container.file}:{requirement.line}"
    ids = [item for item in requirement.items if item.ident]
    if not requirement.items and _ticket_owned(q, ident):  # BMad's line names a parent id or a source section, always
        return [Reach("no-source", None, f"{where}: {ident} names neither a parent id nor a source section")]
    if any(item.via == PARENT and not item.ident for item in requirement.items):
        return [Reach("upstream-unresolved", None, f"{where}: {ident} names a parent but no parent id")]
    if not ids:  # the line reuses a parent's ID (`- FR-4: …`), or cites only a source section: a requirement of this altitude
        reused = None if _ticket_owned(q, ident) else _upstream_reach(q, tree, container, Item(ident, None, ident), ident, where, seen)
        return reused or [Reach("local", ident, f"{where} (no source id)", container.file if _scoped_id(q, ident) else None)]
    reaches = []
    for item in ids:
        reaches += (_upstream_reach(q, tree, container, item, ident, where, seen)
                    or [_folded_or_unresolved(q, container, item, ident, where)])
    return reaches


def _upstream_reach(q: Queries, tree: Tree, container: Container, item: Item, line_id: str, where: str,
                    seen: frozenset) -> list[Reach] | None:
    """An item naming the parent's requirement or a source ID; None when nothing defines it."""
    upstream = _upstream(tree, container)
    if item.via in (None, PARENT) and upstream is not None and item.ident in upstream.requirements:
        if container.covers and item.ident not in container.covers:
            return [Reach("not-in-container-covers", item.ident,
                          f"{line_id} maps to {item.ident}, which {container.file} does not list in covers")]
        return [r._replace(detail=f"{where} → {r.detail}") for r in trace(q, tree, upstream, item.ident, seen)]
    if item.via == PARENT or _ticket_owned(q, item.ident):  # a parent's requirement is in the parent's lines, never a document
        return [Reach("upstream-unresolved", item.ident, f"{line_id} maps to parent {item.ident}, which "
                      f"{upstream.file if upstream else 'no parent container'} does not define")]
    definition = _defined_in_sources(q, tree, container, item.ident, _source_types(q, item.via))
    if definition is None:
        return None
    path, own = definition
    if not own and container.covers and item.ident not in container.covers:
        return [Reach("not-in-container-covers", item.ident,
                      f"{line_id} maps to {item.ident}, which {container.file} does not list in covers")]
    return [_resolved(q, item.ident, path, f"{where} → {item.ident}")]


def _folded_or_unresolved(q: Queries, container: Container, item: Item, line_id: str, where: str) -> Reach:
    """A folded spec's ID (`R2 (CAP-1)`) names the line's own requirement; any other undefined ID, and a spec ID while
    the container still has its spec, is a broken chain."""
    if _family_of(q, item.ident or "") in q.index.config.alias_families and not _has_spec(q, container):
        return Reach("local", line_id, f"{where} ({item.ident} folded into the ticket)", container.file if _scoped_id(q, line_id) else None)
    return Reach("upstream-unresolved", item.ident, f"{line_id} maps to {item.ident}, which no upstream source defines")


def _has_spec(q: Queries, container: Container) -> bool:
    return any(q.files.get(path, {}).get("artifact") == "spec" or path.endswith("/SPEC.md") for path in _source_files(q, container))


def _unlisted(q: Queries, tree: Tree, container: Container, ident: str, seen: frozenset) -> Reach:
    """An ID no Requirements line of the container lists: defined in its own sources, or reused from upstream. A
    ticket's own R id is only ever its container's."""
    if _ticket_owned(q, ident):
        return Reach("unresolved", None, f"{ident} is not a requirement of {container.file or container.folder}")
    definition = _source_defining(q, ident, container)
    if definition and container.kind == "epic" and definition[0].startswith(container.folder + "/") and _scoped_id(q, ident):
        return _local_chain(q, tree, ident, definition, container)
    if definition:
        own = _own_source(container, definition[0])
        found: list[Reach] | None = [_resolved(q, ident, definition[0], f"defined in {', '.join(container.sources) or 'container spec'}")]
    else:
        own = False
        found = _upstream_reach(q, tree, container, Item(ident, None, ident), ident, "parent id reused", seen)
    if not found:
        return Reach("unresolved", None, f"{ident} is not in the requirement source of {container.folder}")
    if found[0].state == "resolved" and not own and container.covers and ident not in container.covers:
        return Reach("not-in-container-covers", found[0].target, f"{container.file or container.folder} does not list {ident} in covers")
    return found[0]


def _local_chain(q: Queries, tree: Tree, ident: str, definition: tuple[str, int], container: Container) -> Reach:
    """An ID of a spec inside an epic's own folder is the epic's to assign: the epic's covers keep the parent IDs it maps
    to. The spec line may name that parent (`- **CAP-1** (FR-4) — …`), which is followed; otherwise the ID is local
    and its parent is unknown, which is not a defect."""
    path, line = definition
    match = REQUIREMENT_LINE.match(q.lines(path)[line - 1])
    parent = next((item for item in _items(match.group("items")) if item.ident), None) if match else None
    if parent is not None:
        reached = _upstream_reach(q, tree, container, parent, ident, f"{path}:{line}", frozenset())
        return reached[0] if reached else Reach("upstream-unresolved", parent.ident,
                                                 f"{ident} maps to {parent.ident}, which no upstream source defines")
    return Reach("local", ident, f"defined in {path}", path)


def _direct(q: Queries, covered: str) -> Reach:
    """A backlog leaf cites the specs of record directly."""
    resolution = q.resolve(covered)
    if resolution.status == "defined":
        return _resolved(q, covered, resolution.definitions[0].path, "defined in the specs of record")
    if resolution.status.startswith("ambiguous"):
        return Reach("ambiguous-source", covered, f"{covered} has several current definitions")
    return Reach("unresolved", None, f"{covered} is not defined in the specs of record")


def _resolved(q: Queries, target: str, path: str, detail: str) -> Reach:
    """A chain ends in one definition; an ID with several current definitions makes the coverage unknown."""
    scoped = _scoped_id(q, target)
    if not scoped and q.resolve(target).status.startswith("ambiguous"):
        return Reach("ambiguous-source", target, f"{target} has several current definitions")
    return Reach("resolved", target, detail, path if scoped else None)


def _ticket_owned(q: Queries, ident: str) -> bool:
    """An ID each ticket numbers for itself (R1), never a parent's ID reused."""
    owners = getattr(q.index.config.families.get(_family_of(q, ident) or ""), "owners", ())
    return any(owner in layout.CONTAINER_TYPES for owner in owners)


def _family_of(q: Queries, ident: str) -> str | None:
    match = q.index.config.id_regex.fullmatch(ident)
    return next((f for g, f in q.index.config.family_groups.items() if match and match.group(g)), None)


def _scoped_id(q: Queries, ident: str) -> bool:
    row = q.conn.execute("SELECT family FROM defs WHERE id=? LIMIT 1", (ident,)).fetchone()
    return row is not None and document_scoped(q, row["family"])


def _upstream(tree: Tree, container: Container) -> Container | None:
    return tree.containers.get(container.parent) if container.parent else None


def _source_types(q: Queries, word: str | None) -> list[str] | None:
    """The artifact types a Requirements item's prefix names (`prd FR-2`); None: any source."""
    return q.index.config.doc_aliases.get(word) if word and word != PARENT else None


def _own_source(container: Container, path: str) -> bool:
    """An epic's own document (its PRD, a spec in its folder) defines IDs that are the epic's to assign, never one of
    the parent IDs its covers must list."""
    return container.kind == "epic" and path.startswith(container.folder + "/")


def _defined_in_sources(q: Queries, tree: Tree, container: Container, ident: str, types: list[str] | None) -> tuple[str, bool] | None:
    """The source defining an ID, and whether it is the container's own. BMad's tree check wants every source ID in a
    `sources:` file of the ticket itself; an October ticket, which declares none, reuses the sources above it."""
    current: Container | None = container
    visited = set()
    while current is not None and current.folder not in visited:
        visited.add(current.folder)
        definition = _source_defining(q, ident, current, types)
        if definition:
            return definition[0], _own_source(container, definition[0])
        if current.declares_sources:
            return None
        current = _upstream(tree, current)
    return None


def _source_files(q: Queries, container: Container) -> list[str]:
    """A container's requirement sources: each source (a sharded one with every shard) and a spec folder inside it."""
    if container.source_files is None:
        shards = [p for p, f in q.files.items() if f["part_of"] in container.sources]
        specs = [p for p, f in q.files.items()
                 if p.startswith(container.folder + "/spec-") and (p.endswith("/SPEC.md") or f["artifact"] == "spec")]
        container.source_files = container.sources + shards + specs
    return container.source_files


def _source_defining(q: Queries, ident: str, container: Container, types: list[str] | None = None) -> tuple[str, int] | None:
    """The path and line where a container's requirement sources define `ident`."""
    for path in _source_files(q, container):
        if types and q.files.get(path, {}).get("artifact") not in types:
            continue
        row = q.conn.execute("SELECT line FROM defs WHERE id=? AND path=? AND effective='definition'", (ident, path)).fetchone()
        if row:
            return path, row["line"]
    return None


# -- where covers are written -------------------------------------------------------------------
def covers_rows(q: Queries, ids: list[str]) -> list[dict]:
    """Ticket chains reaching any of `ids`, shaped like refs rows (kind "covers")."""
    tree = load_tree(q)
    by_key = {t.key: t for t in tree.tickets}
    rows = []
    seen = set()
    for chain in chains(q, tree):
        reached = chain.state in REACHED and chain.target in ids
        cited = chain.covered_id in ids  # an entry citing an R id itself, written in tickets.toml or a leaf file
        if not (reached or cited) or (chain.key, chain.covered_id, reached and chain.target) in seen:
            continue
        seen.add((chain.key, chain.covered_id, reached and chain.target))
        ticket = by_key[chain.key]
        path, line = covers_location(q, ticket)
        ident = chain.target if reached else chain.covered_id
        arrow = f" → {chain.target}" if reached and chain.target != chain.covered_id else ""
        rows.append({"path": path, "line": line, "col": 0, "id": ident, "raw": chain.covered_id, "via_range": 0,
                     "kind": "covers", "src_id": f"ticket {ticket.ref}", "rule": "ticket-chain",
                     "status": "resolved" if chain.state in REACHED else "unresolved",
                     "role": q.files[path]["role"], "temporal": "current", "ids": {ident},
                     "excerpt": f"ticket {ticket.ref} “{ticket.title}” covers {chain.covered_id}{arrow}"})
    return rows


def covers_location(q: Queries, ticket: Ticket) -> tuple[str, int]:
    """Where a ticket's covers are written: its leaf file's frontmatter when that has a covers list, else its
    [[entry]], [[epic]] or [[initiative]] block in tickets.toml (keys in any order, a value may carry a comment)."""
    if ticket.file is not None and ticket.file_covers is not None:
        return ticket.file, _covers_line([(n, line.strip()) for n, line in enumerate(q.lines(ticket.file), start=1)])
    table = {EPIC: "[[epic]]", CHILD: "[[initiative]]"}.get(ticket.kind, "[[entry]]")
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
