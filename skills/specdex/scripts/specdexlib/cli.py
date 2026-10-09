"""Command-line interface. Every command is read-only with respect to the project."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, render
from .config import Config, ConfigError, listing_matcher, load, read_project_config, select_profile, worktree_matcher
from .index import open_index
from .queries import NotFound, Queries, StaleIndex
from .sources import SourceError, run_git

SKILL_ROOT = Path(__file__).resolve().parents[2]
PROFILES = sorted((SKILL_ROOT / "assets").glob("profile-*.toml"))
LEGACY_OVERLAY = Path("_bmad/custom/specdex-overlay.toml")
EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_CONFIG = 0, 1, 2, 3
CHARS_PER_TOKEN = 4


def find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "_bmad").is_dir():
            return candidate
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def load_config(project: Path, profile: Path | None = None, overlay: Path | None = None, revision: str | None = None) -> Config:
    """The project's configuration: the given or layout-selected profile, BMad customization and any legacy overlay.
    With a git revision, the profile is selected by that revision's layout (the project may have migrated since)."""
    project_config = read_project_config(project)
    if profile is not None:
        reason = "--profile"
    elif revision:
        listing = run_git(project, "ls-tree", "-r", "-z", "--name-only", revision).decode("utf-8", "replace").split("\0")
        profile, reason = select_profile(PROFILES, project_config, listing_matcher(listing), use_config_keys=False)
        reason += f" at {revision}"
    else:
        profile, reason = select_profile(PROFILES, project_config, worktree_matcher(project))
    legacy = overlay or (project / LEGACY_OVERLAY if (project / LEGACY_OVERLAY).is_file() else None)
    return load(project, profile, legacy, skill_root=SKILL_ROOT, profile_reason=reason,
                legacy_default_overlay=overlay is None and legacy is not None, project_config=project_config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specdex", description="Read-only search and checks for BMAD specifications.")
    parser.add_argument("--version", action="version", version=f"specdex {__version__}")
    parser.add_argument("--project", type=Path, help="project root (default: nearest folder with _bmad/)")
    parser.add_argument("--profile", type=Path, help="BMAD profile TOML (default: chosen by the project's layout)")
    parser.add_argument("--overlay", type=Path, help=f"legacy overlay TOML (default: {LEGACY_OVERLAY} if present; deprecated)")
    parser.add_argument("--rev", help="index this git revision (committed-snapshot mode) instead of the worktree")
    parser.add_argument("--db", type=Path, help="worktree index file; revision snapshots go next to it (default: under ~/.cache/specdex)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="index generation, roles, profile binding, diagnostics")
    p = sub.add_parser("outline", help="heading tree with line ranges")
    p.add_argument("target", nargs="?", help="file path or suffix (default: all record files)")
    p.add_argument("--level", type=int, help="deepest heading level to show")
    p = sub.add_parser("resolve", help="where an ID, glossary term or token is defined and elaborated")
    p.add_argument("id")
    p.add_argument("--text", action="store_true", help="include the definition text")
    p = sub.add_parser("get", help="complete unit text: ID, term, token, path:line, path:start-end or path#heading")
    p.add_argument("ref", nargs="+")
    p.add_argument("--budget", type=int, default=2000, help="output budget in tokens (a single unit is never cut)")
    p = sub.add_parser("refs", help="every line citing an ID, including inside ranges")
    p.add_argument("id")
    p.add_argument("--scope", default="record", help="record | current | rationale | trail | memlog | all")
    p.add_argument("--children", action="store_true", help="include positional children (FR-7 → FR-7.k)")
    p.add_argument("--kind", choices=("mentions", "binds", "elaborates", "covers"), help="only this edge kind")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=60)
    p = sub.add_parser("search", help="ranked full-text search over sections and rows")
    p.add_argument("query", nargs="+")
    p.add_argument("--scope", default="record")
    p.add_argument("-k", type=int, default=5, help="number of hits")
    p.add_argument("--expand", type=int, default=0, help="include full text of the top N hits")
    from . import maintenance
    maintenance.add_commands(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = (args.project or find_project_root(Path.cwd())).resolve()
    try:
        config = load_config(project, args.profile, args.overlay, args.rev)
    except (ConfigError, OSError, SourceError) as error:
        print(f"specdex: configuration error: {error}", file=sys.stderr)
        return EXIT_CONFIG
    for attempt in range(2):
        try:
            index = open_index(config, args.rev, args.db)
            try:
                return run(args, Queries(index))
            finally:
                index.conn.close()  # ends the read snapshot before a retry opens a fresh one
        except StaleIndex as error:
            if attempt:
                print(f"specdex: {error}", file=sys.stderr)
                return EXIT_USAGE
        except NotFound as error:
            print(f"specdex: {error}", file=sys.stderr)
            return EXIT_USAGE
        except (SourceError, ConfigError) as error:
            print(f"specdex: {error}", file=sys.stderr)
            return EXIT_CONFIG
    return EXIT_USAGE


def emit(args, value, text: str) -> None:
    print(render.to_json(value) if args.json else text)


def run(args, q: Queries) -> int:
    generation = q.index.generation
    if args.command == "status":
        status = q.status()
        emit(args, status, render.status_text(status))
    elif args.command == "outline":
        files = q.outline(args.target, args.level)
        emit(args, files, render.outline_text(files, generation))
    elif args.command == "resolve":
        resolution = q.resolve(" ".join([args.id]), with_text=args.text)
        emit(args, resolution, render.resolution_text(resolution, generation))
        return EXIT_OK if resolution.status == "defined" else EXIT_FINDINGS
    elif args.command == "get":
        hits, notes = [], []
        for ref in args.ref:
            found, more = q.get(ref, args.budget * CHARS_PER_TOKEN)
            hits += found
            notes += more
        emit(args, {"hits": hits, "notes": notes, "generation": generation}, render.hits_text(hits, notes, generation))
    elif args.command == "refs":
        resolution, rows, empty = q.refs(args.id, args.scope, args.children, args.kind)
        emit(args, {"resolution": resolution, "lines": rows, "empty": empty, "generation": generation},
             render.refs_text(resolution, rows, empty, args.page, args.size, generation))
    elif args.command == "search":
        hits, empty = q.search(" ".join(args.query), args.scope, args.k)
        for hit in hits[: args.expand]:
            q.verify_live(hit.path)
            hit.text = q.text(hit.path, hit.start, hit.end)
        notes = [f"no hits: {empty}"] if empty else []
        emit(args, {"hits": hits, "notes": notes, "generation": generation}, render.hits_text(hits, notes, generation))
    else:
        from . import maintenance
        return maintenance.run(args, q)
    return EXIT_OK
