# specdex M2 worklog (BMad v7)

## 2026-10-09

**Baseline:** `33b77c7` (M1 as built; `.idea/` and SQLite eval caches ignored). Plan frozen in `docs/m2-v7-plan.md`.

**Phase 1, fixtures and failing tests.** `tests/fixtures/v7-project/` is built from the preview-ticket fixture, re-homed into `_bmad-output/initiative-shelf/`, and adds:
- every v7 artifact type;
- a second, inactive initiative whose PRD also defines FR-1 and whose `tickets.toml` has entries but no epics;
- a loose PRD, a backlog bug, an inbox note, the v6 archive and a discussion folder;
- `_bmad/config.toml`, `_bmad/custom/config.user.toml` (`core.active_initiative`), `_bmad/custom/specdex.toml`;
- byte-identical copies of BMad's `resolve_config.py`, `resolve_customization.py`, `config_utils.py` and `setup_check.py`.

`tests/test_v7.py` has 19 tests; all failed on the baseline for the intended reasons (v6 profile chosen, APIs missing).

**Phases 2–5, implementation:**
- **Profiles:** moved to `assets/profile-*.toml`. The new `profile-bmad-v7.toml` has main-file rules (`main = true`), trail and history rules ahead of owner rules, `[current] scope`, `[tickets] backlog`, a second FR definition shape (`item-lead`) and bindings at the installed hashes. Both profiles carry `[detect]`; v7 wins on a set `core.active_initiative` or v7 planning documents; v6 on the dated folders; v7 is the default.
- **Config:** `read_project_config` runs BMad's `resolve_config.py` when installed (with this interpreter) and falls back to a reader with BMad's merge rule. `read_customization` does the same with `resolve_customization.py` and the shipped `customize.toml`. A legacy `specdex-overlay.toml` is still read and raises `deprecated-overlay`. `records` may use `{active_initiative}`. `status` prints the profile's reason, the config reader and the record scope.
- **Roles:** owners inside the active initiative are candidates and the rest are `noncurrent`; with no active initiative, `no-active-initiative` is raised. Document-scoped owners (specs) are all records. A `rationale` kind is added for the UX router and research folders.
- **Tickets:** an initiative is recognised by its `initiative-` prefix and may hold entries directly. Backlog leaves check `covers` directly against the records. Specs are found as `spec-<slug>/spec-<slug>.md`. Only the active initiative's tree is checked.
- **Messages:** "overlay" wording replaced by "records setting" / "project settings".

**Real-project check (Barracuda, read-only, cache outside the project).** Profile `bmad-v7` (verified), `resolve_config.py`, 6 records. Two extractor gaps surfaced and were fixed test-first:
- a bold item lead holding italics (`**FR-3. … *word*.**`) was not a definition;
- a sentence opening with an ID in bold (`**FR-2 is verified …**`) was taken for a second definition.

The tamagai corpus has no owner lines of either shape (checked), so M1's definitions are unchanged. Barracuda's lint is now clean.

**Tests:** 195 pass (176 M1 + 19 v7).

**Phase 6, packaging.** Toolsmith's read-only checks all pass: `validate_manifests.py`, `init_skill.py --check`, `scan_paths.py`, `scan_scripts.py`, and `prepass.py` (`SKILL.md` 894 tokens, description 459 characters).
- `SKILL.md` follows the script-utility shape (Run / Read the result / When it fails) with `uv run`; label and status detail moved to `references/reading-results.md`.
- `bmod.toml` has install messages, `required_skills = bmad`, and version 0.2.0.
- `help.md` lost its install mechanics.
- Shipped: `customize.toml` (every setting under `[workflow]`), the smoke test `scripts/tests/test_specdex.py` (4 tests), and `evals/triggers.json` (16 cases).
- README: layouts, settings, Toolsmith deviations.

**Owner decision: built-in reader only.** Running the project's `_bmad/scripts/resolve_*.py` would execute project code from a read-only tool, against M1's rule that only hash-matched validators run. So specdex reads the same files with BMad's merge rules and never runs them.
- Parity tests run the fixture's copies of BMad's resolvers and compare the results, including a user-layer item replacing a team-layer one by id.
- A tampered-resolver test proves nothing runs.

**Role precedence.** Translating the tamagai settings showed that the v7 profile's rationale and trail defaults outranked a project's `role` settings; under v6 those files had no profile kind, so the project's rules applied. Project roles now win, while memlogs and tickets keep their kind (test added). Tests: 197.

**Phase 7, evaluation design** (the plan's Layer B re-targeting was not possible as written: Barracuda has no spine, specs or tickets):
- **tamagai-v7** (`eval/m2-v7/make_tamagai_v7.py`): the frozen M1 corpus moved into the v7 layout by path only, so every byte and every gold line range is unchanged.
  - Layer A reads the corpus's own customization with no records list (the active initiative decides).
  - Layer B uses M1's overlay re-pathed and pinned to `bmad-v7`, so all M1 mutation cases run.
  - Gold: M1's dev and held-out sets with remapped paths.
- **Barracuda** (`eval/local/`, git-ignored): a frozen copy (2026-10-09) plus the user's `active_initiative`.
  - Gold: 24 dev tasks (8 section, 6 exact, 6 citation, 4 history), drafted by two labellers and checked by an independent verifier. One fix: a `forbidden` reason; all line ranges and citation lists were recomputed and matched.
  - Settings come from Barracuda's stated conventions only. UX passages the PRD voids in prose sit inside current sections, so they stay unmarked; that is a measured limitation.
- **Harness:** `run_eval.py` and `layer_b.py` take `--corpus-def` (`corpus_select.py`, defaults in `eval/m1-tamagai/corpus_def.py`), and `layer_b.py` takes `--out`. The tamagai defaults reproduce M1's constants.

**v6 regression (tamagai, M2 engine):**
- Layer A, dev plus held-out (48 tasks × 4 conditions): identical recall, shown spans, call counts and authority results. Tokens moved by −8 to +14 per task, from the generation id and status text.
- Layer B: 12/12 deterministic, 0 false-clean, 4/4 identity, 6/6 freshness, also after the harness refactor.
- Latency was measured at load average about 8 from other processes: Layer B warm p95 0.30 s (SLO 0.5 s), rebuild 2.2–2.9 s (SLO 5 s). A single warm call on an idle shell takes 0.15 s, M1's figure.

**Final runs, first pass (frozen code).**
- v6 regression: Layer A has 0 differences from M1 over 48 tasks × 4 conditions (tokens −8..0); Layer B matches M1.
- tamagai-v7: Layer B 12/12, 4/4, 6/6. Layer A matches v6 for B1 and for specdex-B recall; two specdex-B span swaps come from file-name heading paths shifting BM25. specdex-A and B0 differ where `rg` walks the new paths.
- Barracuda: Layer A as in the report; latency 0.14 s warm p95 and 0.44 s rebuild.

**Independent review** (workflow: 4 reviewers — config, roles and extraction, tickets, profile and packaging — each followed by an adversarial verifier). 40 findings, all confirmed; about 30 distinct after overlaps. Fixed test-first:
- **Security, M1-era:** the hash-pinned `lint_spine.py` ran with its own folder on `sys.path`, so a module planted beside it was imported. Validators now run with `python -I`.
- **Validator, M1-era:** `lint_spine` sets `ok: false` whenever it has findings, and specdex read that as a failure, so spine findings were never reported. `ok: false` is now a failure only without findings or with `error`.
- **Classification:**
  - archives inside an initiative are trail;
  - frontmatter `type` refines only owners, tickets and unmatched files (an archived or working spine copy stays trail);
  - epic-altitude spines are document-scoped beside the initiative spine;
  - `intent.md` and `idea-*` are rationale;
  - a main file linking to unindexed section files beside it (a migrated sharded document) raises `unsupported-layout`;
  - a sharded v6 PRD under a custom `planning_artifacts` selects v6 again.
- **Roles:**
  - rationale and tickets outside the active initiative are noncurrent (backlog tickets stay current);
  - `records` decides only the types it names, instead of making every unnamed owner noncurrent;
  - `status` prints the records setting, and `no-active-initiative` is not raised when records decide;
  - an active initiative that is not an `initiative-*` folder (a backlog folder, as `bmad-ticket` allows) leaves records to the type rule;
  - `output_folder = "{project-root}"` keeps the scope;
  - an unset `{active_initiative}` drops its path segment.
- **Extraction (v6 regression):** a lowercase-led bold lead (`**SM-1 weekly active readers**`) defines again. A sentence-shaped lead is dropped only when the same file defines the ID elsewhere, as in Barracuda's acceptance list.
- **Configuration:**
  - malformed or incomplete settings and non-UTF-8 layers exit 3 with one line;
  - unknown `[workflow]` keys raise `unknown-setting`;
  - a legacy overlay holding a TOML date loads;
  - config diagnostics are part of the index fingerprint;
  - the deprecation message spells out the overlay mapping;
  - `diff` and `--rev` select each revision's profile from that revision's tree, so a diff across the v6→v7 migration no longer reports every FR as added.
- **Packaging:**
  - the profiles carry coverage defaults (FR for tickets and architecture, UJ for UX);
  - the smoke test checks the one-line failure;
  - README, `customize.toml` and `reading-results.md` state the role precedence, the records semantics and the overlay mapping.
- **Tickets:** delegated to a subagent working on `tickets.py`, `coverage.py` and a new test file (see below).
- **Tickets** (subagent, test-first, 23 tests in `tests/test_v7_tickets.py`, 21 failing before the fix):
  - leaf vs epic is stored per ticket: an initiative's own entries were counted as epics;
  - dropped work (`tracker_status`, plan `status`, container `status`) is never coverage and is listed apart;
  - tickets have unique keys, so repeated refs no longer misattribute `refs` and `impact` rows;
  - ids of an epic-local spec need not be in the epic's covers; a definition line naming a parent (`CAP-1 (FR-4)`) is followed, otherwise the state is `local`;
  - leaf files no entry lists, and id-less leaves (by file stem), are tickets, as in `bmad-ticket`'s reader;
  - every `backlog*` folder is checked; with no record files, `covers` reports one `scope-incomplete` problem;
  - an ambiguous backlog cover is `ambiguous-source`;
  - document-scoped coverage is keyed by path and id;
  - a trailing TOML comment on an `id` line no longer breaks the `covers` line;
  - a leaf without `covers` falls back to its entry's;
  - `coverage` with no family exits 2.
- **Tests:** 241 unit tests (176 M1, 65 M2) and 5 smoke tests pass; Toolsmith's checks still pass.

**Final runs, after the review fixes:**
- v6 regression: 0 differences from M1 (tokens 0..+16).
- tamagai-v7: the same pattern as before.
- Barracuda: 0 differences from the pre-review run.
- Layer B on both layouts: 12/12, 4/4, 6/6.
- Latency: Barracuda 0.16 s warm p95 and 0.47 s rebuild; tamagai 0.15–0.16 s and 1.6–1.7 s.

The report is in `docs/m2-report.md`.

**Follow-ups (owner: "do all these").**
- **Barracuda install:** specdex reinstalled as 0.2.0. `-a claude-code` alone copied it into `.claude/skills` and left the old `.agents` copy behind. That copy was removed and the install repeated with `-a claude-code -a codex`, which restores the shared layout.
- **Barracuda settings:** the evaluated settings were added; the `ux` coverage key was dropped because it is now a profile default.
- **Barracuda spines:** `bmad-ux` and `bmad-prd` updates removed the voided passages and the PRD's void list.
- **Report:** published as a private page.
- **Commit:** M2 committed.
