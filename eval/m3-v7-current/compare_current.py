#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["tiktoken>=0.7"]
# ///
"""M3 checks of specdex on a current-layout BMad v7 corpus (one built by make_v7_current.py).

layer-a: reruns M2's Layer A (eval/m1-tamagai/run_eval.py with M2's tamagai-v7 conventions, split `all`) on a
current-layout tamagai corpus. M2's gold (eval/m2-v7/gold-tamagai-v7) gets its paths remapped through the path map
into OUT/gold/; line ranges are kept, since make_v7_current.py rewrites line content only. The results go to
OUT/layer-a-all.json, and eval/m2-v7/compare_layer_a.py compares them task by task with M2's
results-tamagai-v7 under the same map (recall, shown spans, calls and authority must match; tokens may differ).
capture: saves specdex's `status`, `lint --no-validators`, `covers` and `coverage --by tickets|architecture|ux`
(`--json`) on a corpus, one OUT/<name>.json per command, with exit codes and stderr in OUT/exit-codes.json.
Both modes run SPECDEX (default: this repository's) with an index outside the corpus, deleted afterwards.

Usage:
  uv run compare_current.py layer-a OUT [--corpus DIR] [--path-map FILE] [--specdex FILE]
  uv run compare_current.py capture CORPUS OUT [--specdex FILE]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
REPO = EVAL.parent
SPECDEX = REPO / "skills" / "specdex" / "scripts" / "specdex.py"
M1 = EVAL / "m1-tamagai"
M2 = EVAL / "m2-v7"
M2_DEF = M2 / "tamagai_v7_def.py"
M2_GOLD = M2 / "gold-tamagai-v7"
M2_RESULTS = M2 / "results-tamagai-v7" / "layer-a-all.json"
COMPARE = M2 / "compare_layer_a.py"
CORPUS = EVAL / "corpora" / "tamagai-v7-current-2026-11-11"
PATH_MAP = HERE / "path-map-tamagai.json"
SPLITS = ("dev", "heldout")
CAPTURES = {
    "status": ["status"],
    "lint": ["lint", "--no-validators"],
    "covers": ["covers"],
    "coverage-tickets": ["coverage", "--by", "tickets"],
    "coverage-architecture": ["coverage", "--by", "architecture"],
    "coverage-ux": ["coverage", "--by", "ux"],
}


def remapped_path(path: str, path_map: dict[str, str | None]) -> str:
    if path in path_map and path_map[path] is None:
        raise SystemExit(f"gold cites {path}, which the conversion removed; re-target the task by hand")
    return path_map.get(path) or path


def remapped_gold(tasks: list[dict], path_map: dict[str, str | None]) -> list[dict]:
    for task in tasks:
        for unit in task.get("evidence", []) + task.get("forbidden", []):
            unit["path"] = remapped_path(unit["path"], path_map)
        citations = task.get("citations") or {}
        for line in citations.get("lines", []):
            line["path"] = remapped_path(line["path"], path_map)
        for old, new in path_map.items():
            if new and "scope" in citations:
                citations["scope"] = citations["scope"].replace(old, new)
    return tasks


def run_layer_a(corpus: Path, gold: Path, out_file: Path, specdex: Path, db: Path) -> None:
    """M1's run_eval.py in this process with M2's tamagai-v7 corpus definition; the corpus, gold, index and
    engine it names are swapped for these before it runs."""
    sys.argv = [str(M1 / "run_eval.py"), "--corpus-def", str(M2_DEF), "--split", "all", "--out", str(out_file)]
    sys.path.insert(0, str(M1))
    import run_eval  # noqa: E402 - reads --corpus-def from sys.argv when imported

    run_eval.CORPUS, run_eval.DB, run_eval.ENGINE, run_eval.C.GOLD = corpus, db, specdex, gold
    run_eval.main()


def layer_a(args: argparse.Namespace) -> int:
    path_map = json.loads(args.path_map.read_text(encoding="utf-8"))
    gold = args.out / "gold"
    gold.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        tasks = json.loads((M2_GOLD / f"{split}.json").read_text(encoding="utf-8"))
        (gold / f"{split}.json").write_text(json.dumps(remapped_gold(tasks, path_map), indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    results = args.out / "layer-a-all.json"
    with tempfile.TemporaryDirectory() as scratch:
        run_layer_a(args.corpus.resolve(), gold, results, args.specdex.resolve(), Path(scratch) / "index.sqlite")
    print(f"\n== compare with {M2_RESULTS.relative_to(REPO)} under {args.path_map.name}", flush=True)
    return subprocess.run([sys.executable, str(COMPARE), str(results), str(M2_RESULTS), "--path-map", str(args.path_map)]).returncode


def capture(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    runs = {}
    with tempfile.TemporaryDirectory() as scratch:
        base = [sys.executable, str(args.specdex.resolve()), "--project", str(args.corpus.resolve()),
                "--db", str(Path(scratch) / "index.sqlite"), "--json"]
        for name, command in CAPTURES.items():
            done = subprocess.run(base + command, capture_output=True, text=True)
            (args.out / f"{name}.json").write_text(done.stdout, encoding="utf-8")
            runs[name] = {"command": command, "exit": done.returncode, "stderr": done.stderr.strip()}
            print(f"{name}: exit {done.returncode}")
    (args.out / "exit-codes.json").write_text(json.dumps(runs, indent=1) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    a = modes.add_parser("layer-a", help="rerun M2's Layer A and compare with results-tamagai-v7")
    a.add_argument("out", type=Path)
    a.add_argument("--corpus", type=Path, default=CORPUS)
    a.add_argument("--path-map", type=Path, default=PATH_MAP)
    c = modes.add_parser("capture", help="save status, lint, covers and coverage as JSON")
    c.add_argument("corpus", type=Path)
    c.add_argument("out", type=Path)
    for mode in (a, c):
        mode.add_argument("--specdex", type=Path, default=SPECDEX, help="specdex.py to run (default: this repository's)")
    args = parser.parse_args()
    return layer_a(args) if args.mode == "layer-a" else capture(args)


if __name__ == "__main__":
    raise SystemExit(main())
