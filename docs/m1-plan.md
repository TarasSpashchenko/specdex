# specdex M1 plan (frozen before coding, 2026-10-04)

specdex is a lightweight, read-only engine that indexes, searches and checks BMAD specifications in any project. It ships as a BMAD module installed per project. The design comes from two Codex–Claude discussions held in the Tamagai repository (`_bmad-output/planning-artifacts/discussion-spec-search/`): `outcome.md` (round 1: search) and `outcome-2.md` (round 2: generic search and maintenance). This plan records only the decisions those documents left open, which the owner delegated to Claude on 2026-10-04 ("Make all decisions yourself").

## Decisions

| Item | Decision |
|---|---|
| Repository | `~/TS/ts/specdex`, owned by the user. Nothing is committed without the owner's say-so. |
| Packaging | A one-skill BMAD module: `skills/specdex/` holds `bmod.toml` (`[bmod]` and `[skill]`), `SKILL.md` (routing guidance), `help/help.md`, `profiles/`, and `scripts/specdex.py` with its package `scripts/specdexlib/`. It installs with `npx skills add`. The installed BMad Builder (v2.2.2) is not used for packaging, because its module builder scaffolds `module.yaml`/`module-help.csv` and reads `_bmad/config.yaml`, while the target BMAD (6.13.0-next) uses `bmod.toml` and `config.toml`. Its script standards (PEP 723, standard library, `uv run`) are followed. |
| Runtime | Python ≥3.11, standard library only (sqlite3 with FTS5, tomllib). Evaluation scripts may use extra packages through PEP 723. |
| M1 scope | Tamagai only. Support tier: the installed dated v6 layout (BMAD 6.13.0-next) plus preview tickets. Ticket checks are tested on synthetic fixtures until Tamagai has tickets. Other layouts (classic-v6 sharded, initiative-v7) produce an "unsupported layout" diagnostic. |
| Overlay | During M1 the Tamagai overlay lives in `eval/m1-tamagai/overlay.toml`, so the Tamagai repository is untouched. After adoption, its default path is `{project-root}/_bmad/custom/specdex-overlay.toml`. |
| Index location | Outside the project: `${XDG_CACHE_HOME:-~/.cache}/specdex/<key>/index.sqlite`, where the key is derived from the project root, the mode and the revision; `--db` overrides it. |
| Effort | M1 only: Layers A and B, the identity cases, packaging, and a short agent replay. M2, M3 and S each need a later go-ahead. |

## Frozen evaluation parameters

- **Corpus:** `eval/corpora/tamagai-2026-10-04/` (git-ignored), an rsync copy of the Tamagai worktree at `502a77a` with the uncommitted 2026-10-04 edits. It excludes `.git`, `gallery/`, media, and `discussion-spec-search/` (the evaluation's own material). Gold labels refer to its paths and line numbers.
- **Layer A (retrieval):** 48 tasks per round 1 §4. The 32 development tasks are drafted by Claude's subagents with an independent verifier. The 16 held-out tasks (8 paraphrases plus 2 each of section, exact, citation and history) are written and labelled by Codex, sealed, and unseen until the final run. The contract is in `eval/m1-tamagai/GOLD-SPEC.md`.
- **Layer B (maintenance):** the 12 deterministic mutation cases of round 2 §6, plus one agent-only semantic contradiction that is reported separately. Mutations are applied to copies; the 4 identity cases are listed in round 2 §6.
- **Evidence scoring:** a returned span covers a gold unit when it has the same path and its line range contains the gold range. Top-5 evidence recall for a task is the share of its gold units covered by its top 5 results, averaged over tasks. An outright failure is a task with recall 0. Citation tasks are scored by set precision and recall over (path, line).
- **Tokens:** one tokenizer (tiktoken `o200k_base`) for every condition's output. Engine budgets use a chars/4 estimate.
- **Baselines:** B0 is `rg` plus reads; B1 is the manifest plus a generated outline plus bounded reads. Both run as deterministic proxies over all tasks: B0 searches with the task's key terms and reads around each hit the way agents were observed to (median requested ranges, extract-corpus §B6), and B1 reads the record-file outline and then the matched section. An agent replay of a frozen subset in both harnesses checks the proxies.
- **Smallest worthwhile benefit, per layer:**
  - **Stage A (outline, get, resolve, refs):** median lookup tokens (section and exact tasks) at least 30% below the stronger of B0 and B1, with no loss of evidence or answer correctness.
  - **Stage B (ranked FTS5 search):** on wording and paraphrase tasks, top-5 evidence recall at least 10 percentage points above Stage A plus `rg`, with no authority regression. Otherwise Stage B stays off by default.
  - **Layer B:** at least 11 of the 12 deterministic mutations flagged, with zero false-clean results, and 4 of 4 identity cases correct.
- **Phase 2 (semantic) trigger, from round 1:** the strongest lexical workflow scores below 75% held-out top-5 recall on the 8 paraphrases, or fails more than 2 of them outright.
- **SLOs (frozen from round 2 §6's provisional values):** at 1× scale (worktree mode, this machine), warm verified lexical p95 ≤500 ms and full rebuild ≤5 s. In snapshot mode (measured in M2): warm search p95 ≤1 s at 10× and ≤2 s at 100×; incremental parse and index of one typical spec file ≤2 s at 10× and ≤5 s at 100×. A typical mutation is one record-sized spec file with at most 20 changed lines. Strict worktree verification reports its full cost.
- **Gates:** every deterministic gold case is correct; zero authority or freshness failures; ambiguous scopes never return false-clean results; and the thresholds above.
