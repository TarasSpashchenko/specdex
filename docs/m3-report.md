# specdex M3 report (current BMad v7, 2026-11-11)

M3 makes specdex correct on BMad's current v7 layout, BMAD-METHOD `a867e160`. That version has:
- Sofia's ticket tree, with each container's breakdown in its `tickets/` folder;
- Requirements lines that carry their own `R<n>` ids;
- planning documents written on the `bmad-facilitate` engine;
- `bmad-shard-pro` shards.

The v6 and October v7 layouts keep working.

Before M3, on projects built from the current templates, specdex:
- reported every FR `missing` in ticket and architecture coverage;
- raised `ambiguous-current` on epic-level documents;
- treated many valid id definitions as undefined.

The plan is `docs/m3-plan.md`. The owner delegated every decision, and the proposed ones were taken; deviations are listed below. The working notes are in `docs/m3-worklog.md`. Nothing is committed: the work sits on the branch `m3-bmad-v7-current`, based on `1f6279d`.

## Verdict

| Gate (`m3-plan.md`) | Result |
|---|---|
| All tests pass; both conformance tests exact | **Pass.** 298 unit tests and 5 smoke tests.<br>• `check_ids.py`: specdex's definitions and citations equal the oracle's line by line on three document groups, using `check_ids.py`'s own `scan` captured from inside. They stay equal when fenced code, comments, CRLF line ends and other id families are added. Duplicates, withdrawn ids and undefined ids are reported alike.<br>• `tickets.py status`: the same tickets, states and covers as specdex, on an initiative, a parent initiative and the backlog. |
| Zero false-clean results | **Pass.** Layer B on the current layout: 6/6. These are M2's three ticket cases re-targeted to `tickets/` folders, plus the three new ones: an R line losing its parent, the PRD leaving `sources:`, and an FR edited inside a shard. All controls are clean.<br>M2's set: 12/12 on the v6, October and current corpora, with no false-clean result.<br>`coverage` now exits 1 when it counts nothing or the scope is not fully indexed. |
| Both regressions identical | **Pass.**<br>• v6 (tamagai, M1 corpus): Layer A has 0 differences over 48 tasks × 4 conditions; tokens change by −16 to 0. Layer B is 12/12, 1/1, 4/4 and 6/6, as in M1 and M2.<br>• October v7 (tamagai-v7 against `eval/m2-v7/results-tamagai-v7`): 0 differences; tokens change by 0 to +8. Layer B is 12/12. |
| Sharding is answer-invariant | **Pass.** On the fixture, `resolve`, `get`, `refs`, every `coverage` view and `lint` give the same answers on the sharded and unsharded PRD, apart from paths and lines. This holds for a pre-engine PRD too, including when only its main file changes.<br>On tamagai (B16), sharding its 2,000-line PRD with BMad's `shard_tool.py` changes no answer and no id. An edit inside a shard reaches `diff` and `get`. |
| Latency (warm p95 ≤ 500 ms, rebuild ≤ 5 s) | **Pass.**<br>• tamagai-v7-current: warm p95 0.177 s, full rebuild 1.77 s, a 20-line edit 0.44 s.<br>• v6 corpus: 0.173 s and 1.71 s.<br>• October corpus: 0.198 s and 2.44 s.<br>Barracuda has not been migrated by its owner, so the tamagai numbers stand in for it, as the plan allows. |
| Packaging (Toolsmith) | **Pass.** `validate_manifests.py`, `init_skill.py --check --any-name`, `scan_paths.py`, `scan_scripts.py` and `prepass.py` report nothing. `SKILL.md` is 952 tokens, the gate; its description is 464 characters. Version 0.3.0. |
| Trigger cases do not regress | **Pass.** `bmad-eval` ran 16 queries × 3 runs on 0.2.0 and 0.3.0.<br>• Both load the skill on 14 of 16 queries and miss the same two: q7 ("what changed in the requirements between yesterday's commit and now?") under-triggers, and q10 ("rewrite FR-12") fires on an edit request.<br>• The runner's own counts include 7 false loads on both versions, where the canary token appeared in tool output. That is a `run_triggers.py` issue. |

**Bottom line:**
- On BMad's current layout, specdex reads the ticket tree:
  - it follows every Requirements line form BMad writes to the source ids;
  - it treats a ticket's R ids as definitions;
  - it lets an epic's documents stand beside its initiative's;
  - it includes parent initiatives;
  - it reads shards as one document.
- It decides where an id is defined exactly as BMad's own `check_ids.py` does, and sees the same tickets as BMad's `tickets.py`.
- Older projects answer as before, with 0 differences on the v6 and October regressions.

## What changed

| Findings | Change |
|---|---|
| T1–T3, T9 | `layout.py` (new) reads both ticket layouts. A container is a folder holding `<name>.md`. Its breakdown is in `tickets/` or, in October trees, beside the file. A container also counts before it is sliced, so a spine's binds work right after the Requirements are written. Parent initiatives come from `[[initiative]]`, and the current scope is the active initiative plus its parents. |
| T4–T7 | Requirements lines are parsed into items:<br>• `parent R3`, or a bare `R3`;<br>• source ids, optionally typed (`prd FR-2`), and ranges;<br>• a section citation, which makes the chain `local`, never `missing`;<br>• a folded spec's `CAP-n`, which is a `local` alias while no spec remains.<br>A line naming nothing (`- R2:`) or `parent` without an id is a problem. |
| T6, T10 | A ticket's sources are its `sources:` paths, from the project root or, as BMad's spec fold writes them, from the ticket's folder. References lines count only for October tickets, which have no `sources:`. A source id must be in the ticket's own sources, as BMad's tree check requires. Companions are found from the project root too. |
| T8, P1 | R ids are a document-scoped family, defined by a ticket's Requirements lines and cited only in `covers`, Requirements and spine binds. A story or spine cites its own container's R ids; a container's `covers` and `(parent R3)` cite its parent's. One `trace()` follows them for ticket chains and for architecture coverage. `refs` on an R id lists the `tickets.toml` entries citing it. |
| P2, P3 | Under an active initiative, each container has its own record of each type. The `records` setting decides within the container of each file it names. Two documents of one type in one container stay `ambiguous`, and the diagnostic now names both fixes: the records setting, and `archive/`. |
| P4, P6 | For documents the engine wrote (`template:`) and their shards, ids are defined where `check_ids.py` says, ported line for line:<br>• table groups that re-cite earlier ids, read parents first;<br>• `withdrawn` marks;<br>• ranges joined by words and dashes, with bold ends;<br>• fenced code and comments skipped. |
| P5, P7, P9 | New families RULE, OQ, BR and SC (and R). Owner templates are prd, prd-light, srs, brd, agent-spec, brief and charter; the other templates are rationale. `archive/`, `.source/`, shard map pages, the identifier lookup and `.template.md` are trail. |
| P8 | A shard (`part_of:`) is part of its document. It takes the main file's role, type and rule set, and is read in the map's order. |
| X1–X5 | • X1: bindings re-pinned to `a867e160`; `tickets.py` is covered by the conformance test instead.<br>• X2: routing text names `bmad-agent-pm`, `bmad-agent-analyst`, `bmad-ux`, `bmad-architecture` and `bmad-agent-po`.<br>• X3: `coverage` exit codes.<br>• X4: `lint` reports broken covers chains as `ticket-*` findings where the covers are written.<br>• X5: resolver copies refreshed. |

The engine is 4,967 lines (+682 over M2). It is still stdlib only, with index schema 8.

## Evaluation corpora

- `tests/fixtures/v7-current/` was built from BMad's templates, and BMad's `tickets.py` and `check_ids.py` accept it. It has:
  - a parent initiative with a charter;
  - an active child with PRD, BRD, brief, UX and spine;
  - an epic with its own PRD and spine;
  - a dropped epic, an initiative without epics, a backlog and an archive.
- `v7-current-sharded/` is its PRD after `bmad-shard-pro`. `v7-folded/` is `v7-project` after BMad's spec fold and migration-2.
- `eval/m3-v7-current/make_v7_current.py` applies migration-2 to a corpus copy, with its path rewrites and the spec fold. tamagai-v7 has no ticket tree, so its current copy is byte-identical. Current-layout ticket coverage on a real corpus therefore comes from Layer B, which builds a tree inside tamagai that `tickets.py` accepts.
- **Barracuda** (frozen copy, converted; kept in `eval/local/`): the same roles, the same coverage rows and a clean lint, as before M3. The profile reads `unverified`, because the project still has the October BMad installed. It reads `verified` once the project updates BMad.

## Review

The code was reviewed by a workflow:
- Four dimension reviewers covered the ticket tree, the extraction and derivation, regressions, and the tests and docs.
- One skeptic per top finding tried to refute it.
- All 6 verified findings were real. Of the 15 unverified findings: 13 were fixed, one was the Layer B shard bug already fixed, and one (on the conformance test) is now covered by a test. All of them are listed in the worklog.

Layer B found four more bugs on its first run: a bare `R2:` line, a story's R id falling through to its parent, a pre-engine PRD's shards, and `diff` on duplicated ids. Every fix has a regression test. The evaluations above were rerun on the final code.

## Deviations from the plan

| Plan | Done | Why |
|---|---|---|
| The check_ids forms for planning documents | Only for documents with `template:` (and their shards, by their main file) | tamagai's earlier PRD lists assumptions as `- FR-2 — …`, which `check_ids.py` reads as 29 duplicate definitions; BMad checks only engine documents |
| Mirror `check_ids.py` | Except that a bold lead reading as a sentence (`**FR-2 is verified by …**`) cites an id defined elsewhere in its document | M2's real-project fix; reading it as a definition would make FR-2 ambiguous |
| T11: backlog is `backlog/` only | Kept `backlog*` | The v6→v7 migration wrote `backlog-<slug>/` folders; narrowing would drop their tickets or misread them as epics |
| Sponsor templates are rationale, the charter included | The charter is an owner (SM, RULE) | Its ids are global, and initiatives cite them (`R1 (RULE-1)`) |
| `.template.md` is skipped | Indexed as trail | The same effect for answers, and still searchable with `--scope all` |
| The converter adds `template:` frontmatter | Not added | It would shift every gold line range; the fixtures test `template:` |
| Sources in the order `sources:`, References, spec folder | References only when there is no `sources:` | BMad's tree check requires every source id to be in a `sources:` file; a PRD left only on a References line must be flagged (B15) |
| Settle the shard identifier lookup | Trail | It is generated from the shards and defines nothing |

## Limits and open items

- BMad v7 is pre-release. The closing drift check found upstream `main` still at `a867e160` on 2026-11-11. The conformance tests fail as soon as the installed `check_ids.py` or `tickets.py` changes.
- Only the active initiative's tree, its parents and the backlog are checked. Tracker stores are read only through mirrored files.
- Ids that a sponsor document (business case, narrative) lists are not definitions.
- In a project with no engine documents, a BR or SC id not declared as a project family is a dangling reference.
- **Trigger eval harness:** the trigger eval recorded a harness in `_bmad/custom/bmad-eval.user.toml`, which is personal and not committed. It runs `claude -p … --dangerously-skip-permissions`; keep it for future `bmad-eval` runs or delete it.
- **Trigger eval scope:** its clean room held only specdex, so the routing text's sibling skills were not part of the test.

## Files

| Area | Files |
|---|---|
| Engine | `skills/specdex/scripts/specdexlib/`: `layout.py` (new), `tickets.py`, `extract.py`, `resolve.py`, `coverage.py`, `maintenance.py`, `config.py`, `store.py`, `queries.py`, `render.py`, `diffing.py` |
| Profile and docs | `assets/profile-bmad-v7.toml` (release 2), `SKILL.md`, `help/help.md`, `references/reading-results.md`, `bmod.toml`, `README.md` |
| Tests | `tests/test_v7_current.py`, `tests/test_conformance.py`, additions to `tests/test_v7_tickets.py`; fixtures `v7-current`, `v7-current-sharded`, `v7-folded` |
| Evaluation | `eval/m3-v7-current/`: converter, Layer A comparison and capture, Layer B on the current layout (`results-layer-b.json`, `results-layer-b-full.json`), the v6 and October regressions, trigger runs (summaries only) |
