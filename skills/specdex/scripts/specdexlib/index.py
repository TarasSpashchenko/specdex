"""Open a verified index generation.

Worktree mode hashes every in-scope file on every open and re-extracts what
changed before answering (mtime and size are never trusted). Snapshot mode
indexes one commit's blobs; a commit is immutable, so a complete snapshot index
needs no re-verification. The two modes use different cache files and never mix.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__, extract, resolve, store
from .config import Config, ConfigError
from .sources import GitRevisionSource, SourceFile, WorktreeSource


@dataclass(slots=True)
class Index:
    conn: sqlite3.Connection
    config: Config
    mode: str            # "worktree" or "commit:<sha>"
    generation: str
    changed: int         # files re-extracted while opening
    verify_ms: float
    update_ms: float


def cache_path(config: Config, mode: str) -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "specdex"
    key = hashlib.sha256(f"{config.project_root.resolve()}|{mode}".encode()).hexdigest()[:16]
    return base / key / "index.sqlite"


def index_file(config: Config, mode: str, db_path: Path | None) -> Path:
    """An explicit --db holds the worktree index; each revision snapshot gets a sibling file, so two never share one.
    The index never goes inside the project, whatever --db or XDG_CACHE_HOME say: specdex writes nothing there."""
    if db_path is None:
        path = cache_path(config, mode)
    elif mode == WorktreeSource.label:
        path = db_path
    else:
        path = db_path.with_name(f"{db_path.stem}.{mode.replace(':', '-')}{db_path.suffix}")
    if path.resolve().is_relative_to(config.project_root.resolve()):
        raise ConfigError(f"index location {path} is inside the project; use --db or XDG_CACHE_HOME outside it")
    return path


def open_index(config: Config, revision: str | None = None, db_path: Path | None = None) -> Index:
    source = GitRevisionSource(config, revision) if revision else WorktreeSource(config)
    mode = source.label
    conn = store.connect(index_file(config, mode, db_path))
    stamp = f"{store.SCHEMA_VERSION}|{config.fingerprint}|{__version__}"
    started = time.perf_counter()
    # Every return leaves one read transaction open: all of a command's queries see the same generation.
    if revision and store.get_meta(conn, "stamp") == stamp and store.get_meta(conn, "complete") == "1" and store.get_meta(conn, "mode") == mode:
        conn.execute("BEGIN")
        return Index(conn, config, mode, store.get_meta(conn, "generation") or "", 0, 0.0, 0.0)
    inventory = source.files()
    verified = time.perf_counter()
    conn.execute("BEGIN")
    if _fresh(conn, stamp, inventory, source.problems):
        return Index(conn, config, mode, store.get_meta(conn, "generation") or "", 0, (verified - started) * 1000, 0.0)
    conn.execute("ROLLBACK")
    conn.execute("BEGIN IMMEDIATE")
    changed = 0
    try:
        inventory = source.files()  # re-read under the lock: the first read may predate another writer's commit
        if not _fresh(conn, stamp, inventory, source.problems):
            changed = _sync(conn, config, stamp, inventory)
            resolve.derive(conn, config, source.problems)
            store.set_meta(conn, "generation", _generation(config, inventory, source.problems))
            store.set_meta(conn, "stamp", stamp)
            store.set_meta(conn, "complete", "1")
            store.set_meta(conn, "mode", mode)
            store.set_meta(conn, "source_problems", json.dumps(source.problems))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    done = time.perf_counter()
    conn.execute("BEGIN")
    return Index(conn, config, mode, store.get_meta(conn, "generation") or "", changed, (verified - started) * 1000, (done - verified) * 1000)


def _fresh(conn: sqlite3.Connection, stamp: str, inventory: dict[str, SourceFile], problems: list) -> bool:
    if store.get_meta(conn, "stamp") != stamp or store.get_meta(conn, "complete") != "1":
        return False
    if store.get_meta(conn, "source_problems") != json.dumps(problems):
        return False
    stored = {row["path"]: (row["sha256"], row["identity"]) for row in conn.execute("SELECT path, sha256, identity FROM files")}
    return stored == {path: (source.sha256, source.identity) for path, source in inventory.items()}


def _generation(config: Config, inventory: dict[str, SourceFile], problems: list) -> str:
    digest = hashlib.sha256(config.fingerprint.encode())
    for path in sorted(inventory):
        digest.update(f"{path}\0{inventory[path].sha256}\0{inventory[path].identity}\n".encode())
    digest.update(json.dumps(problems).encode())
    return digest.hexdigest()[:12]


def _sync(conn: sqlite3.Connection, config: Config, stamp: str, inventory: dict[str, SourceFile]) -> int:
    if store.get_meta(conn, "stamp") != stamp:
        store.reset(conn)
    stored = {row["path"]: (row["sha256"], row["identity"]) for row in conn.execute("SELECT path, sha256, identity FROM files")}
    skipped = _not_extracted(config, inventory)
    stale = [p for p in stored if p not in inventory or stored[p] != (inventory[p].sha256, inventory[p].identity)
             or (p in skipped) != _was_skipped(conn, p)]
    for path in stale:
        store.delete_file(conn, path)
    remaining = set(stored) - set(stale)
    changed = 0
    for path, source in sorted(inventory.items()):
        if path in remaining:
            continue
        text = source.data.decode("utf-8", errors="replace")
        facts = None if path in skipped else extract.extract(config, path, text)
        store.write_file(conn, source, text, facts)
        changed += 1
    return changed


def _was_skipped(conn: sqlite3.Connection, path: str) -> bool:
    row = conn.execute("SELECT extracted FROM files WHERE path=?", (path,)).fetchone()
    return bool(row) and not row["extracted"]


def _not_extracted(config: Config, inventory: dict[str, SourceFile]) -> set[str]:
    """Paths indexed only as aliases: symlinks to an indexed file and equal declared replicas.
    A drifting replica is not an alias: it stays a separate document and lint reports the drift."""
    skipped = {p for p, s in inventory.items() if s.is_link and s.identity in inventory}
    for group in config.replicas:
        primary = inventory.get(group[0])
        for member in group[1:]:
            if primary and member in inventory and inventory[member].sha256 == primary.sha256:
                skipped.add(member)
    return skipped
