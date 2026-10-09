# specdex M1 report (Tamagai, 2026-10-04)

specdex is a lightweight, strictly read-only engine for searching and maintaining BMAD specifications, installed per project as a one-skill BMAD module. M1 tested it on a frozen copy of the Tamagai project, under the plan frozen before coding (`docs/m1-plan.md`). Working notes are in `docs/m1-worklog.md`.

## Verdict

| Gate (frozen in `m1-plan.md`) | Result |
|---|---|
| Stage A: lookup tokens ≥30% below the stronger baseline, with no loss | **Held-out: pass.** 85% fewer tokens (344 vs 2,350), 4/4 vs 4/4. **Dev: fail on no-loss.** 73% fewer tokens, but 16/20 vs B1's 19/20 contained. |
| Stage B: paraphrase top-5 recall ≥10 pp above Stage A | **Nominal pass** (12.5% vs 0%). The absolute recall is poor. |
| Layer B: ≥11/12 mutations flagged, 0 false-clean, 4/4 identity | **Pass.** 12/12, 0 false-clean, 4/4 identity, 6/6 freshness. |
| Zero authority errors | **Pass.** specdex 0 in the proxies; 0 in all 76 blind-judged agent answers across both conditions. |
| SLOs: warm p95 ≤500 ms, full rebuild ≤5 s | **Pass.** 0.15 s and 1.8 s; a typical 20-line edit takes 0.43 s. |
| Round-1 contract with real agents (replay): ≥30% fewer tokens, no correctness loss | **Mixed.** The guide is the one-off SKILL.md load, charged here to every single-question session.<br>Dev: Codex −62% (pass); Claude −22% with the guide (below the bar), −76% without it.<br>Held-out paraphrases: Claude −38% (pass); Codex −25% (below the bar).<br>Correctness: no loss in any set. |
| Phase 2 (semantic) trigger: <75% paraphrase top-5, or >2 outright failures | **Fired.** Lexical search found 1 of 8 held-out paraphrases in its top 5, with 7 outright failures. |

**Bottom line:** specdex works for its main job. With real agents it cut median tool tokens per answer:
- on dev tasks, by 22% (Claude) and 62% (Codex) counting the one-off skill guide in every single-question session, and by 75–76% without it;
- on held-out paraphrases, by 38% (Claude) and 25% (Codex) with the guide counted.

Blind-judged correctness was equal or better: no "wrong" answers with specdex, against 2 for the baselines. Its maintenance checks passed every mutation case. Two results are weak:
- **Ranked search is weak on paraphrases:** the semantic trigger fired. Real agents compensated by searching again with other words.
- **Stage A without search** misses some dev lookups.

The verdict on Phase 2 is a recommendation, not a pass. See "Decisions for you".

## What was built

- **Engine** (`skills/specdex/scripts/specdexlib/`): 3,746 lines of stdlib Python ≥3.11 (`sqlite3` FTS5, `tomllib`).
  - It parses Markdown and frontmatter with line addresses.
  - A versioned, hash-bound BMAD profile (`profiles/bmad-6.13.0-next.toml`, 248 rule lines) is combined with a project overlay. The Tamagai overlay is 195 rule lines.
  - It extracts typed edges (defines, elaborates, binds, mentions, covers, companion), with ranges and positional IDs (FR-n.k).
  - It assigns roles, temporal labels and scopes, and resolves citations to resolved, ambiguous, unresolved, out-of-bounds, historical or textual.
  - Freshness is byte-verified in worktree mode. Snapshot mode reads git revisions.
- **Commands:** `status`, `outline`, `resolve`, `get`, `refs`, `search`, `lint`, `impact`, `diff`, `covers` and `coverage`. Exit codes are 0/1/2/3.
- **Packaging:**
  - `SKILL.md`, an 88-line routing guide;
  - `bmod.toml`, a one-skill module record;
  - `help/help.md`;
  - `README.md`.

  BMAD's own `knowledge.py` and setup report 0 problems. `npx skills add` installs a working launcher into a fresh project.
- **Tests:** 176 stdlib unit tests, all passing, over synthetic fixtures: a mini BMAD project and a preview-ticket tree that BMAD's real `tickets.py` accepts.

## Results

### Layer A: retrieval (deterministic proxies)

All conditions are mechanical agents with the frozen policy described in the `run_eval.py` docstring. Scoring:
- **Contained:** a shown span contains the gold unit.
- **Top-5:** the first five distinct spans shown.
- **Tokens:** `o200k_base` tokens of everything the condition saw.

**Dev (32 tasks; lookup = 20 section and exact tasks):**

| Condition | Contained complete, all | Contained complete, lookup | Median lookup tokens | Top-5 recall, all | Citation R/P |
|---|---|---|---|---|---|
| specdex-B (with search) | 29/32 | 20/20 | 851 | 0.839 | 0.833 / 0.812 |
| specdex-A (no search) | 23/32 | 16/20 | 980 | 0.557 | 0.833 / 0.812 |
| B1 (manifest + outline + reads) | 30/32 | 19/20 | 3,665 | 0.771 | 0.778 / 0.833 |
| B0 (`rg` + reads) | 12/32 | 8/20 | 28,920 | 0.104 | 0.778 / 0.833 |

**Held-out (16 tasks, written by Codex, sealed until this one run):**

| Condition | Contained complete | Lookup (4) tokens | Paraphrase (8): complete / top-5 | Citation (2) | History (2) |
|---|---|---|---|---|---|
| specdex-B | 8/16 | 4/4 · 344 | 1/8 · 0.125 | 1/2 | 2/2 |
| specdex-A | 8/16 | 4/4 · 344 | 1/8 · 0.000 | 1/2 | 2/2 |
| B1 | 16/16 | 4/4 · 2,350 | 8/8 · 1.000 | 2/2 | 2/2 |
| B0 | 6/16 | 3/4 · 3,236 | 1/8 · 0.000 | 1/2 | 1/2 |

Reproducibility: held-out ran once, before Codex's re-check. After the re-check fixes, re-running it on the final engine gave identical recall on every task and condition; each call costs about 4 tokens less, because the printed generation ID changed. Nothing was tuned on held-out results.

B1's 8/8 on paraphrases is an artifact of the shared oracle continuation. B1 reads every heading first, and the oracle then picks the gold section for it, something a real agent must do itself. The agent replay below measures that step.

### Layer B: maintenance, identity, freshness, latency

From `layer_b.py` on copies of the corpus. Every detection case needs a clean control.

| Group | Result |
|---|---|
| Deterministic mutations | **12/12:** range-hidden citation; dropped and changed positional consequence; two same-ID scopes; inherited AD plus local redefinition; missing companion; unresolved covers source; refined file vs stale entry; planned ticket without a file; reused retired ID (git history); same-size restored-time edit; ambiguous current artifact, including an ID unique to one candidate. 0 false-clean. |
| Agent-only contradiction | lint states what it does not check, so it never reads as clean. Detecting the contradiction remains agent work. |
| Identity | **4/4:** identical independent documents kept distinct; declared equal replicas aliased; drifting replicas flagged; symlink aliased. |
| Freshness | **6/6:** dirty edit; inserted lines and bullets; delete and rename; invalid YAML; branch change plus a `--rev` snapshot; two concurrent readers. |
| Latency | Warm p95 0.15 s; full rebuild 1.8 s; typical 20-line edit 0.43 s. |

### Agent replay: real agents, blind-judged

Setup:
- **Harnesses:** Claude Code headless (`claude -p`, Sonnet 5.5, project skills, a read-only Bash allow-list) and Codex (`codex exec`, gpt-6.1-sol).
- **Workspaces:** each agent works on a private copy of the corpus. The specdex condition has the skill installed and one sentence saying so.
- **Tokens:** tool calls plus tool results. Skill-guide tokens are the one-off SKILL.md load, charged to every single-question session here.
- **Judging:** blind against the gold answer, with answers shuffled under the labels A–D.
- **Isolation:** 0 violations, and no workspace was modified.

| Set | Harness | Median tool tokens, baseline → specdex (without guide) | Judged correct/partial/wrong, baseline → specdex | Authority errors |
|---|---|---|---|---|
| Dev, 11 tasks | Claude | 3,684 → 2,857 (899) | 5/5/1 → 7/4/0 | 0 |
| Dev, 11 tasks | Codex | 13,753 → 5,287 (3,437) | 7/3/1 → 6/5/0 | 0 |
| Held-out paraphrases, 8 | Claude | 7,237 → 4,486 (2,384) | 5/3/0 → 7/1/0 | 0 |
| Held-out paraphrases, 8 | Codex | 18,331 → 13,742 (11,704) | 4/4/0 → 5/3/0 | 0 |

- **The baselines' two "wrong" answers (dev C04)** counted memlog, review and extract files as record citations: the scoping error specdex's roles prevent.
- **Baseline partials on H03/H04** missed the `[ASSUMPTION]` markers that specdex labels show.
- **Two specdex partials (dev Y02, Y05)** answered from one unit and missed a second rule. SKILL.md now says to `search` the concept as well.
- **Timing:** the dev replay ran before the audit fixes, which changed safety and labels, not search. The held-out paraphrase replay ran on the final engine. It is post-hoc and diagnostic only: nothing was tuned on it.

## Independent audit (Codex)

Codex audited the code, the dev labels and the harnesses. It wrote only its report (`eval/m1-tamagai/results/codex-audit.md`); the repository snapshot and corpus lock confirm this. It raised 29 findings, 15 of them high. Its verdict was "M1 acceptance cannot be trusted yet". Everything was fixed before the held-out run.

- **Engine:**
  - Validators run only when hash-verified, and failures are reported (A-01, A-22).
  - The index is never placed inside the project, and foreign SQLite files are refused (A-02).
  - The inventory is re-read under the write lock, and each command is pinned to one read snapshot (A-03).
  - "Partly historical" labels (A-04).
  - Definitions in retired text no longer answer current citations (A-05).
  - IDs from candidate documents are ambiguous (A-06).
  - Ticket covers edges appear in `refs`/`impact` (A-07); ownership and uniqueness checks for ticket chains (A-08).
  - Parse gaps make negatives unknown (A-09).
  - Symlinks out of the project are skipped and reported (A-10).
  - The remaining fixes, A-16 to A-21, A-26, A-28 and A-29, each come with a regression test (71 regression tests in all, including the re-check).
- **Harnesses:**
  - The frozen per-span containment and top-5 metrics now apply to every condition, with a gate block (A-13).
  - B0 can't repeat a step (A-11).
  - Authority errors are counted by overlap, and are not measurable for unlabelled baselines (A-14).
  - Replay paths must resolve to exactly one file (A-15).
  - Citation instrumentation is limited to the visible page (A-23).
  - Stronger Layer B controls (A-24); replay accounting documented (A-25).
- **Dev labels:** a subagent verified all 8 corrections independently and applied them (`results/dev-gold-audit-changes.json`).
- **Re-check** (`results/codex-recheck.md`; Codex again wrote only its report):
  - 11 findings resolved, 18 partly. The partials are mostly residual edges, plus evaluation-design limits that stay disclosed below.
  - It found 4 new defects that the fixes had introduced:
    - N1: a live requirement left coverage when its section held history.
    - N2: a retired positional child read as out-of-bounds.
    - N3: a ticket covers line was wrong when TOML keys were reordered.
    - N4: a document-scoped ticket source was wrongly ambiguous.
  - All 4 are fixed, along with the engine partials:
    - A-02: refuse any file holding non-specdex tables;
    - A-09: wrong-shaped frontmatter fields are parse gaps;
    - A-10: unreadable directories are reported;
    - A-18: identity and skipped sources are part of the generation;
    - A-19: full-folder scope keys, scoped citations in diff;
    - A-20: `max_members` counts members, in every range form;
    - A-22: a missing validator is a finding.
  - Remaining by design:
    - A-01: a hash-verified BMAD validator is trusted, not sandboxed.
    - A-12 to A-15, A-23, A-25: the proxies stay oracle-assisted and are disclosed, with the replay as the external check.

## Limits and threats to validity

- **One corpus.** Tamagai, one profile (BMAD 6.13.0-next dated v6), worktree mode at 1× scale. No claim yet about other projects or layouts; that is M2/M3.
- **The proxies are oracle-assisted.** The gold unit picks which pointer to follow and when to stop, for every condition, and the engine supplies definitions and section boundaries to the baselines too. This flatters B1 most (paraphrases), and B0 (28,920 median tokens) is more pessimistic than real agents. The replay is the external check, but its samples are small: 11 dev tasks and 8 paraphrases per harness.
- **Small held-out set.** Only 4 lookup tasks and 2 per minor category; the gates on them carry little statistical weight.
- **Replay accounting.** Codex ran with the user's RTK output compression in both conditions, which shrinks the baseline and makes the comparison conservative for specdex. The session system context is not counted. `--bare` was unavailable because only OAuth is configured.
- **Tickets are synthetic.** Tamagai has no tickets yet.

## Decisions for you

1. **Phase 2 (semantic search).** The frozen trigger fired, but real agents with specdex still matched or beat the baselines on held-out paraphrases. My recommendation:
   - Don't start a model trial yet.
   - First label about 20 new discovery tasks, as Phase 2's protocol requires anyway. The held-out set is now spent.
   - Try cheap lexical improvements against them: heading-weighted search, synonym and stem expansion, and an outline fallback in SKILL.md.
   - Request the local embedder and reranker trial on the LAN GPU host only if the lexical result still misses the ≥10 pp bar.

   A model trial needs your go-ahead (round 1, D-07); cloud processing is a separate decision.
2. **Adopt specdex in Tamagai?** That means:
   - `npx skills add ~/TS/ts/specdex --skill specdex` in the Tamagai repo;
   - copying the overlay to `_bmad/custom/specdex-overlay.toml`.

   Both change the Tamagai repository, so I haven't done them.
3. **Commit.** Nothing is committed in `~/TS/ts/specdex`. The Tamagai repository also still has uncommitted work from earlier.
4. **M2** (other layouts, scale) and **M3** (a held-out real project) each need a go-ahead.

## Artifacts

| What | Where |
|---|---|
| Plan, worklog, this report | `docs/m1-plan.md`, `docs/m1-worklog.md`, `docs/m1-report.md` |
| Engine, profile, skill | `skills/specdex/` |
| Overlay, gold, labelling contract | `eval/m1-tamagai/overlay.toml`, `gold/dev.json`, `gold/heldout.json`, `GOLD-SPEC.md` |
| Harnesses | `eval/m1-tamagai/run_eval.py`, `layer_b.py`, `replay/` |
| Results | `eval/m1-tamagai/results/`: `layer-a-dev.json`, `layer-a-heldout.json`, `layer-b.json`, `replay/`, `replay-heldout/`, `codex-audit.md`, `codex-recheck.md` |
| Tests | `tests/` (`python3 -m unittest discover -s tests`) |
