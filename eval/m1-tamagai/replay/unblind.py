# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Map blind judge verdicts (from a workflow journal) back to harness and condition, and tally them.

Usage: uv run replay/unblind.py --split dev|heldout-paraphrase --journal <workflow journal.jsonl>
Writes results/<folder>/judgements.json and prints verdict counts per harness/condition.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from judge_input import EVAL, SPLITS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=sorted(SPLITS), default="dev")
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    results = EVAL / "results" / SPLITS[args.split][1]
    key = json.loads((results / "judge-key.json").read_text(encoding="utf-8"))
    labels, verdicts = {}, {}
    for line in args.journal.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "started":
            labels[event["key"]] = event["label"].split(":", 1)[1]
        elif event.get("type") == "result":
            value = event.get("result")
            verdicts[event["key"]] = json.loads(value) if isinstance(value, str) else value
    rows = []
    for agent_key, value in verdicts.items():
        task = labels[agent_key]
        for answer in value["answers"]:
            rows.append({"task": task, **key[f"{task}:{answer['label']}"],
                         **{field: answer[field] for field in ("verdict", "authority_error", "missing", "reason")}})
    rows.sort(key=lambda r: (r["task"], r["harness"], r["condition"]))
    (results / "judgements.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in rows:
        group = tally[f"{row['harness']}/{row['condition']}"]
        group[row["verdict"]] += 1
        group["authority_errors"] += row["authority_error"]
    for name in sorted(tally):
        print(name, dict(tally[name]))


if __name__ == "__main__":
    main()
