#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Convert an October BMad v7 corpus to the current layout: bmod-method migration-2, then BMad's spec fold.

SOURCE is copied whole to TARGET (an existing TARGET is replaced), `_bmad/` and `_bmad/custom/` included, so
specdex and BMad read the same active initiative. Then, in the copy:
1. migration-2's moves. In each `initiative-*/` folder of the output folder, `tickets.toml`, `epic-*/` folders,
   leaf files (`story-`, `spike-`, `bug-*.md`) and `*-plan.md` plans move into `<initiative>/tickets/`; then in
   each epic folder, wherever it sits, its `tickets.toml`, leaves and plans move into `<epic>/tickets/`.
2. migration-2's path rewrites, in the live `.md` and `.toml` files of the output folder and `_bmad/custom/`
   (hidden files and `archive*` folders are not live). A path token that reached a moved file or folder, or that a
   moved file wrote from its old folder, is rewritten to reach the same target from where the file is now
   (`sources:`, `companions:`, `inputDocuments:`, References lines, links). A token is a path when it holds a `/`
   or is a Markdown link target, so bare names (`parent: epic-x`, `after` slugs) stay. Tokens resolve as BMad's
   fold resolves them: `{project-root}/`, `{output_folder}/`, `./` and `../` from the file's folder, any other
   from the file's folder and each folder above it. Only line content changes, so gold line ranges stay valid.
3. BMad's spec fold (`migrate_v6.py --fold-specs`, this repository's copy), when a `spec-<name>/spec-<name>.md`
   folder exists.
4. `tickets.py status` (this repository's `_bmad/method/scripts/tickets.py`) on every initiative folder.
No `template:` frontmatter is added, and files that need no rewrite keep their bytes.

PATH_MAP gets every moved file, old -> new, corpus-relative (null for a file the fold removed). SUMMARY gets the
matched folders, the item moves, each rewritten token, the files whose bytes changed or were added, globs in
`_bmad/custom/` to update by hand, references outside the output folder and `_bmad/` (never edited), the
fold's report and each status output. Exit 1 when a status check fails, a fold reports a problem or a token
cannot be rewritten.

Usage: uv run make_v7_current.py SOURCE TARGET --path-map FILE --summary FILE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TICKETS_PY = REPO / "_bmad" / "method" / "scripts" / "tickets.py"
BMAD_SKILL = REPO / ".agents" / "skills" / "bmad"
MIGRATE_V6 = BMAD_SKILL / "scripts" / "migrate_v6.py"

TICKETS = "tickets"
BREAKDOWN = "tickets.toml"
LEAF_OR_PLAN = re.compile(r"\A(?:(?:story|spike|bug)-.+|.+-plan)\.md\Z")
EPIC = re.compile(r"\Aepic-.+\Z")
INITIATIVE = re.compile(r"\Ainitiative-.+\Z")
SPEC_FOLDER = re.compile(r"\Aspec-[A-Za-z0-9][A-Za-z0-9._-]*\Z")  # migrate_v6.SPEC_FOLDER
TEXT_SUFFIXES = (".md", ".toml")
PATH_TOKEN = re.compile(r"[^\s()\[\]<>\"'`,|=:]+")  # migrate_v6.LINK_TOKEN
SENTENCE_END = ".;!?"
PROJECT_ROOT = "{project-root}/"
OUTPUT_FOLDER = "{output_folder}/"
MARKDOWN_LINK = "]("
QUOTED_GLOB = re.compile(r'"([^"\n]*[*?][^"\n]*)"')
CONFIG_LAYERS = ("config.toml", "custom/config.toml", "custom/config.user.toml")


class Unrewritable(Exception):
    pass


@dataclass
class Conversion:
    source: Path
    target: Path
    out: str                                   # the output folder, project-relative
    moves: dict[str, str]                      # item (file or folder) -> new place, project-relative

    def moved(self, path: str) -> str:
        """Where a project-relative path sits after the moves: the deepest moved item that is it or holds it decides."""
        parts = path.split("/")
        for n in range(len(parts), 0, -1):
            head = "/".join(parts[:n])
            if head in self.moves:
                return "/".join([self.moves[head], *parts[n:]])
        return path

    def resolve(self, token: str, folder: str, tree: Path, *, link: bool) -> tuple[str, str] | None:
        """(base folder, target) of a path token written in a file of `folder`, project-relative, or None when
        it reaches nothing in `tree`. A Markdown link reads from the file's folder only."""
        if token.startswith(PROJECT_ROOT):
            bases, path = [""], token.removeprefix(PROJECT_ROOT)
        elif token.startswith(OUTPUT_FOLDER):
            bases, path = [self.out], token.removeprefix(OUTPUT_FOLDER)
        elif token.startswith("/"):
            return None
        elif link or token.startswith(("./", "../")):
            bases, path = [folder], token
        else:
            bases, path = folder_and_above(folder), token
        for base in bases:
            target = posixpath.normpath(posixpath.join(base, path))
            if target != "." and target != ".." and not target.startswith("../") and (tree / target).exists():
                return base, target
        return None

    def rewritten(self, token: str, old_file: str, new_file: str, *, link: bool) -> str | None:
        """The token as the file must write it now to reach what it reached before, or None when it still does."""
        old_folder, new_folder = posixpath.dirname(old_file), posixpath.dirname(new_file)
        found = self.resolve(token, old_folder, self.source, link=link)
        if found is None:
            return None
        base, target = found
        target_now = self.moved(target)
        still = self.resolve(token, new_folder, self.target, link=link)
        if still and still[1] == target_now:
            return None
        if token.startswith(PROJECT_ROOT):
            new = PROJECT_ROOT + target_now
        elif token.startswith(OUTPUT_FOLDER):
            new = OUTPUT_FOLDER + posixpath.relpath(target_now, self.out)
        else:
            new_base = new_folder if base == old_folder else self.moved(base)
            new = posixpath.relpath(target_now, new_base or ".")
            if token.startswith("./") and not new.startswith("../"):
                new = "./" + new
        if token.endswith("/"):
            new += "/"
        check = self.resolve(new, new_folder, self.target, link=link)
        if not check or check[1] != target_now:
            raise Unrewritable(f"{new_file}: {token} (reached {target}, now {target_now})")
        return new

    def rewrite_text(self, text: str, old_file: str, new_file: str) -> tuple[str, list[list[str]]]:
        changes: list[list[str]] = []

        def swap(match: re.Match[str]) -> str:
            raw = match.group(0)
            body = raw.rstrip(SENTENCE_END)
            path, hash_, anchor = body.partition("#")
            is_link = text[max(0, match.start() - len(MARKDOWN_LINK)) : match.start()] == MARKDOWN_LINK
            if not path or ("/" not in path and not is_link):
                return raw
            new = self.rewritten(path, old_file, new_file, link=is_link)
            if new is None:
                return raw
            changes.append([path, new])
            return new + hash_ + anchor + raw[len(body):]

        return PATH_TOKEN.sub(swap, text), changes


def folder_and_above(folder: str) -> list[str]:
    bases = [folder]
    while folder:
        folder = posixpath.dirname(folder)
        bases.append(folder)
    return bases


def output_folder(project: Path) -> str:
    """`core.output_folder`, project-relative, from `_bmad/config.toml` and its custom layers (the last set wins)."""
    value = None
    for layer in CONFIG_LAYERS:
        path = project / "_bmad" / layer
        if path.is_file():
            value = tomllib.loads(path.read_text(encoding="utf-8")).get("core", {}).get("output_folder", value)
    if not value:
        raise SystemExit(f"{project}: no core.output_folder in _bmad/")
    return value.removeprefix(PROJECT_ROOT).strip("/")


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def breakdown_items(folder: Path, *, with_epics: bool) -> list[Path]:
    """What migration-2 moves out of a container folder into its `tickets/` folder."""
    return sorted(
        p for p in folder.iterdir()
        if (p.is_dir() and with_epics and EPIC.match(p.name))
        or (p.is_file() and (p.name == BREAKDOWN or LEAF_OR_PLAN.match(p.name)))
    )


def plan_moves(project: Path, out: str) -> tuple[dict[str, str], list[str]]:
    """migration-2's item moves (old -> new, project-relative) and the container folders that matched its detect."""
    root = project / out
    moves: dict[str, str] = {}
    matched: list[str] = []
    initiatives = sorted(d for d in root.iterdir() if d.is_dir() and INITIATIVE.match(d.name))
    for initiative in initiatives:
        items = breakdown_items(initiative, with_epics=True)
        if items:
            matched.append(relative(initiative, project))
        for item in items:
            moves[relative(item, project)] = f"{relative(initiative, project)}/{TICKETS}/{item.name}"
    epics = [d for folder in (root, *initiatives) for d in folder.iterdir() if d.is_dir() and EPIC.match(d.name)]
    for epic in sorted(epics):
        items = breakdown_items(epic, with_epics=False)
        if items:
            matched.append(relative(epic, project))
        epic_now = moves.get(relative(epic, project), relative(epic, project))
        for item in items:
            moves[relative(item, project)] = f"{epic_now}/{TICKETS}/{item.name}"
    return moves, matched


def apply_moves(target: Path, moves: dict[str, str]) -> None:
    """Deepest items first, each into the `tickets/` folder beside it; an epic folder moved later carries its own."""
    for old in sorted(moves, key=lambda p: (-p.count("/"), p)):
        item = target / old
        destination = item.parent / TICKETS / item.name
        if destination.exists():
            raise SystemExit(f"{relative(destination, target)} already exists")
        destination.parent.mkdir(exist_ok=True)
        item.rename(destination)


def files_under(root: Path, folder: str, *, live_text: bool = False) -> list[str]:
    """Project-relative files under `folder`; with live_text, only `.md`/`.toml`, hidden files and `archive*` out."""
    found: list[str] = []
    for current, dirs, names in os.walk(root / folder):
        if live_text:
            dirs[:] = [d for d in dirs if not d.startswith((".", "archive"))]
            names = [n for n in names if n.endswith(TEXT_SUFFIXES) and not n.startswith(".")]
        dirs.sort()
        found += [relative(Path(current) / n, root) for n in sorted(names)]
    return found


def rewrite_paths(conv: Conversion, path_map: dict[str, str]) -> tuple[dict[str, list[list[str]]], list[str]]:
    """migration-2's path rewrites; returns each rewritten file's token changes and the tokens left as they were."""
    old_of = {new: old for old, new in path_map.items()}
    rewritten: dict[str, list[list[str]]] = {}
    unrewritable: list[str] = []
    for new_file in files_under(conv.target, conv.out, live_text=True) + files_under(conv.target, "_bmad/custom", live_text=True):
        path = conv.target / new_file
        text = path.read_bytes().decode("utf-8")
        try:
            changed, changes = conv.rewrite_text(text, old_of.get(new_file, new_file), new_file)
        except Unrewritable as problem:
            unrewritable.append(str(problem))
            continue
        if changes:
            path.write_bytes(changed.encode("utf-8"))
            rewritten[new_file] = changes
    return rewritten, unrewritable


def glob_regex(glob: str, out: str) -> re.Pattern[str]:
    if glob.startswith(OUTPUT_FOLDER):
        glob = f"{out}/{glob.removeprefix(OUTPUT_FOLDER)}"
    glob = glob.removeprefix(PROJECT_ROOT)
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob)
    wildcard = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    return re.compile("".join(wildcard.get(part, re.escape(part)) for part in parts))


def stale_custom_globs(project: Path, out: str, path_map: dict[str, str]) -> list[dict]:
    """Globs in `_bmad/custom/` that matched a moved file at its old path but not at its new one."""
    stale = []
    for file in files_under(project, "_bmad/custom", live_text=True):
        for number, line in enumerate((project / file).read_text(encoding="utf-8").splitlines(), start=1):
            for glob in QUOTED_GLOB.findall(line):
                regex = glob_regex(glob, out)
                lost = [old for old, new in path_map.items() if new and regex.fullmatch(old) and not regex.fullmatch(new)]
                if lost:
                    stale.append({"file": file, "line": number, "glob": glob, "lost": len(lost), "example": lost[0]})
    return stale


def outside_references(project: Path, out: str, moves: dict[str, str]) -> list[dict]:
    """Lines outside the output folder and `_bmad/` that name a moved item's old path; migration-2 never edits them."""
    needles = sorted({form for old in moves for form in (old, old.removeprefix(f"{out}/"))})
    found = []
    for current, dirs, names in os.walk(project):
        here = relative(Path(current), project) if Path(current) != project else ""
        dirs[:] = sorted(d for d in dirs if posixpath.join(here, d) not in (".git", out, "_bmad"))
        for name in sorted(names):
            file = posixpath.join(here, name)
            try:
                lines = (project / file).read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, start=1):
                hits = [needle for needle in needles if needle in line]
                if hits:
                    found.append({"file": file, "line": number, "old": max(hits, key=len)})
    return found


def spec_folders(project: Path, out: str) -> list[str]:
    found = []
    for current, dirs, _names in os.walk(project / out):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "archive")))
        found += [relative(Path(current) / d, project) for d in dirs
                  if SPEC_FOLDER.match(d) and (Path(current) / d / f"{d}.md").is_file()]
    return found


def fold_specs(project: Path, out: str) -> tuple[dict | None, dict[str, str | None]]:
    """BMad's spec fold, when a spec folder exists: its report and where each file of a folded spec went."""
    folders = spec_folders(project, out)
    if not folders:
        return None, {}
    before = {folder: files_under(project, folder) for folder in folders}
    done = subprocess.run(["uv", "run", "--quiet", str(MIGRATE_V6), "--project-root", str(project), "--skill",
                           str(BMAD_SKILL), "--fold-specs", str(project / out)], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"migrate_v6.py --fold-specs failed: {done.stderr.strip()}")
    report = json.loads(done.stdout)
    went: dict[str, str | None] = {}
    for fold in report["folded"]:
        folder, ticket = fold["spec"], fold["ticket"]
        home = posixpath.dirname(ticket)
        for file in before[folder]:
            inside = posixpath.relpath(file, folder)
            new = ticket if inside == f"{posixpath.basename(folder)}.md" else fold["memlog"] if inside == ".memlog.md" \
                else posixpath.join(home, inside)
            went[file] = new if (project / new).exists() else None
    return report, went


def tree_status(project: Path, out: str) -> list[dict]:
    results = []
    for initiative in sorted(d for d in (project / out).iterdir() if d.is_dir() and INITIATIVE.match(d.name)):
        done = subprocess.run(["uv", "run", "--quiet", str(TICKETS_PY), "--project-root", str(project), "status",
                               str(initiative)], capture_output=True, text=True)
        try:
            output = json.loads(done.stdout)
        except json.JSONDecodeError:
            output = done.stdout
        results.append({"initiative": initiative.name, "exit": done.returncode, "status": output,
                        "stderr": done.stderr.strip()})
    return results


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def byte_changes(source: Path, target: Path, out: str, path_map: dict[str, str | None]) -> tuple[list[str], list[str]]:
    """Output-folder and `_bmad/custom/` files whose bytes differ from their source file, and files with no source."""
    old_of = {new: old for old, new in path_map.items() if new}
    changed, added = [], []
    for file in files_under(target, out) + files_under(target, "_bmad/custom"):
        old = source / old_of.get(file, file)
        if not old.is_file():
            added.append(file)
        elif digest(old) != digest(target / file):
            changed.append(file)
    return changed, added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--path-map", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.source.resolve(), args.target.resolve()
    if source == target or source.is_relative_to(target) or target.is_relative_to(source):
        raise SystemExit("SOURCE and TARGET must be separate folders")
    out = output_folder(source)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=True)

    moves, matched = plan_moves(source, out)
    conv = Conversion(source, target, out, moves)
    apply_moves(target, moves)
    moved_files = {old: conv.moved(old) for old in files_under(source, out)}
    missing = [new for new in moved_files.values() if not (target / new).is_file()]
    if missing:
        raise SystemExit(f"not where the moves put them: {missing[:5]}")
    rewritten, unrewritable = rewrite_paths(conv, {old: new for old, new in moved_files.items() if old != new})
    stale_globs = stale_custom_globs(target, out, {old: new for old, new in moved_files.items() if old != new})
    outside = outside_references(target, out, moves)

    fold, went = fold_specs(target, out)
    final = {old: went.get(new, new) for old, new in moved_files.items()}
    path_map = {old: new for old, new in final.items() if new != old}
    changed, added = byte_changes(source, target, out, path_map)
    status = tree_status(target, out)

    args.path_map.parent.mkdir(parents=True, exist_ok=True)
    args.path_map.write_text(json.dumps(path_map, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "source": source.name, "target": target.name, "output_folder": out,
        "matched_folders": matched, "item_moves": moves, "moved_files": len(path_map),
        "rewritten_tokens": rewritten, "unrewritable": unrewritable,
        "changed_files": changed, "added_files": added,
        "custom_globs_to_update": stale_globs, "outside_references": outside,
        "fold": fold, "tickets_status": status,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [s["initiative"] for s in status if s["exit"]]
    problems = (fold or {}).get("problems", [])
    print(f"{target.name}: {len(matched)} folders matched, {len(moves)} items and {len(path_map)} files moved, "
          f"{len(changed)} files changed, {len(added)} added, {len(fold['folded']) if fold else 0} specs folded; "
          f"tickets.py status exit {[s['exit'] for s in status]}")
    for line in [*unrewritable, *(f"fold problem: {p}" for p in problems), *(f"status failed: {i}" for i in failed)]:
        print(line)
    return 1 if unrewritable or problems or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
