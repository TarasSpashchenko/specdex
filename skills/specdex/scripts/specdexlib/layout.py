"""Where BMad's ticket tree keeps its parts; path logic only, nothing here reads the index.

A container (an initiative or an epic) is a folder `<name>/` holding `<name>.md`. Its breakdown (`tickets.toml`, an
initiative's epic folders, an epic's leaf files and plans) sits in `<name>/tickets/` in current BMad, or beside its
file in the October v7 layout; both are read. A parent initiative's breakdown lists its children, initiative
folders beside it, in `[[initiative]]` tables.
"""
from __future__ import annotations

import posixpath
import tomllib
from collections.abc import Iterable

TICKETS = "tickets"
CONTAINER_TYPES = ("initiative", "epic")


def container_of_breakdown(path: str) -> str:
    """The container folder a tickets.toml belongs to."""
    holder = posixpath.dirname(path)
    return posixpath.dirname(holder) if posixpath.basename(holder) == TICKETS else holder


def tickets_dir(folder: str, paths: Iterable[str]) -> str:
    """Where a container's breakdown sits: its `tickets/` folder when that holds anything, else the folder itself."""
    inner = f"{folder}/{TICKETS}"
    return inner if any(p.startswith(inner + "/") for p in paths) else folder


def child_parents(breakdowns: dict[str, str]) -> dict[str, str]:
    """Each child initiative's folder and the parent initiative listing it, from tickets.toml texts by path."""
    links = {}
    for path, text in breakdowns.items():
        if "[[initiative]]" not in text:
            continue
        try:
            children = tomllib.loads(text).get("initiative", [])
        except tomllib.TOMLDecodeError:
            continue  # the ticket tree reports it
        parent = container_of_breakdown(path)
        for child in children if isinstance(children, list) else []:
            if isinstance(child, dict) and isinstance(child.get("slug"), str) and child["slug"]:
                links[posixpath.join(posixpath.dirname(parent), child["slug"])] = parent
    return links


def ancestors(folder: str, parents: dict[str, str]) -> list[str]:
    """The parent initiatives above a child, nearest first."""
    found: list[str] = []
    while folder in parents and parents[folder] not in found and parents[folder] != folder:
        folder = parents[folder]
        found.append(folder)
    return found


class Containers:
    """Container folders and their parents: an epic's parent is the nearest container above it, a child
    initiative's the parent initiative listing it."""

    def __init__(self, files: Iterable[tuple[str, str]], parents: dict[str, str]) -> None:
        self.folders = {posixpath.dirname(path) for path, artifact in files
                        if artifact in CONTAINER_TYPES and is_main_file(path)}
        self.parents = parents

    def of(self, path: str) -> str | None:
        """The nearest container folder holding a path."""
        folder = posixpath.dirname(path)
        while folder:
            if folder in self.folders:
                return folder
            folder = posixpath.dirname(folder)
        return None

    def parent(self, folder: str) -> str | None:
        return self.parents.get(folder) or self.of(folder)

    @staticmethod
    def file(folder: str) -> str:
        return f"{folder}/{posixpath.basename(folder)}.md"


def is_main_file(path: str) -> bool:
    """`<name>/<name>.md`: the file a folder is named for."""
    return posixpath.splitext(posixpath.basename(path))[0] == posixpath.basename(posixpath.dirname(path))
