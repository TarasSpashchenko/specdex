# specdex M2 report (BMad v7, 2026-10-09)

M2 makes specdex work on BMad v7 projects and pass BMad Toolsmith's packaging checks, without losing the dated v6 layout M1 was built for. In v7, BMAD-METHOD "next" still reports version `6.13.0-next`, but:
- planning skills write into `{output_folder}/{active_initiative}/<type>-<slug>/<type>-<slug>.md`;
- `bmad-ticket` replaced `bmad-preview-ticketing`;
- Toolsmith replaced BMad Builder.

Before M2, specdex found no record files on a v7 project (Barracuda) and answered `resolve FR-1` with "unknown". The plan was frozen before coding (`docs/m2-v7-plan.md`), and the working notes are in `docs/m2-worklog.md`.

## Verdict

| Gate (frozen in `m2-v7-plan.md`) | Result |
|---|---|
| All tests pass | **Pass.** 241 unit tests (176 from M1, 65 new) and the 5 shipped smoke tests. |
| Every deterministic gold case correct; 0 false-clean results in ambiguous scopes | **Pass.** Layer B 12/12 deterministic mutation cases on both layouts, with no false-clean result. Unit tests cover ambiguous records inside the active initiative. |
| 0 authority or freshness failures | **Pass, with a disclosed blind spot.** The proxy counted 0 authority errors on every corpus, and freshness passed 6/6 on both layouts. The proxy only counts history the settings declare. On Barracuda, specdex showed 5 forbidden passages without a historical label, because Barracuda voids them only in prose. See "Barracuda". |
| Layer A median lookup tokens ≥30% below the stronger baseline (B1) | **Pass with search (specdex-B); fail on no-loss without it (specdex-A),** the same pattern as M1 dev.<br>Barracuda: specdex-B used 538 vs 3,949 tokens (−86%) and completed 13/14 lookups, against B1's 12/14. specdex-A used −95% tokens but completed 8/14.<br>Tamagai: specdex-B 24/24 at 760 tokens, against B1's 23/24 at 3,473. |
| Layer B: ≥11/12 mutations, 0 false-clean, 4/4 identity | **Pass on tamagai, v6 and v7 layouts:** 12/12, 0 false-clean, 4/4 identity, 6/6 freshness. Not run on Barracuda; see "Deviations". |
| v6 regression matches M1 | **Pass.** Layer A, 48 tasks × 4 conditions: 0 differences in recall, shown spans, calls and authority results. Tokens changed by 0 to +16 per call, from the generation ID and the new status text. Layer B: the same summary as M1. |
| Latency at 1× on Barracuda: warm p95 ≤500 ms, full rebuild ≤5 s | **Pass.** Warm p95 0.16 s, full rebuild 0.47 s, a 20-line edit 0.24 s. Tamagai: 0.15–0.16 s and 1.6–1.7 s. |
| Toolsmith packaging checks | **Pass.** `validate_manifests.py`, `init_skill.py --check`, `scan_paths.py`, `scan_scripts.py` and `prepass.py` report nothing beyond the kept deviations. `SKILL.md` is 894 tokens and its description 459 characters. |

**Bottom line:**
- On Barracuda, a real v7 project, specdex picks the right profile, finds the 6 record files of the active initiative, and its lint is clean. With search it answers 13 of 14 lookups at 14% of B1's tokens.
- On the tamagai corpus moved into the v7 layout byte for byte, it behaves as on v6. The exception is two search-rank swaps caused by file names, which leave recall unchanged.
- An independent review then found 40 defects, all confirmed by adversarial verifiers. All were fixed test-first, and the evaluations were rerun on the fixed code; no evaluation number changed beyond tokens. The defects included two M1-era validator bugs, one of them a security bug.
- **The weak spot is history questions on Barracuda** (specdex-B 1/4, B1 4/4). The traps there are mostly content-level, a PRD paragraph voiding passages of other documents, which settings cannot express.

## What changed

- **Profiles** (`skills/specdex/assets/profile-*.toml`, moved from `profiles/` per Toolsmith):
  - The new `bmad-v7` profile has 41 artifact rules:
    - **trail and history first:** archives at any depth, inbox, discussion, `.working`, imports, mockups, wireframes, review, reconcile, validation reports, migration, change, deferred work, retrospective;
    - **rationale:** research, brainstorm, forge, PRFAQ, intent and idea files, and the UX router;
    - **owners** as main files `<type>-<slug>/<type>-<slug>.md`: brief and addendum, PRD and addendum, `DESIGN.md`, `EXPERIENCE.md`, architecture spines and specs (both document-scoped, so epic spines and epic specs stand beside the initiative's);
    - **the `bmad-ticket` tree.**
  - It defines FR both by heading and by bold list lead, ships coverage defaults (FR for tickets and architecture, UJ for UX), and pins the installed templates, `lint_spine.py` and the `bmad-ticket` assets by hash.
  - Each profile has a `[detect]` table: v7 wins on a set `core.active_initiative` or on v7 planning documents, v6 on its dated folders (sharded ones included), and v7 is the default. `--profile` overrides, `status` prints the reason, and a git revision is matched by its own tree.
- **Settings are BMad-native.**
  - The skill ships `customize.toml` with every setting under `[workflow]`; projects override it in `_bmad/custom/specdex.toml` and `.user.toml`.
  - specdex reads those layers and `_bmad/config.toml`, `custom/config.toml`, `custom/config.user.toml` itself, with BMad's merge rules. **It never runs the project's `_bmad/scripts/resolve_*.py`** (owner decision: a read-only tool must not execute project code). Parity tests compare the results with the fixture's byte-identical copies of BMad's resolvers, and a tampered-resolver test proves nothing runs.
  - Malformed settings exit 3 with one line, and unknown keys raise `unknown-setting`.
  - The legacy `specdex-overlay.toml` is still read for one release and raises `deprecated-overlay`, which spells out the mapping.
- **Records follow the active initiative.**
  - Owners inside `{output_folder}/{active_initiative}/` are the candidates: one per type is the record, and several are ambiguous unless document-scoped.
  - Owners, rationale and tickets of other initiatives are `noncurrent`; backlog tickets stay current.
  - A `records` setting decides the types it names.
  - With no initiative, specdex uses M1's rule plus `no-active-initiative`, unless records decide. An active "initiative" that is a backlog folder, as `bmad-ticket` allows, scopes no specs.
- **Tickets follow `bmad-ticket`:**
  - initiatives with entries and no epics;
  - unique ticket keys;
  - dropped work is never coverage;
  - epic-local spec ids map to the epic's parent ids;
  - unlisted and id-less leaves count;
  - every `backlog*` folder is checked;
  - specs are found at `spec-<slug>/spec-<slug>.md`;
  - only the active initiative's tree is checked.
- **Extractor:** a bold item lead may hold italics. A sentence-shaped bold lead (`**FR-2 is verified …**`) is a citation when the file defines the ID elsewhere, and still a definition otherwise. A main file linking to unindexed section files beside it (a migrated sharded document) raises `unsupported-layout`.
- **Validators** (M1-era fixes): `lint_spine.py` runs only when hash-matched and now in Python's isolated mode, and its findings are reported (they were dropped before).
- **Packaging (Toolsmith):**
  - `SKILL.md` follows the script-utility shape with `uv run`, and its detail moved to `references/reading-results.md`;
  - `bmod.toml` 0.2.0 has install messages and `required_skills = bmad`;
  - `help.md` has no install mechanics;
  - shipped alongside: `customize.toml`, a smoke test with the one-line failure case, and `evals/triggers.json` (16 cases).
- **Size:** the engine is 4,285 lines (+539 over M1), stdlib only. The v7 fixture `tests/fixtures/v7-project/` has two initiatives, a loose PRD, backlog, inbox, archive, discussion and every v7 artifact type; tests build further shapes from it.

## Results

All numbers are from the final code, after the review fixes; the pre-review runs gave the same recall everywhere.

### v6 regression (tamagai, M1 corpus and overlay)

`eval/m2-v7/compare_layer_a.py` compared the M2 run (`eval/m2-v7/results-v6-regression/`) with M1's committed dev and held-out results:
- **0 differences** in contained, top-5 and workflow recall, shown spans, call counts and authority errors, across 48 tasks × 4 conditions;
- tokens changed by 0 to +16 per task-condition.

Layer B matched M1: 12/12, 1/1 agent-only, 4/4 identity, 6/6 freshness, no false-clean. Warm p95 was 0.16 s (M1 0.15 s) and the full rebuild 1.64 s (M1 1.8 s).

### tamagai-v7 (the same bytes in the v7 layout)

`eval/m2-v7/make_tamagai_v7.py` moved the frozen M1 corpus into `_bmad-output/initiative-tamagai/` by path only, so every byte and every gold line range is unchanged.
- **Settings:**
  - Layer A reads the corpus's own `_bmad/custom/specdex.toml`, which is the M1 overlay as customization with no records list: the active initiative decides.
  - Layer B uses the M1 overlay re-pathed.
- **`status`:** the same role counts as v6 (record 9, rationale 7, trail 140, memlog 8) and the same lint.
- **Profile `unverified`:** tamagai's installed BMad predates the v7 assets, so the bindings differ. This is expected and changes no answer.
- **Layer A against the v6 run:**
  - **B1 identical; specdex-B recall identical**, with two shown-span differences (C02, H03). Heading paths of files without an H1 fall back to the file name (`prd.md` vs `prd-tamagai.md`), which shifts the FTS5 BM25 averages and swaps the fifth search hit. `refs FR-7` prints identical lines on both layouts.
  - **specdex-A and B0 differ** where they grep: `rg` walks the new paths in another order and truncates elsewhere. specdex-A completes the same 31/48; B0 goes from 18/48 to 19/48.
- **Layer B:** 12/12, 4/4, 6/6, no false-clean; warm p95 0.15 s, rebuild 1.70 s.

### Barracuda (real v7 project, frozen on 2026-10-09, kept out of git)

**Profile and files:** `bmad-v7` (verified; active initiative set). 46 files: record 6, rationale 1, ticket 2, memlog 3, trail 30, and unverified 4, which are the project's own notes. Lint is clean.

The gold is 24 dev tasks under M1's labelling contract, drafted by two labellers and checked by an independent verifier. The settings come from Barracuda's stated conventions only:
- seven project ID families and the glossary;
- three history marks (two addendum sections and one labelled block);
- the UX coverage key.

| Condition | Lookup complete (14) | Median lookup tokens | All complete (24) | History (4) | Citation R/P |
|---|---|---|---|---|---|
| specdex-B (with search) | **13/14** | **538** | 19/24 | 1/4 | 0.833 / 0.756 |
| specdex-A (no search) | 8/14 | 207 | 13/24 | 0/4 | 0.833 / 0.756 |
| B1 (manifest + outline + reads) | 12/14 | 3,949 | 21/24 | 4/4 | 0.679 / 0.673 |
| B0 (`rg` + reads) | 10/14 | 7,884 | 18/24 | 2/4 | 0.679 / 0.673 |

**Notes on individual tasks:**
- **E01:** the glossary family was added after the first run, and this change is declared here. It fixed E01 (define a glossary term) for both specdex conditions, at 93 instead of 3,070 tokens. Nothing else changed between the runs. Run 1 is kept in `results/layer-a-dev.run1-before-term.json` and the pre-review run in `results/layer-a-dev.run2-before-review.json`.
- **E03 is a gold defect.** It asks for a positional sub-ID (`FR-n.k`), a notation Barracuda never uses (0 occurrences) and never declares; the labellers read it as a requirement's third sub-bullet. specdex-A answers "not defined", which is right under the project's conventions, while specdex-B and B1 find the sub-bullet by search. Without E03 the lookup scores are specdex-B 12/13, B1 11/13 and specdex-A 8/13.
- **C04 is a proxy limit.** The frozen M1 policy calls `refs` only when the prompt matches its citation-intent pattern, and its "which acceptance tests verify FR-n" prompt does not. Run by hand, `refs` lists all three acceptance-test lines with their `[in AT-n]` units.
- **S08** scores 0.5 in every condition: its second unit is a PRD line voiding a design passage.
- **History tasks are content traps.** Y01 asks about a UX component that a PRD paragraph voids in prose. Y03 pits an older brief-addendum fact against a newer PRD-addendum one. Y04 asks for a requirement that does not exist.
  - specdex-B misses the PRD units in Y01 and Y04.
  - It **shows 5 forbidden passages unlabelled:** four UX lines voided in prose and a digest of a rejected earlier proposal. B1 shows 6 and B0 13, also unlabelled.
  - The proxy's authority counter only counts passages that a convention marks historical, so it reports 0.
  - Settings cannot mark single passages inside a current section, so this is a limit of the settings model. The durable fix is in the source: remove the voided passages from the UX documents with `bmad-ux`.
- **Latency** (`eval/local/m2-barracuda/latency.py`, the Layer B method): full rebuild 0.47 s, warm p95 0.16 s over 30 mixed calls, and 0.24 s for a 20-line edit.

## Independent review

Four reviewers each covered one dimension against the installed BMad v7 skills: configuration, roles and extraction, tickets, and profile with packaging. An adversarial verifier per dimension then tried to refute every finding. **40 findings, all confirmed;** after overlaps about 30 distinct defects. Every one was fixed test-first (65 M2 tests in all), except one that was narrowed to documentation.

| Severity | Defect (fixed) |
|---|---|
| high | A module planted beside the hash-pinned `lint_spine.py` was imported (M1-era). Validators now run with `python -I`. |
| high | `lint_spine` findings were never reported: its `ok: false` was read as a failure (M1-era). |
| high | An `archive-v6/` inside an initiative (where the migration puts it) was not trail. Archived owners competed as records. |
| high | Frontmatter `type` turned archived, working or discussion copies of a spine into owners. It now refines only owners, tickets and unmatched files. |
| high | Migrated sharded documents lost their sections silently. They now raise `unsupported-layout`, and negatives become `unknown`. |
| high | An initiative's own `[[entry]]` tickets were counted as epics. |
| medium | **Roles:** rationale and tickets of other initiatives were labelled current. |
| medium | **Roles:** an epic spine beside the initiative spine made every AD ambiguous. |
| medium | **Records:** a `records` list made every unnamed owner noncurrent. |
| medium | **Records:** `no-active-initiative` was raised even when records decided. |
| medium | **Records:** `output_folder = "{project-root}"` lost the scope. |
| medium | **Records:** a backlog folder as the active initiative removed every record. |
| medium | **Extraction:** a lowercase-led bold lead no longer defined its ID (a v6 regression). |
| medium | **diff:** `diff` across the v6→v7 migration used today's profile for the old revision. |
| medium | **Tickets:** dropped tickets counted as coverage. |
| medium | **Tickets:** repeated ticket refs misattributed `refs` rows. |
| medium | **Tickets:** epic-local spec ids were flagged against the template. |
| medium | **Tickets:** unlisted and id-less leaves were ignored, and so were `backlog-<slug>/` folders. |
| medium | **Coverage:** `coverage` with no family read as clean. Defaults now ship, and an empty list exits 2. |
| medium | **Docs:** the overlay mapping dropped `records` without a word. |
| low | **Configuration:** malformed settings, non-UTF-8 layers and incomplete items crashed with exit 1 instead of exit 3. |
| low | **Configuration:** a TOML date in an overlay crashed. |
| low | **Configuration:** config diagnostics were outside the fingerprint. |
| low | **Configuration:** an unset `{active_initiative}` in a records path left `//`. |
| low | **Configuration:** sharded v6 under a custom planning folder lost `unsupported-layout`. |
| low | **Profile:** intent and idea files were unclassified. |
| low | **Tickets:** an ambiguous backlog cover read as undefined. |
| low | **Coverage:** document-scoped coverage keys collided. |
| low | **Tickets:** a trailing comment broke `covers` line numbers. |
| low | **Tickets:** a leaf without `covers` hid its entry's covers. |
| low | **Packaging:** the smoke test lacked the one-line failure case. |
| medium (narrowed) | Project `role` settings outrank the profile's trail and rationale defaults. The verifier agreed this precedence is deliberate (it is needed so tamagai's settings mean the same on v7). The docs that still described the M1 rule were corrected. |

Two minor residuals remain:
- `coverage` with no record files at all prints an empty population marked `incomplete` and exits 0.
- A ticket plan with no `status` reads as "planned" where `bmad-ticket` says "backlog".

## Deviations from the plan

| Plan | What happened | Why |
|---|---|---|
| Worktree mode calls the project's `resolve_config.py` and `resolve_customization.py` | specdex reads the same files with BMad's merge rules and never runs project scripts. | Owner decision after implementation: security (a read-only tool must not execute project code) and latency. Parity is tested against the real resolvers. |
| Layer B re-targeted to Barracuda | Run on tamagai-v7 instead. Barracuda gets Layer A, `status`, lint and latency. | 7 of the 12 mutation classes need an architecture spine, positional IDs or ticket epics. Barracuda has none of these yet (its `tickets.toml` has no epics). tamagai-v7 has every artifact type in the v7 layout. |
| Barracuda settings fixed before the run | The glossary family was added after run 1; declared above. | Run 1 showed that the PRD §3 glossary, a stated project convention, was not a defined family. |
| (not planned) | An independent review with adversarial verification, then fixes and a full rerun. | Quality gate before reporting; the M1 audit had shown its value. |
| `update_source` | Stays `file:`. | Kept deviation as planned: the repository is not published. |

Kept Toolsmith deviations (README, "BMad Toolsmith compliance"):
- running the hash-pinned `lint_spine.py`, now isolated;
- the unprefixed name `specdex`;
- the `scripts/specdexlib/` package;
- text output by default (`--json` available).

## Limits and threats to validity

- **One real v7 project,** frozen, with 24 dev tasks and no held-out set or agent replay. M1 established both, and M2 changes indexing, not search.
- **The proxies are M1's frozen, oracle-assisted policies** (C04 above), and the Barracuda gold has one defective task (E03).
- **Barracuda has no tickets, spine or specs.** The v7 ticket, spec and architecture paths are tested on the synthetic fixture and on tamagai-v7 only. The epic-local spec map follows `bmad-ticket`'s "map on the line" form (`CAP-1 (FR-4)`), which `bmad-ticket` itself does not specify for spec definitions.
- **Content-level supersession** (a paragraph voiding another document's passages) is invisible to the settings model.

## Follow-ups (done 2026-10-09, on the owner's request)

1. **Commit:** M2 is committed in `~/TS/ts/specdex` on top of the baseline `33b77c7`, with no push.
2. **Barracuda's install** is specdex 0.2.0, in the project's shared layout (`.agents/skills/specdex` with a `.claude/skills` symlink). The evaluated settings are in `_bmad/custom/specdex.toml`, minus the coverage key that is now a profile default. On the live project: profile verified, 6 records, lint clean.
3. **Barracuda's spines:** a `bmad-ux` update removed every passage the PRD voided in prose. It replaced them with the PRD's current decisions in `DESIGN.md`, `EXPERIENCE.md` and the one mock. A `bmad-prd` update then replaced the PRD's stale void list with a pointer to the reconciliation. The history traps of the Barracuda gold set no longer exist in the live project; the frozen evaluation corpus keeps them, so the numbers above stand.

## Artifacts

| What | Where |
|---|---|
| Plan, worklog, this report | `docs/m2-v7-plan.md`, `docs/m2-worklog.md`, `docs/m2-report.md` |
| Profiles, settings, skill | `skills/specdex/assets/`, `skills/specdex/customize.toml`, `skills/specdex/` |
| v7 fixture and tests | `tests/fixtures/v7-project/`, `tests/test_v7.py`, `tests/test_v7_tickets.py` |
| Harness changes | `eval/m1-tamagai/corpus_def.py` and `corpus_select.py` (`--corpus-def`); `layer_b.py --out` |
| tamagai-v7 | `eval/m2-v7/`: `make_tamagai_v7.py`, `tamagai_v7_def.py`, `tamagai-v7-specdex.toml`, `overlay-tamagai-v7.toml`, `gold-tamagai-v7/`, `results-tamagai-v7/`, `compare_layer_a.py` |
| v6 regression results | `eval/m2-v7/results-v6-regression/` |
| Barracuda (git-ignored) | `eval/local/m2-barracuda/` (gold, settings, corpus definition, `latency.py`, results); corpus `eval/corpora/barracuda-2026-10-09/` |
