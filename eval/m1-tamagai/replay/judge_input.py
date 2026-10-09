# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Blind judging input for the replay: per task, the gold answer and the four answers under neutral labels.

The label order rotates by task position so no condition sits under one letter; the key that maps labels
back to (harness, condition) is written separately and never shown to judges.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
SPLITS = {"dev": ("dev.json", "replay"), "heldout-paraphrase": ("heldout.json", "replay-heldout")}  # gold file, results folder
LABELS = "ABCD"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=sorted(SPLITS), default="dev")
    gold_file, folder = SPLITS[parser.parse_args().split]
    results = EVAL / "results" / folder
    out = results / "judge"
    gold = {t["id"]: t for t in json.loads((EVAL / "gold" / gold_file).read_text(encoding="utf-8"))}
    runs = json.loads((results / "replay.json").read_text(encoding="utf-8"))["runs"]
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for position, task_id in enumerate(sorted({r["task"] for r in runs})):
        answers = sorted((r for r in runs if r["task"] == task_id), key=lambda r: (r["harness"], r["condition"]))
        rotated = answers[position % len(answers):] + answers[:position % len(answers)]
        task = gold[task_id]
        lines = [f"# Task {task_id}", "", f"**Question:** {task['prompt']}", "", f"**Gold answer:** {task['answer']}", "",
                 "**Gold evidence (current record):**"]
        lines += [f"- {e['path']}:{e['start']}-{e['end']} — {e['why']}" for e in task.get("evidence") or []]
        if task.get("forbidden"):
            lines += ["", "**Non-current text that must not be presented as current:**"]
            lines += [f"- {f['path']}:{f['start']}-{f['end']} — {f['why']}" for f in task["forbidden"]]
        if task.get("notes"):
            lines += ["", f"**Labeller notes:** {task['notes']}"]
        for label, run in zip(LABELS, rotated):
            lines += ["", f"## Answer {label}", "", run["answer"].strip() or "(no answer)"]
            key[f"{task_id}:{label}"] = {"harness": run["harness"], "condition": run["condition"]}
        (out / f"{task_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out.parent / "judge-key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(key)} answers in {out}")


if __name__ == "__main__":
    main()
