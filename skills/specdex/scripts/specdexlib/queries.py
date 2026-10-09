"""Read-only retrieval over a verified index generation.

Every hit carries its file, line range, heading path, role and temporal status,
so a caller never mistakes trail or historical text for a current requirement.
Empty answers say whether the scope was fully indexed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .index import Index

ROLE_ORDER = {"record": 0, "ambiguous": 1, "rationale": 2, "ticket": 3, "noncurrent": 4, "unverified": 5, "trail": 6, "memlog": 7}
SCOPES = {
    "record": ("record", "ambiguous"),
    "current": ("record", "ambiguous", "rationale", "ticket"),
    "all": tuple(ROLE_ORDER),
    "trail": ("trail",),
    "memlog": ("memlog",),
    "rationale": ("rationale",),
}
STOPWORDS = set("""a an and are as at be been being but by can could did do does doing for from had has have how i if in into is it
its me my of on or our over shall should so than that the their them then there these they this those through to under up
us was we were what when where which while who whom why will with would you your about after again all also any because before
between both each few more most no nor not now only other out own same some such too very just does don't isn't what's show tell
give find list say says said get pull see look""".split())
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9']*")
SECTION_REF = re.compile(r"^(?P<doc>[\w .-]+?)\s*§\s*(?P<number>\d+(?:\.\d+)*)$")
LINE_REF = re.compile(r"^(?P<path>[^:#]+):(?P<a>\d+)(?:-(?P<b>\d+))?$")
HEADING_REF = re.compile(r"^(?P<path>[^#]+)#(?P<heading>.+)$")
HISTORICAL_PENALTY = 0.5
SUPERSEDED_PENALTY = 0.7


class StaleIndex(Exception):
    """A file changed after the index generation was verified; reopen and retry."""


class NotFound(Exception):
    """A reference names nothing in the indexed scope."""


@dataclass(slots=True)
class Hit:
    path: str
    start: int
    end: int
    kind: str
    hpath: str
    role: str
    temporal: str = "current"
    flags: str = ""
    disposition: str | None = None
    authority: str | None = None
    label: str | None = None
    text: str | None = None
    snippet: str | None = None
    score: float | None = None

    def ref(self) -> str:
        return f"{self.path}:{self.start}-{self.end}" if self.end != self.start else f"{self.path}:{self.start}"


@dataclass(slots=True)
class Resolution:
    query: str
    status: str
    definitions: list[Hit] = field(default_factory=list)
    elaborations: list[Hit] = field(default_factory=list)
    historical: list[Hit] = field(default_factory=list)   # definitions kept only as history (retired, declined)
    children: int | None = None
    notes: list[str] = field(default_factory=list)


class Queries:
    def __init__(self, index: Index) -> None:
        self.index = index
        self.conn = index.conn
        self.files = {r["path"]: dict(r) for r in self.conn.execute(
            "SELECT path, sha256, role, artifact, canonical, superseded_by, authority_note, lines FROM files")}
        self._lines_cache: dict[str, list[str]] = {}

    # -- helpers ----------------------------------------------------------------------
    def lines(self, path: str) -> list[str]:
        if path not in self._lines_cache:
            row = self.conn.execute("SELECT text FROM files WHERE path=?", (path,)).fetchone()
            self._lines_cache[path] = row["text"].split("\n") if row else []
        return self._lines_cache[path]

    def text(self, path: str, start: int, end: int) -> str:
        return "\n".join(self.lines(path)[start - 1:end])

    def verify_live(self, path: str) -> None:
        """Re-check live bytes before returning text (worktree mode only)."""
        if self.index.mode != "worktree":
            return
        try:
            data = (self.index.config.project_root / path).read_bytes()
        except OSError as error:
            raise StaleIndex(f"{path} is no longer readable") from error
        if hashlib.sha256(data).hexdigest() != self.files[path]["sha256"]:
            raise StaleIndex(f"{path} changed since the index was verified")

    def hit_from_span(self, sid: int, label: str | None = None, with_text: bool = False) -> Hit:
        span = self.conn.execute("SELECT * FROM spans WHERE sid=?", (sid,)).fetchone()
        info = self.files[span["path"]]
        hit = Hit(span["path"], span["start"], span["end"], span["kind"], span["hpath"], info["role"], span["temporal"],
                  span["flags"] or "", span["disposition"], self._authority(span["path"], span["hpath"]), label)
        if with_text:
            self.verify_live(hit.path)
            hit.text = self.text(hit.path, hit.start, hit.end)
        return hit

    def _authority(self, path: str, hpath: str) -> str | None:
        note = self.files[path]["authority_note"]
        if not note:
            return None
        for exception in (e.strip() for e in note.split("except", 1)[1].split(",")) if "except" in note else ():
            if exception and exception in hpath:
                return "authoritative exception (" + exception + ")"
        return note

    def scope_roles(self, scope: str) -> tuple[str, ...]:
        if scope not in SCOPES:
            raise NotFound(f"unknown scope {scope!r}; use one of {', '.join(SCOPES)}")
        return SCOPES[scope]

    def scope_complete(self, roles: tuple[str, ...]) -> str | None:
        """None when the scope is fully indexed, else why an empty answer is 'unknown'."""
        gaps = self.conn.execute(
            "SELECT DISTINCT d.path FROM fdiag d JOIN files f ON f.path=d.path WHERE d.code='parse-gap' AND f.role IN (%s)"
            % ",".join("?" * len(roles)), roles).fetchall()
        if gaps:
            return "parse gaps in " + ", ".join(r["path"] for r in gaps)
        if "record" in roles and not any(f["role"] == "record" for f in self.files.values()):
            return "no current record files were found; check the profile layout or the overlay's records"
        if self.conn.execute("SELECT 1 FROM gdiag WHERE code IN ('ambiguous-current','unsupported-layout','missing-record','source-skipped') LIMIT 1").fetchone():
            return "the current artifact set is ambiguous, partly unsupported or partly unreadable (see lint)"
        return None

    def empty_answer(self, roles: tuple[str, ...]) -> str:
        gap = self.scope_complete(roles)
        return f"unknown ({gap})" if gap else "none in a fully indexed scope"

    # -- status and outline ---------------------------------------------------------------
    def status(self) -> dict:
        roles: dict[str, int] = {}
        for info in self.files.values():
            roles[info["role"] or "unverified"] = roles.get(info["role"] or "unverified", 0) + 1
        diags = [dict(r) for r in self.conn.execute("SELECT code, severity, COUNT(*) AS n FROM (SELECT code, severity FROM gdiag UNION ALL SELECT code, severity FROM fdiag) GROUP BY code, severity")]
        return {
            "mode": self.index.mode, "generation": self.index.generation, "profile": self.index.config.profile_id,
            "overlay": str(self.index.config.overlay_path) if self.index.config.overlay_path else None,
            "files": len(self.files), "roles": roles, "binding": self.binding(), "diagnostics": diags,
            "verify_ms": round(self.index.verify_ms, 1), "update_ms": round(self.index.update_ms, 1), "reindexed": self.index.changed,
        }

    def binding(self) -> dict:
        """Compare the profile's recorded hashes with the installed BMAD files."""
        config = self.index.config
        roots = [config.project_root / r for r in config.binding.get("skill_roots", [])]
        mismatched, missing = [], []
        for entry in config.binding.get("files", []):
            found = next((root / entry["path"] for root in roots if (root / entry["path"]).is_file()), None)
            if found is None:
                missing.append(entry["path"])
            elif hashlib.sha256(found.read_bytes()).hexdigest() != entry["sha256"]:
                mismatched.append(entry["path"])
        state = "verified" if not mismatched and not missing else "unverified"
        return {"state": state, "mismatched": mismatched, "missing": missing}

    def outline(self, target: str | None, max_level: int | None) -> list[dict]:
        paths = self.match_paths(target) if target else sorted(p for p, f in self.files.items() if f["role"] in SCOPES["record"])
        result = []
        for path in paths:
            rows = self.conn.execute("SELECT start, end, level, title FROM spans WHERE path=? AND kind='section' ORDER BY start", (path,)).fetchall()
            sections = [dict(r) for r in rows if max_level is None or r["level"] <= max_level]
            result.append({"path": path, "role": self.files[path]["role"], "lines": self.files[path]["lines"], "sections": sections})
        return result

    def match_paths(self, fragment: str) -> list[str]:
        fragment = fragment.strip("/")
        if fragment in self.files:
            return [fragment]
        matches = sorted(p for p in self.files if p.endswith("/" + fragment)) or sorted(p for p in self.files if p.endswith(fragment))
        if not matches:
            raise NotFound(f"no indexed file matches {fragment!r}")
        return matches

    # -- resolve and get ---------------------------------------------------------------------
    def normalize(self, raw: str) -> str:
        text = raw.strip().strip("`*")
        return self.index.config.aliases.get(text, text)

    def resolve(self, raw: str, with_text: bool = False) -> Resolution:
        ident = self.normalize(raw)
        rows = self._def_rows(ident)
        if not rows:
            rows = self._fallback_rows(ident)
        resolution = Resolution(ident, "")
        for row in rows:
            ident = row["id"]
            target = {"definition": resolution.definitions, "historical": resolution.historical}.get(row["effective"], resolution.elaborations)
            target.append(self.hit_from_span(row["sid"], f"{row['effective']} ({row['shape']})", with_text and row["effective"] == "definition"))
        count = self.conn.execute("SELECT n FROM poscount WHERE parent_id=?", (ident,)).fetchone()
        resolution.children = count["n"] if count else None
        resolution.query = ident
        resolution.status = self._status_of(ident, resolution)
        resolution.notes += self._convention_note(ident)
        return resolution

    def _convention_note(self, ident: str) -> list[str]:
        """Positional IDs depend on a project convention; say where it is stated."""
        family = self.index.config.id_regex.fullmatch(ident)
        if not family or "." not in ident:
            return []
        name = next((f for g, f in self.index.config.family_groups.items() if family.group(g)), None)
        rule = self.index.config.positional.get(name)
        if not rule or not rule.source:
            return []
        try:
            where = self._section_number(*rule.source.split("§", 1), [])[0]
            return [f"positional convention stated at {where.ref()} — {where.hpath.split(' › ')[-1]}"]
        except NotFound:
            return [f"positional convention stated in {rule.source}"]

    def _def_rows(self, ident: str) -> list:
        return self.conn.execute("SELECT * FROM defs WHERE id=? ORDER BY effective, path, line", (ident,)).fetchall()

    def _fallback_rows(self, text: str) -> list:
        rows = self.conn.execute("SELECT * FROM defs WHERE family='TERM' AND lower(id)=lower(?)", (text,)).fetchall()
        if not rows:
            rows = self.conn.execute("SELECT * FROM defs WHERE family='TOKEN' AND (id=? OR id LIKE ?)", (text, "%." + text)).fetchall()
        return rows

    def _status_of(self, ident: str, resolution: Resolution) -> str:
        if resolution.definitions and all(h.role == "ambiguous" for h in resolution.definitions):
            return "ambiguous: defined in one of several candidate current documents; choose the record in the overlay"
        if len(resolution.definitions) == 1:
            return "defined"
        if len(resolution.definitions) > 1:
            scopes = self.conn.execute("SELECT COUNT(DISTINCT scope) FROM defs WHERE id=? AND effective='definition'", (ident,)).fetchone()[0]
            return "ambiguous: several definitions in one scope" if scopes == 1 else f"ambiguous: defined in {scopes} scopes; the citing document decides"
        if resolution.historical:
            return "historical only (retired or declined; not a current definition)"
        if "." in ident:
            parent = ident.rsplit(".", 1)[0]
            count = self.conn.execute("SELECT n FROM poscount WHERE parent_id=?", (parent,)).fetchone()
            if count is not None:
                resolution.notes.append(f"{parent} has {count['n']} positional item(s)")
                return "out-of-bounds"
        if resolution.elaborations:
            return "elaborated only (no definition in the owner document)"
        return "not defined: " + self.empty_answer(SCOPES["record"])

    def get(self, ref: str, budget_chars: int) -> tuple[list[Hit], list[str]]:
        notes: list[str] = []
        hits = self._locate(ref.strip(), notes)
        total, kept = 0, []
        for hit in hits:
            self.verify_live(hit.path)
            hit.text = self.text(hit.path, hit.start, hit.end)
            if kept and total + len(hit.text) > budget_chars:
                notes.append(f"{len(hits) - len(kept)} more unit(s) over the output budget; request them by reference")
                break
            kept.append(hit)
            total += len(hit.text)
        if len(kept) == 1 and total > budget_chars:
            notes.append("the unit is larger than the output budget and is returned whole (normative units are never cut)")
        return kept, notes

    def _locate(self, ref: str, notes: list[str]) -> list[Hit]:
        line_ref = LINE_REF.match(ref)
        if line_ref:
            path = self._one_path(line_ref.group("path"))
            a = int(line_ref.group("a"))
            if line_ref.group("b"):
                return [self._range_hit(path, a, int(line_ref.group("b")))]
            return [self._unit_at(path, a)]
        section_ref = SECTION_REF.match(ref)
        if section_ref:
            return self._section_number(section_ref.group("doc"), section_ref.group("number"), notes)
        heading_ref = HEADING_REF.match(ref)
        if heading_ref and not self._looks_like_id(ref):
            path = self._one_path(heading_ref.group("path"))
            return self._headings(heading_ref.group("heading"), [path], notes)
        resolution = self.resolve(ref)
        if resolution.definitions:
            if len(resolution.definitions) > 1:
                notes.append(f"{resolution.query} is ambiguous: {len(resolution.definitions)} definitions")
            notes += [f"{resolution.query} elaborated in {h.ref()} — {h.hpath.split(' › ')[-1]}" for h in resolution.elaborations]
            return [self.hit_from_span(self._sid_of(h), h.label) for h in resolution.definitions]
        if resolution.historical:
            notes.append(f"{resolution.query} is defined only in historical text: not a current requirement")
            return [self.hit_from_span(self._sid_of(h), h.label) for h in resolution.historical]
        if resolution.status == "out-of-bounds":
            parent = self.resolve(resolution.query.rsplit(".", 1)[0])
            notes.append(f"{resolution.query} does not exist: {'; '.join(resolution.notes)}; showing the parent")
            return [self.hit_from_span(self._sid_of(h), h.label) for h in parent.definitions]
        if self._looks_like_id(ref):
            raise NotFound(f"{resolution.query}: {resolution.status}")
        hits = self._headings(ref, sorted(p for p, f in self.files.items() if f["role"] in SCOPES["record"]), notes)
        if not hits:
            raise NotFound(f"no definition, term, token or heading matches {ref!r}; try search")
        return hits

    def _section_number(self, doc_word: str, number: str, notes: list[str]) -> list[Hit]:
        """'addendum §2.8' or 'PRD §4.7': the section whose title starts with that number in the named document."""
        path = self.document(doc_word)
        rows = self.conn.execute("SELECT sid, title FROM spans WHERE path=? AND kind='section' ORDER BY start", (path,)).fetchall()
        chosen = [r for r in rows if re.match(rf"{re.escape(number)}\.?(?:\s|$)", r["title"])]  # "2" is "2." or "2 ", never "2.1"
        if not chosen:
            raise NotFound(f"no section {number} in {path}")
        return [self.hit_from_span(chosen[0]["sid"])]

    def document(self, word: str) -> str:
        """A record document named by a word (prd, addendum, spine…) or a path suffix."""
        word = word.strip().strip("`").lower()
        for artifact in self.index.config.doc_aliases.get(word, []):
            paths = [p for p, f in self.files.items() if f["artifact"] == artifact and f["role"] in SCOPES["record"]]
            if len(paths) == 1:
                return paths[0]
        return self._one_path(word)

    def _looks_like_id(self, text: str) -> bool:
        return bool(self.index.config.id_regex.fullmatch(text.strip()))

    def _sid_of(self, hit: Hit) -> int:
        return self.conn.execute("SELECT sid FROM spans WHERE path=? AND start=? AND end=? AND kind=?", (hit.path, hit.start, hit.end, hit.kind)).fetchone()["sid"]

    def _one_path(self, fragment: str) -> str:
        paths = self.match_paths(fragment)
        if len(paths) > 1:
            raise NotFound(f"{fragment!r} matches {len(paths)} files: " + ", ".join(paths[:6]))
        return paths[0]

    def _range_hit(self, path: str, start: int, end: int) -> Hit:
        """An arbitrary line range: the exact unit when it is one, else labelled by the history it overlaps."""
        end = min(end, self.files[path]["lines"] or end)
        unit = self.conn.execute("SELECT sid FROM spans WHERE path=? AND start=? AND end=? AND kind!='file' "
                                 "ORDER BY CASE kind WHEN 'row' THEN 0 WHEN 'item' THEN 1 WHEN 'section' THEN 2 ELSE 3 END LIMIT 1",
                                 (path, start, end)).fetchone()
        if unit:
            return self.hit_from_span(unit["sid"])
        row = self.conn.execute("SELECT hpath FROM spans WHERE path=? AND kind IN ('section','file') AND start<=? AND end>=? ORDER BY start DESC LIMIT 1", (path, start, start)).fetchone()
        hpath = row["hpath"] if row else path
        return Hit(path, start, end, "range", hpath, self.files[path]["role"], self._range_temporal(path, start, end), authority=self._authority(path, hpath))

    def _range_temporal(self, path: str, start: int, end: int) -> str:
        historical: set[int] = set()
        for span in self.conn.execute("SELECT start, end FROM spans WHERE path=? AND temporal='historical' AND start<=? AND end>=?", (path, end, start)):
            historical.update(range(span["start"], span["end"] + 1))
        lines = self.lines(path)
        nonblank = {n for n in range(start, end + 1) if n <= len(lines) and lines[n - 1].strip()}
        if not historical & nonblank:
            return "current"
        return "historical" if nonblank <= historical else "partly historical"

    def _unit_at(self, path: str, line: int) -> Hit:
        row = self.conn.execute(
            "SELECT sid FROM spans WHERE path=? AND start<=? AND end>=? AND kind IN ('row','item','para','yaml','section') "
            "ORDER BY CASE kind WHEN 'row' THEN 0 WHEN 'yaml' THEN 1 WHEN 'item' THEN 2 WHEN 'para' THEN 3 ELSE 4 END, (end-start) LIMIT 1",
            (path, line, line)).fetchone()
        if not row:
            return self._range_hit(path, line, line)
        return self.hit_from_span(row["sid"])

    def _headings(self, text: str, paths: list[str], notes: list[str]) -> list[Hit]:
        needle = text.strip().lower()
        rows = self.conn.execute(
            "SELECT sid, path, title FROM spans WHERE kind='section' AND path IN (%s)" % ",".join("?" * len(paths)), paths).fetchall()
        exact = [r for r in rows if r["title"].lower() == needle]
        prefix = [r for r in rows if r["title"].lower().startswith(needle)]
        contains = [r for r in rows if needle in r["title"].lower()]
        chosen = exact or prefix or contains
        if len(chosen) > 1:
            notes.append(f"{len(chosen)} headings match {text!r}; showing all")
        return [self.hit_from_span(r["sid"]) for r in chosen]

    # -- refs -----------------------------------------------------------------------------
    def refs(self, raw: str, scope: str, children: bool, kind: str | None = None) -> tuple[Resolution, list[dict], str | None]:
        resolution = self.resolve(raw)
        ident = resolution.query
        roles = self.scope_roles(scope)
        ids = [ident]
        if children:
            ids += [r["id"] for r in self.conn.execute("SELECT DISTINCT id FROM defs WHERE parent_id=?", (ident,))]
        kinds = (kind,) if kind else ("mentions", "binds", "elaborates", "covers")
        rows = self.conn.execute(
            "SELECT o.path, o.line, o.col, o.id, o.raw, o.via_range, o.kind, o.src_id, o.rule, o.status, f.role, s.temporal "
            "FROM occ o JOIN files f ON f.path=o.path LEFT JOIN spans s ON s.sid=o.sid "
            "WHERE o.id IN (%s) AND o.kind IN (%s) AND f.role IN (%s) ORDER BY o.path, o.line, o.col"
            % (",".join("?" * len(ids)), ",".join("?" * len(kinds)), ",".join("?" * len(roles))), (*ids, *kinds, *roles)).fetchall()
        seen: dict[tuple[str, int], dict] = {}
        for row in rows:
            key = (row["path"], row["line"])
            if key in seen:
                seen[key]["ids"].add(row["id"])
                continue
            seen[key] = {**dict(row), "ids": {row["id"]}, "excerpt": self._excerpt(row["path"], row["line"], row["col"])}
        found = sorted(seen.values(), key=lambda r: (ROLE_ORDER.get(r["role"], 9), r["path"], r["line"]))
        if kind in (None, "binds"):
            found = sorted(found + self.textual_bindings(ident, roles), key=lambda r: (ROLE_ORDER.get(r["role"], 9), r["path"], r["line"]))
        if kind == "covers" or (kind is None and "ticket" in roles):  # asking for covers edges means asking for tickets
            from .tickets import covers_rows
            found += covers_rows(self, ids)
        return resolution, found, None if found else self.empty_answer(roles)

    def textual_bindings(self, ident: str, roles: tuple[str, ...]) -> list[dict]:
        """Binds lines that bind by phrase ('all MVP FRs'): reported, never silently counted or dropped. A phrase
        is offered to the families it names ('FRs'), or to every family when it names none ('all requirements')."""
        family = self.conn.execute("SELECT family FROM defs WHERE id=? LIMIT 1", (ident,)).fetchone()
        if not family:
            return []
        names = [f for f in self.index.config.families if self.index.config.families[f].kind == "id"]
        rows = self.conn.execute(
            "SELECT o.path, o.line, o.col, o.id, o.raw, o.via_range, o.kind, o.src_id, o.rule, o.status, f.role, s.temporal "
            "FROM occ o JOIN files f ON f.path=o.path LEFT JOIN spans s ON s.sid=o.sid WHERE o.family='SCOPE' AND f.role IN (%s)"
            % ",".join("?" * len(roles)), roles).fetchall()
        result = []
        for r in rows:
            named = [n for n in names if re.search(rf"(?<![\w-]){re.escape(n)}s?(?![\w-])", r["raw"])]
            if not named or family["family"] in named:
                result.append({**dict(r), "ids": {ident}, "excerpt": f"binds by phrase “{r['raw'].strip()}” — read to decide whether it covers {ident}"})
        return result

    def _excerpt(self, path: str, line: int, col: int, width: int = 150) -> str:
        text = self.lines(path)[line - 1] if line <= len(self.lines(path)) else ""
        if len(text) <= width:
            return text.strip()
        start = max(0, col - width // 3)
        return ("…" if start else "") + text[start:start + width].strip() + "…"

    # -- search ---------------------------------------------------------------------------------
    def search(self, query: str, scope: str, limit: int) -> tuple[list[Hit], str | None]:
        roles = self.scope_roles(scope)
        hits: list[Hit] = []
        for match in self.index.config.id_regex.finditer(query):
            resolution = self.resolve(match.group(0))
            for hit in resolution.definitions:
                if hit.role in roles:
                    hit.label, hit.score = "exact ID", float("-inf")
                    hits.append(hit)
        hits += self._heading_mentions(query, roles)
        terms = self._terms(query)
        if terms:
            phrases = [f'"{a} {b}"' for a, b in zip(terms, terms[1:])]
            hits += self._fts(" OR ".join([f'"{t}"' for t in terms] + phrases), roles)
        ranked = self._dedupe(sorted(hits, key=lambda h: h.score))[:limit]
        return ranked, None if ranked else self.empty_answer(roles)

    def _heading_mentions(self, query: str, roles: tuple[str, ...]) -> list[Hit]:
        """A section whose heading text appears verbatim in the query ranks first (by-heading requests)."""
        normalized = " " + " ".join(WORD.findall(query.lower())) + " "
        rows = self.conn.execute(
            "SELECT s.sid, s.title FROM spans s JOIN files f ON f.path=s.path WHERE s.kind='section' AND f.role IN (%s)"
            % ",".join("?" * len(roles)), roles).fetchall()
        hits = []
        for row in rows:
            title_words = WORD.findall(re.sub(r"\(.*?\)|`[^`]*`|\[.*?\]", " ", row["title"].lower()))
            if len(title_words) >= 2 and len(" ".join(title_words)) >= 8 and f" {' '.join(title_words)} " in normalized:
                hit = self.hit_from_span(row["sid"], "heading named in the query")
                hit.score = -1e9 - len(title_words)
                hits.append(hit)
        # Keep the most specific match: drop a section that contains another matched section.
        return [h for h in hits if not any(o is not h and o.path == h.path and h.start <= o.start and o.end <= h.end for o in hits)]

    def _terms(self, query: str) -> list[str]:
        stripped = self.index.config.id_regex.sub(" ", query)
        words = [w.lower().strip("'") for w in WORD.findall(stripped)]
        return list(dict.fromkeys(w for w in words if w not in STOPWORDS and len(w) > 1))

    def _fts(self, match: str, roles: tuple[str, ...]) -> list[Hit]:
        rows = self.conn.execute(
            "SELECT c.path, c.start, c.end, c.hpath, c.sid, bm25(chunks_fts, 3.0, 1.0, 1.0) AS score, "
            "snippet(chunks_fts, 1, '«', '»', '…', 14) AS snip, f.role, s.temporal, s.flags, s.disposition, s.kind "
            "FROM chunks_fts JOIN chunks c ON c.cid=chunks_fts.rowid JOIN files f ON f.path=c.path JOIN spans s ON s.sid=c.sid "
            "WHERE chunks_fts MATCH ? AND f.role IN (%s) ORDER BY score LIMIT 60" % ",".join("?" * len(roles)),
            (match, *roles)).fetchall()
        hits = []
        for row in rows:
            score = row["score"]
            temporal = self._range_temporal(row["path"], row["start"], row["end"]) if row["temporal"] == "partly historical" else row["temporal"]
            if temporal == "historical":
                score *= HISTORICAL_PENALTY
            if self.files[row["path"]]["superseded_by"]:
                score *= SUPERSEDED_PENALTY
            hits.append(Hit(row["path"], row["start"], row["end"], row["kind"], row["hpath"], row["role"], temporal,
                            row["flags"] or "", row["disposition"], self._authority(row["path"], row["hpath"]),
                            snippet=" ".join(row["snip"].split()), score=score))
        return hits

    @staticmethod
    def _dedupe(hits: list[Hit]) -> list[Hit]:
        """One hit per region: drop a hit that contains, or lies inside, a better-ranked one."""
        kept: list[Hit] = []
        for hit in hits:
            if any(k.path == hit.path and ((k.start <= hit.start and hit.end <= k.end) or (hit.start <= k.start and k.end <= hit.end)) for k in kept):
                continue
            kept.append(hit)
        return kept
