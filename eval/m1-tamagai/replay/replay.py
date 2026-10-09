# /// script
# requires-python = ">=3.11"
# dependencies = ["tiktoken>=0.7"]
# ///
"""Agent replay: real agents answer a frozen subset of dev tasks with and without specdex.

Harnesses: Claude Code headless (`claude -p`, stream-json) and Codex (`codex exec --json`).
Conditions: `baseline` (the corpus copy as is: rg, grep and file reads) and `specdex`
(the skill installed in the copy, plus one sentence saying so). Both get the same prompt
otherwise. Measured: tokens of tool calls and tool output the agent received (o200k_base),
calls, the harness's own usage, the model each run used, evidence overlap with gold, and isolation
violations. Answer correctness is judged separately and blind: replay/judge_input.py writes the judge
input from results/replay/replay.json.

Measured boundary: tool calls and their results only. Claude: every tool_use input, every tool_result
and each loaded skill body. Codex: every completed tool-like item (shell commands with their output;
MCP and collaboration tool calls, web searches and file changes as JSON). The system prompt, the
session context the harness injects (instructions, skill listings), the prompt, reasoning and the
answer are outside tool_tokens; the harness's own usage is recorded separately.

Scoring: `evidence_overlap` is the share of gold units that a cited range in the same file overlaps
(agents cite lines, not whole units, so one overlapping line earns the unit; it is not the Layer A
containment metric). Citations are set recall and precision over (path, line), ranges expanded. A cited
path must resolve by suffix to exactly one corpus file; an ambiguous or unknown path earns nothing.
`--rescore` recomputes scoring and tool accounting from the saved answers and transcripts and keeps the
isolation violations recorded at run time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Callable
from functools import cache
from pathlib import Path

import tiktoken

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
REPO = EVAL.parents[1]
CORPUS = REPO / "eval" / "corpora" / "tamagai-2026-10-04"
SKILL = REPO / "skills" / "specdex"
OVERLAY = EVAL / "overlay.toml"


@dataclass(frozen=True, slots=True)
class Split:
    gold: Path
    results: Path
    pick: Callable[[int, dict], bool]   # (position by id, task) -> part of the replay?

    @property
    def transcripts(self) -> Path:
        return self.results / "transcripts"


SPLITS = {
    # Frozen subset rule: every third dev task by id (index 0, 3, 6, …).
    "dev": Split(EVAL / "gold" / "dev.json", EVAL / "results" / "replay", lambda n, t: n % TASK_STRIDE == 0),
    # Post-hoc diagnostic after the single held-out run: the 8 paraphrases, nothing tuned on it.
    "heldout-paraphrase": Split(EVAL / "gold" / "heldout.json", EVAL / "results" / "replay-heldout", lambda n, t: t["category"] == "paraphrase"),
}
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
ENCODING = tiktoken.get_encoding("o200k_base")

TASK_STRIDE = 3            # frozen subset rule: every third dev task by id (index 0, 3, 6, …)
CLAUDE_MODEL = "claude-sonnet-5-5"
CODEX_MODEL = "gpt-6.1-sol"  # the model the recorded runs used; pinned so reruns compare like with like
RUN_TIMEOUT_S = 900
WORKERS = 4
SPECDEX_CLI = "python3 .claude/skills/specdex/scripts/specdex.py"
READ_ONLY_BASH = ["rg", "grep", "sed", "head", "tail", "cat", "ls", "find", "wc", "awk"]
SKILL_BODY_PREFIX = "Base directory for this skill:"
REF = re.compile(r"([\w./-]+\.(?:md|toml)):(\d+)(?:\s*[-–]\s*(\d+))?")
CODEX_NON_TOOL_ITEMS = {"agent_message", "reasoning", "todo_list", "error"}
SAVED_FIELDS = ("task", "harness", "condition", "answer", "violations", "error")  # kept by --rescore

PROMPT = """You are answering a question about this project's BMAD specifications (the files under _bmad-output/).
Work only inside the current directory and do not modify any file.
Answer in two to six sentences. Then, under a line "Evidence:", list each supporting passage as path:start-end (paths relative to this directory), one per line.

Question: {question}"""
SPECDEX_NOTE = {"claude": "The specdex skill (.claude/skills/specdex/SKILL.md) is installed for spec lookups.",
                "codex": "The specdex skill (.agents/skills/specdex/SKILL.md) is installed for spec lookups."}


@dataclass(slots=True)
class Run:
    task: str
    harness: str
    condition: str
    answer: str = ""
    model: str = ""
    calls: int = 0
    tool_tokens: int = 0
    harness_usage: dict = field(default_factory=dict)
    specdex_calls: int = 0
    guide_tokens: int = 0     # reading the skill guide (SKILL.md) once; included in tool_tokens
    evidence_overlap: float = 0.0
    citation_recall: float | None = None     # citation tasks only: set recall/precision over (path, line)
    citation_precision: float | None = None
    cited: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    error: str | None = None


def tokens(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


def frozen_tasks(split: Split) -> list[dict]:
    tasks = sorted(json.loads(split.gold.read_text(encoding="utf-8")), key=lambda t: t["id"])
    return [t for n, t in enumerate(tasks) if split.pick(n, t)]


# -- workspaces -----------------------------------------------------------------------------
def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        digest.update(f"{path.relative_to(root)}\0".encode() + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def is_specdex_call(payload: str) -> bool:
    return "scripts/specdex.py" in payload or '"skill": "specdex"' in payload


def is_guide_read(payload: str) -> bool:
    return "specdex/SKILL.md" in payload or '"skill": "specdex"' in payload


def prepare(base: Path, condition: str) -> Path:
    workspace = base / f"ws-{condition}"  # neutral names: a path must never look like a specdex call
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(CORPUS, workspace, symlinks=True)
    if condition == "specdex":
        for skills in (".claude/skills", ".agents/skills"):
            target = workspace / skills / "specdex"
            if target.is_symlink() or target.exists():
                continue
            shutil.copytree(SKILL, target, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(OVERLAY, workspace / "_bmad" / "custom" / "specdex-overlay.toml")
        subprocess.run(SPECDEX_CLI.split() + ["status"], cwd=workspace, capture_output=True, check=True)  # warm the cache index
    return workspace


# -- harnesses ------------------------------------------------------------------------------
def claude_command(prompt: str) -> list[str]:
    allowed = [f"Bash({tool} *)" for tool in READ_ONLY_BASH] + [f"Bash({SPECDEX_CLI} *)"]
    return ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--tools", "Bash,Read,Grep,Glob,Skill",
            "--allowedTools", *allowed, "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence",
            "--model", CLAUDE_MODEL]


def parse_claude(lines: list[str], run: Run) -> list[str]:
    """Tool accounting from a stream-json transcript; returns the tool calls' payloads."""
    guide_ids, payloads = set(), []
    for line in lines:
        event = json.loads(line)
        if event.get("type") == "system" and event.get("subtype") == "init":
            run.model = event.get("model", "")
        elif event.get("type") == "assistant":
            for block in event["message"]["content"]:
                if block.get("type") == "tool_use":
                    payload = json.dumps({"name": block["name"], **block["input"]}, ensure_ascii=False)
                    run.calls += 1
                    run.tool_tokens += tokens(payload)
                    run.specdex_calls += is_specdex_call(payload)
                    if is_guide_read(payload):
                        guide_ids.add(block["id"])
                    payloads.append(payload)
        elif event.get("type") == "user":
            for block in event["message"]["content"]:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").startswith(SKILL_BODY_PREFIX):
                    used = tokens(block["text"])  # a loaded skill's body arrives as its own message after the Skill call
                    run.tool_tokens += used
                    run.guide_tokens += used if "/specdex" in block["text"].split("\n", 1)[0] else 0
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content")
                    used = tokens(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
                    run.tool_tokens += used
                    run.guide_tokens += used if block.get("tool_use_id") in guide_ids else 0
        elif event.get("type") == "result":
            run.answer = event.get("result") or ""
            run.harness_usage = {"usage": event.get("usage"), "num_turns": event.get("num_turns"), "cost_usd": event.get("total_cost_usd")}
    return payloads


def codex_command(workspace: Path, last: Path) -> list[str]:
    return ["codex", "exec", "-m", CODEX_MODEL, "-s", "danger-full-access", "-C", str(workspace), "--color", "never", "--json",
            "--skip-git-repo-check", "-o", str(last), "-"]


def parse_codex(lines: list[str], run: Run) -> list[str]:
    """Tool accounting from a `codex exec --json` transcript; returns the tool calls' payloads."""
    payloads = []
    for line in lines:
        event = json.loads(line)
        item = event.get("item") or {}
        if event.get("type") == "thread.started":
            run.model = codex_model(event["thread_id"])
        elif event.get("type") == "item.completed" and item.get("type") not in CODEX_NON_TOOL_ITEMS:
            call, output = codex_tool_io(item)
            run.calls += 1
            run.tool_tokens += tokens(call) + tokens(output)
            run.specdex_calls += is_specdex_call(call)
            run.guide_tokens += tokens(output) if is_guide_read(call) else 0
            payloads.append(call)
        elif event.get("type") == "turn.completed":
            run.harness_usage = {"usage": event.get("usage")}
    return payloads


def codex_tool_io(item: dict) -> tuple[str, str]:
    """A tool-like item's call and result: a shell command and its output, or any other tool item as JSON."""
    if item["type"] == "command_execution":
        return item.get("command", ""), item.get("aggregated_output", "")
    call = json.dumps({k: v for k, v in item.items() if k not in ("id", "status", "result")}, ensure_ascii=False)
    return call, json.dumps(item["result"], ensure_ascii=False) if item.get("result") is not None else ""


def codex_model(thread_id: str) -> str:
    """The model Codex recorded for a thread: the turn context in its session file (the events carry only the thread id)."""
    for path in CODEX_SESSIONS.rglob(f"rollout-*-{thread_id}.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("type") == "turn_context":
                return event["payload"].get("model", "unknown")
    return "unknown"


PARSERS = {"claude": parse_claude, "codex": parse_codex}


def outside_paths(text: str, workspace: Path) -> list[str]:
    """Absolute paths the agent touched outside its workspace (its own cache and tool homes excepted)."""
    allowed = (str(workspace), "/dev/null", "/usr/", "/bin/", str(Path.home() / ".cache" / "specdex"), str(Path.home() / ".codex"))
    found = re.findall(r"(?<![\w.])(/(?:home|tmp|etc|root|var)/[^\s'\"),;]*)", text)
    return [p for p in found if not p.startswith(allowed)]


def transcript_stem(run: Run, split: Split) -> Path:
    return split.transcripts / f"{run.harness}-{run.condition}-{run.task}"


def json_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("{")]


def run_one(task: dict, harness: str, condition: str, workspace: Path, split: Split) -> Run:
    run = Run(task["id"], harness, condition)
    prompt = PROMPT.format(question=task["prompt"]) + ("\n\n" + SPECDEX_NOTE[harness] if condition == "specdex" else "")
    stem = transcript_stem(run, split)
    try:
        if harness == "claude":
            proc = subprocess.run(claude_command(prompt), cwd=workspace, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=RUN_TIMEOUT_S)
        else:
            proc = subprocess.run(codex_command(workspace, stem.with_suffix(".last.txt")), input=prompt, capture_output=True, text=True, timeout=RUN_TIMEOUT_S)
        stem.with_suffix(".jsonl").write_text(proc.stdout, encoding="utf-8")
        payloads = PARSERS[harness](json_lines(proc.stdout), run)
        run.violations = [path for payload in payloads for path in outside_paths(payload, workspace)]
        if harness == "codex" and stem.with_suffix(".last.txt").exists():
            run.answer = stem.with_suffix(".last.txt").read_text(encoding="utf-8")
        if proc.returncode != 0:
            run.error = f"exit {proc.returncode}: {proc.stderr.strip()[-300:]}"
    except subprocess.TimeoutExpired:
        run.error = "timeout"
    score(run, task)
    return run


# -- scoring --------------------------------------------------------------------------------------
@cache
def corpus_files() -> tuple[str, ...]:
    return tuple(sorted(p.relative_to(CORPUS).as_posix() for p in CORPUS.rglob("*") if p.is_file()))


def resolve_path(cited: str) -> str | None:
    """The one corpus file a cited path names by suffix; None when no file or several files match."""
    cited = cited.removeprefix("./")
    matches = [p for p in corpus_files() if p == cited or p.endswith("/" + cited)]
    return matches[0] if len(matches) == 1 else None


def cited_ranges(answer: str) -> list[tuple[str, str | None, int, int]]:
    """(cited path, resolved corpus path or None, start, end) for every path:line reference in an answer."""
    return [(m.group(1), resolve_path(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))) for m in REF.finditer(answer)]


def score(run: Run, task: dict) -> None:
    run.cited, run.evidence_overlap = score_evidence(run.answer, task)
    if task.get("citations"):
        run.citation_recall, run.citation_precision = score_citations(run.answer, task["citations"]["lines"])


def score_evidence(answer: str, task: dict) -> tuple[list[str], float]:
    """evidence_overlap: the share of gold units that a cited range of the same corpus file overlaps."""
    cited = cited_ranges(answer)
    units = task.get("evidence") or []
    hit = sum(any(path == unit["path"] and start <= unit["end"] and end >= unit["start"] for _, path, start, end in cited)
              for unit in units)
    return [f"{raw}:{a}-{b}" for raw, _, a, b in cited], round(hit / len(units), 3) if units else 1.0


def score_citations(answer: str, gold_lines: list[dict]) -> tuple[float, float]:
    """Cited lines (ranges expanded) against the gold citing lines; an unresolved path still counts as cited."""
    gold = {(g["path"], g["line"]) for g in gold_lines}
    got = {(path or raw, line) for raw, path, start, end in cited_ranges(answer) for line in range(start, end + 1)}
    hit = len(gold & got)
    return round(hit / len(gold), 3), round(hit / len(got), 3) if got else 0.0


def summarize(runs: list[Run]) -> dict:
    groups: dict[str, list[Run]] = {}
    for run in runs:
        groups.setdefault(f"{run.harness}/{run.condition}", []).append(run)
    summary = {}
    for name, members in sorted(groups.items()):
        cites = [r for r in members if r.citation_recall is not None]
        summary[name] = {
            "runs": len(members), "errors": sum(bool(r.error) for r in members),
            "median_tool_tokens": statistics.median(r.tool_tokens for r in members),
            "median_tool_tokens_without_guide": statistics.median(r.tool_tokens - r.guide_tokens for r in members),
            "median_calls": statistics.median(r.calls for r in members),
            "used_specdex": sum(r.specdex_calls > 0 for r in members),
            "mean_evidence_overlap": round(statistics.mean(r.evidence_overlap for r in members if r.citation_recall is None), 3),
            "mean_citation_recall": round(statistics.mean(r.citation_recall for r in cites), 3) if cites else None,
            "mean_citation_precision": round(statistics.mean(r.citation_precision for r in cites), 3) if cites else None,
            "violations": sum(len(r.violations) for r in members),
        }
    return summary


def write_report(report: dict, runs: list[Run], split: Split) -> None:
    models = {h: sorted({r.model for r in runs if r.harness == h}) for h in sorted({r.harness for r in runs})}
    report |= {"models": models, "summary": summarize(runs), "runs": [asdict(r) for r in runs]}
    (split.results / "replay.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")


def rescore(tasks: list[dict], split: Split) -> int:
    """Score saved answers and re-count tool use from the saved transcripts (no agent runs)."""
    report = json.loads((split.results / "replay.json").read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in tasks}
    runs = []
    for raw in report["runs"]:
        run = Run(**{k: raw[k] for k in SAVED_FIELDS})
        PARSERS[run.harness](json_lines(transcript_stem(run, split).with_suffix(".jsonl").read_text(encoding="utf-8")), run)
        score(run, by_id[run.task])
        runs.append(run)
    write_report(report, runs, split)
    print(json.dumps({"models": report["models"], "summary": report["summary"]}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, help="scratch folder for the corpus copies (required unless --rescore)")
    parser.add_argument("--rescore", action="store_true", help="score the saved answers again; run no agents")
    parser.add_argument("--harness", nargs="*", default=["claude", "codex"])
    parser.add_argument("--only", nargs="*", help="task ids")
    parser.add_argument("--split", choices=sorted(SPLITS), default="dev")
    args = parser.parse_args()
    split = SPLITS[args.split]
    tasks = [t for t in frozen_tasks(split) if not args.only or t["id"] in args.only]
    if args.rescore:
        return rescore(tasks, split)
    if args.base is None:
        parser.error("--base is required")
    split.transcripts.mkdir(parents=True, exist_ok=True)
    workspaces = {c: prepare(args.base, c) for c in ("baseline", "specdex")}
    digests = {c: tree_digest(w) for c, w in workspaces.items()}
    jobs = [(t, h, c) for t in tasks for h in args.harness for c in workspaces]
    with ThreadPoolExecutor(WORKERS) as pool:
        runs = list(pool.map(lambda job: run_one(job[0], job[1], job[2], workspaces[job[2]], split), jobs))
    modified = [c for c, w in workspaces.items() if tree_digest(w) != digests[c]]
    write_report({"tasks": [t["id"] for t in tasks], "claude_model": CLAUDE_MODEL, "workspaces_modified": modified}, runs, split)
    for r in runs:
        print(f"{r.task} {r.harness:6} {r.condition:8} calls {r.calls:2} tool-tokens {r.tool_tokens:6} guide {r.guide_tokens:5} specdex {r.specdex_calls:2} "
              f"overlap {r.evidence_overlap:.2f} violations {len(r.violations)} {r.error or ''}")
    print("modified workspaces:", modified or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
