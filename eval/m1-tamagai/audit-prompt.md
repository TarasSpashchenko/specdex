# Independent audit of specdex M1 (code, dev labels, evaluation)

You are an independent senior reviewer. Audit the specdex M1 milestone and write one report. Do not change any file except the report.

## What specdex is

specdex (repo root: the current directory) is a lightweight, strictly read-only search and maintenance engine for BMAD Markdown specifications, installed per project as a one-skill BMAD module.
- **Code:** `skills/specdex/scripts/specdexlib/`, a stdlib Python ≥3.11 CLI; the launcher is `skills/specdex/scripts/specdex.py`.
- **Configuration:** `skills/specdex/profiles/bmad-6.13.0-next.toml` holds what BMAD fixes; a project overlay holds what one project adds. The Tamagai one is `eval/m1-tamagai/overlay.toml`.
- **Design and decisions:** `docs/m1-plan.md`, with frozen gates and SLOs, and `docs/m1-worklog.md`.
- **Agent-facing guide:** `skills/specdex/SKILL.md`.

M1 evaluates it on a frozen copy of the Tamagai project, `eval/corpora/tamagai-2026-10-04/`. It has three parts:
- **Layer A, retrieval:** `eval/m1-tamagai/run_eval.py`; dev gold in `eval/m1-tamagai/gold/dev.json`; labelling contract in `eval/m1-tamagai/GOLD-SPEC.md`.
- **Layer B, maintenance mutations, identity cases, freshness and latency:** `eval/m1-tamagai/layer_b.py`.
- **Agent replay:** `eval/m1-tamagai/replay/replay.py`.

Unit tests are in `tests/`; run them with `python3 -m unittest discover -s tests`.

## Hard rules

- Write only `eval/m1-tamagai/results/codex-audit.md`. Do not edit, create, move or delete anything else: no code fixes, no git commands that change state, no index files inside the repo.
- If you run specdex, pass `--db` pointing to a file under `/tmp`.
- Never open `eval/m1-tamagai/gold/heldout.json` or anything under `eval/m1-tamagai/results/replay/`. The held-out set stays sealed until its single final run.
- Stay inside this repository and `eval/corpora/`. Don't open anything under `~/TS/ts/tamagai`.
- Cite evidence as `path:line`. Separate verified facts, which you reproduced or read, from opinions.

## Audit these, in order

1. **Correctness bugs in `specdexlib`.** Find real defects with a concrete failing input. Priority areas:
   - range and ID extraction (`extract.py`);
   - citation resolution and scope rules (`resolve.py`);
   - freshness and concurrency (`index.py`, `store.py`: `BEGIN IMMEDIATE`, schema version, stale reads);
   - `get`/`refs`/`search` semantics (`queries.py`);
   - diff, history and positional kinds (`diffing.py`);
   - lint false-clean risks (`maintenance.py`);
   - the ticket adapter (`tickets.py`, `coverage.py`).

   Reproduce each one where you can, for example with a small temp project or `python3 -c`, and give the command and its output.
2. **The read-only guarantee and safety.** Can any command write inside the project, follow a symlink out of the project, run unexpected subprocesses, or build SQL from untrusted text?
3. **The generality gate.** No Tamagai path, ID family or rule may live in the core code or the profile; they belong in the overlay. List any violation.
4. **Dev gold labels** (`gold/dev.json`, 32 tasks). For each task, check against the frozen corpus that:
   - every evidence span exists and supports the answer;
   - no current-record unit needed for a complete answer is missing;
   - `forbidden` spans really are non-current;
   - citation tasks list every citing line and only those.

   Report each label error with its fix. Spot-check at least 12 tasks in full, and all 6 citation tasks.
5. **Evaluation fairness and validity.**
   - **Layer A:** does `run_eval.py` handicap the baselines (B0 `rg` + reads, B1 manifest + outline + section reads) or favour specdex? Check the frozen proxy policy, the scoring rule and the token counting.
   - **Layer B:** in `layer_b.py`, does each case test what its title claims? Could a case pass for the wrong reason? Is each control meaningful?
   - **Replay:** in `replay.py`, are the two conditions comparable? Is the token accounting complete?
6. **SKILL.md.** Is it accurate against the code (commands, statuses, exit codes, labels)? Is anything misleading for an agent?

## Report format (`eval/m1-tamagai/results/codex-audit.md`)

- A verdict paragraph: can the M1 results be trusted, and what must be fixed first?
- A findings table, most severe first, with columns: ID (A-01…), severity (critical/high/medium/low), area, `path:line`, finding, evidence (reproduction or quote), suggested fix.
- A section on dev label errors, one row per task affected, with the corrected evidence or citations.
- A short list of what you checked and found sound, so a clean area is distinguishable from an unchecked one.

Be concrete and terse. No praise, no restating the code.
