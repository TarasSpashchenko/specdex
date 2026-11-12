"""SQLite store: per-file facts plus derived (whole-corpus) tables.

Per-file tables are replaced when a file changes; derived tables are rebuilt by
resolve.derive() in the same transaction, so readers always see one coherent
generation. The database is a disposable cache: deleting it loses nothing.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import ConfigError
from .extract import FileFacts
from .sources import SourceFile

SCHEMA_VERSION = 8  # stored in PRAGMA user_version; a different value rebuilds the tables
APPLICATION_ID = 0x53445831  # "SDX1" in PRAGMA application_id: marks a file as a specdex index

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(
  path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size INTEGER, identity TEXT, is_link INTEGER,
  artifact TEXT, kind TEXT, scope_kind TEXT, lines INTEGER, frontmatter TEXT, text TEXT,
  extracted INTEGER DEFAULT 0,
  role TEXT, canonical TEXT, companion_of TEXT, superseded_by TEXT, authority_note TEXT, part_of TEXT);
CREATE TABLE IF NOT EXISTS spans(
  sid INTEGER PRIMARY KEY, path TEXT, ord INTEGER, kind TEXT, start INTEGER, end INTEGER, level INTEGER,
  title TEXT, hpath TEXT, temporal TEXT, flags TEXT, disposition TEXT);
CREATE INDEX IF NOT EXISTS spans_path ON spans(path, ord);
CREATE TABLE IF NOT EXISTS chunks(cid INTEGER PRIMARY KEY, path TEXT, sid INTEGER, start INTEGER, end INTEGER, hpath TEXT, body TEXT, terms TEXT);
CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  hpath, body, terms, content='chunks', content_rowid='cid', tokenize='porter unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS occ(
  oid INTEGER PRIMARY KEY, path TEXT, line INTEGER, col INTEGER, family TEXT, id TEXT, raw TEXT,
  via_range INTEGER, sid INTEGER, kind TEXT, src_id TEXT, rule TEXT, derived INTEGER DEFAULT 0,
  target INTEGER, status TEXT);
CREATE INDEX IF NOT EXISTS occ_id ON occ(id);
CREATE INDEX IF NOT EXISTS occ_path ON occ(path, line);
CREATE TABLE IF NOT EXISTS cand(
  cid INTEGER PRIMARY KEY, path TEXT, role TEXT, id TEXT, family TEXT, shape TEXT, sid INTEGER, line INTEGER,
  parent_id TEXT, ordinal INTEGER, grp INTEGER, withdrawn INTEGER, documents TEXT, sentence INTEGER);
CREATE INDEX IF NOT EXISTS cand_path ON cand(path);
CREATE TABLE IF NOT EXISTS defs(
  did INTEGER PRIMARY KEY, id TEXT, family TEXT, scope TEXT, path TEXT, line INTEGER, sid INTEGER, shape TEXT,
  effective TEXT, parent_id TEXT, ordinal INTEGER);
CREATE INDEX IF NOT EXISTS defs_id ON defs(id);
CREATE TABLE IF NOT EXISTS poscount(path TEXT, parent_id TEXT, n INTEGER);
CREATE TABLE IF NOT EXISTS backtick(path TEXT, line INTEGER, col INTEGER, word TEXT, sid INTEGER);
CREATE TABLE IF NOT EXISTS companions(path TEXT, value TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS fdiag(path TEXT, code TEXT, severity TEXT, line INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS gdiag(code TEXT, severity TEXT, path TEXT, line INTEGER, detail TEXT);
"""

PER_FILE_TABLES = ("spans", "occ", "cand", "poscount", "backtick", "companions", "fdiag")
OWN_TABLES = {"meta", "files", "chunks", "defs", "gdiag", *PER_FILE_TABLES}


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60, isolation_level=None)
    conn.row_factory = sqlite3.Row
    outdated = conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
    if outdated and not _is_ours(conn):  # checked before any PRAGMA that would change a foreign file
        conn.close()
        raise ConfigError(f"{path} is not a specdex index; refusing to rebuild it (choose another --db)")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    if outdated:
        _create_schema(conn)
    return conn


def _is_ours(conn: sqlite3.Connection) -> bool:
    """Marked as specdex, or holding no table except specdex's own (an index from before the marker, or empty)."""
    if conn.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID:
        return True
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return all(name in OWN_TABLES or name.startswith("chunks_fts") for name in tables)


def _create_schema(conn: sqlite3.Connection) -> None:
    """Drop whatever an older version left and create the current tables, in one transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:  # another process may have won
            names = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'chunks_fts_%'")]
            for name in names:
                conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            for statement in filter(str.strip, SCHEMA.split(";")):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def reset(conn: sqlite3.Connection) -> None:
    """Drop every row (used when the schema, profile or project settings changed)."""
    for table in ("files", "chunks", "defs", "gdiag", "meta") + PER_FILE_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")


def delete_file(conn: sqlite3.Connection, path: str) -> None:
    for table in PER_FILE_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE path=?", (path,))
    rows = conn.execute("SELECT cid, hpath, body, terms FROM chunks WHERE path=?", (path,)).fetchall()
    for row in rows:
        conn.execute("INSERT INTO chunks_fts(chunks_fts, rowid, hpath, body, terms) VALUES('delete', ?, ?, ?, ?)",
                     (row["cid"], row["hpath"], row["body"], row["terms"]))
    conn.execute("DELETE FROM chunks WHERE path=?", (path,))
    conn.execute("DELETE FROM files WHERE path=?", (path,))


def write_file(conn: sqlite3.Connection, source: SourceFile, text: str, facts: FileFacts | None) -> None:
    """Insert one file; facts is None for an alias or replica whose canonical copy is indexed."""
    if facts is None:
        conn.execute("INSERT INTO files(path, sha256, size, identity, is_link, text, extracted) VALUES(?,?,?,?,?,?,0)",
                     (source.path, source.sha256, len(source.data), source.identity, int(source.is_link), text))
        return
    simple = {k: v for k, v in facts.frontmatter.items() if not k.startswith("__")}
    conn.execute(
        "INSERT INTO files(path, sha256, size, identity, is_link, artifact, kind, scope_kind, lines, frontmatter, text, extracted)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
        (source.path, source.sha256, len(source.data), source.identity, int(source.is_link), facts.artifact, facts.kind,
         facts.scope_kind, facts.lines, json.dumps(simple, ensure_ascii=False), text))
    first = conn.execute("SELECT COALESCE(MAX(sid), 0) + 1 FROM spans").fetchone()[0]
    conn.executemany(
        "INSERT INTO spans(sid, path, ord, kind, start, end, level, title, hpath, temporal, flags, disposition) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(first + i, source.path, i, s.kind, s.start, s.end, s.level, s.title, s.hpath, s.temporal, ",".join(s.flags), s.disposition)
         for i, s in enumerate(facts.spans)])
    conn.executemany(
        "INSERT INTO occ(path, line, col, family, id, raw, via_range, sid, kind, src_id, rule) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [(source.path, o.line, o.col, o.family, o.id, o.raw, int(o.via_range), first + o.span, o.kind, o.src_id, o.rule)
         for o in facts.occurrences])
    conn.executemany(
        "INSERT INTO cand(path, role, id, family, shape, sid, line, parent_id, ordinal, grp, withdrawn, documents, sentence) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(source.path, role, c.id, c.family, c.shape, first + c.span, c.line, c.parent_id, c.ordinal, c.group, int(c.withdrawn),
          c.documents, int(c.sentence))
         for role, group in (("definition", facts.definitions), ("elaboration", facts.elaborations)) for c in group])
    conn.executemany("INSERT INTO poscount(path, parent_id, n) VALUES(?,?,?)",
                     [(source.path, parent, n) for parent, n in facts.positional_counts.items()])
    conn.executemany("INSERT INTO backtick(path, line, col, word, sid) VALUES(?,?,?,?,?)",
                     [(source.path, line, col, word, first + span) for line, col, word, span in facts.backtick_words])
    conn.executemany("INSERT INTO companions(path, value, line) VALUES(?,?,?)",
                     [(source.path, value, line) for value, line in facts.companions])
    conn.executemany("INSERT INTO fdiag(path, code, severity, line, detail) VALUES(?,?,?,?,?)",
                     [(source.path, code, severity, line, detail) for code, severity, line, detail in facts.diagnostics])
    for chunk in facts.chunks:
        terms = chunk.terms
        cursor = conn.execute("INSERT INTO chunks(path, sid, start, end, hpath, body, terms) VALUES(?,?,?,?,?,?,?)",
                              (source.path, first + chunk.span, chunk.start, chunk.end, chunk.hpath, chunk.body, terms))
        conn.execute("INSERT INTO chunks_fts(rowid, hpath, body, terms) VALUES(?,?,?,?)", (cursor.lastrowid, chunk.hpath, chunk.body, terms))
