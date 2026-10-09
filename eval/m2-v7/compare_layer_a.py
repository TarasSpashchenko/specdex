"""Compare a Layer A run with reference runs task by task (M2 v6 regression and tamagai-v7 parity).

Usage: compare_layer_a.py CANDIDATE REFERENCE [REFERENCE ...] [--path-map path-map.json]
Recall, shown spans, call counts and authority errors must match; tokens may differ (generation ids, paths, status text).
With --path-map (old path -> new path), the references' shown paths are mapped before the comparison.
"""
import argparse
import json
from pathlib import Path

EXACT_FIELDS = ("contained_recall", "top5_recall", "workflow_recall", "calls", "authority_errors")


def tasks(path: Path) -> dict:
    return {task["id"]: task for task in json.loads(path.read_text(encoding="utf-8"))["tasks"]}


def mapped(shown: dict, path_map: dict) -> dict:
    return {path_map.get(path, path): lines for path, lines in shown.items()}


def compare(candidate: dict, reference: dict, path_map: dict) -> tuple[list[str], list[int]]:
    differences, token_deltas = [], []
    for task_id, ref in reference.items():
        cand = candidate.get(task_id)
        if cand is None:
            differences.append(f"{task_id}: missing from the candidate")
            continue
        for condition, ref_score in ref["conditions"].items():
            cand_score = cand["conditions"][condition]
            for field in EXACT_FIELDS:
                if cand_score.get(field) != ref_score.get(field):
                    differences.append(f"{task_id} {condition} {field}: {ref_score.get(field)} -> {cand_score.get(field)}")
            if cand_score["shown"] != mapped(ref_score["shown"], path_map):
                differences.append(f"{task_id} {condition} shown spans differ")
            token_deltas.append(cand_score["tokens"] - ref_score["tokens"])
    return differences, token_deltas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("candidate", type=Path)
    parser.add_argument("references", type=Path, nargs="+")
    parser.add_argument("--path-map", type=Path)
    args = parser.parse_args()
    path_map = json.loads(args.path_map.read_text(encoding="utf-8")) if args.path_map else {}
    reference = {}
    for path in args.references:
        reference.update(tasks(path))
    differences, deltas = compare(tasks(args.candidate), reference, path_map)
    print(f"{len(reference)} tasks, {len(deltas)} task-conditions compared; {len(differences)} differences")
    print(*differences, sep="\n")
    print(f"token delta per task-condition: min {min(deltas)}, max {max(deltas)}, "
          f"changed {sum(1 for d in deltas if d)}/{len(deltas)}")


if __name__ == "__main__":
    main()
