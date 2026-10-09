# specdex M2 plan: BMad v7 compliance (frozen before coding, 2026-10-09)

BMAD-METHOD "next" still reports version `6.13.0-next`, but its planning skills now write into initiative folders, `bmad-ticket` replaced `bmad-preview-ticketing`, and Toolsmith replaced BMad Builder and sets the packaging rules. specdex M1 targeted the earlier dated v6 layout. On a v7 project (Barracuda) it finds no record files, reports `unsupported-layout`, and answers `resolve FR-1` with "unknown". This plan makes specdex work on v7 and pass Toolsmith's checks without losing v6 support.

## Owner decisions (2026-10-09)

| Item | Decision |
|---|---|
| v6 support | Keep it. Ship a v6 profile and a v7 profile, and pick by layout. M1's eval stays reproducible. |
| Settings | Go BMad-native: ship `customize.toml`; read overrides (`_bmad/custom/specdex.toml`, `.user.toml`) through `resolve_customization.py`. Still read a legacy `_bmad/custom/specdex-overlay.toml` for one release, with a deprecation diagnostic. |
| Corpus | Tests use a committed synthetic v7 fixture. The M1-style eval runs on a frozen Barracuda snapshot whose corpus and gold sets stay out of git. |
| Git | Baseline `33b77c7`. Commits only on the owner's request; no push. |

## Design decisions (delegated)

| Item | Decision |
|---|---|
| v7 detection | The version string is the same for both layouts, so specdex probes the layout. v7 when `core.active_initiative` is set or any `{output_folder}/initiative-*/` folder exists; v6 when `{planning_artifacts}/prds/prd-*/prd.md` (or the brief, UX or spine v6 globs) match and no initiative folder exists; v7 otherwise. `--profile` still overrides. `status` prints the profile and why it was chosen. |
| v7 artifacts | Main files are matched by rule option `main = true`: the file stem equals its parent folder name (`prd-x/prd-x.md`). Owners: brief and addendum, PRD and addendum, `DESIGN.md`, `EXPERIENCE.md`, `architecture-<slug>.md`, and `spec-<slug>.md` (also inside epic or initiative folders), each inside an initiative or loose under `{output_folder}`. The UX router `ux-<slug>.md` is rationale. Trail: `review-*`, `reconcile-*`, `validation-report.*`, `reviews/`, `.working/`, `imports/`, `mockups/`, `wireframes/`, `change-*`, `migration-v6-v7/`, `archive-v6/`, `inbox/`, `deferred-work.md`, `discussion-*/`. Research, brainstorm, forge and PRFAQ folders are rationale. Tickets follow `bmad-ticket` (below). |
| Frontmatter `type` | Only the v6→v7 migration writes it, so path rules stay primary. `type` refines a path type only where the profile maps it (`prd`, `brief`, `ux` → router, `initiative`, `epic`, `story`, `bug`, `spike`, `migration` → trail, `architecture-spine`). |
| ID families | The v7 profile keeps the template families (FR, UJ, SM, SM-C, AD, CAP, TOKEN). FR is defined by heading (template) or by a bold item lead (`- **FR-N. …**`, Barracuda). Project families (NFR, AT, AI, L…) stay in customization. |
| Current record | With `active_initiative` set, owners inside `{output_folder}/{active_initiative}/` are the candidates; one per type is the record, several are ambiguous (document-scoped specs excepted); owners elsewhere are `noncurrent`. Unset: the M1 rule (one per type, else `ambiguous-current`) plus a `no-active-initiative` diagnostic. A `records` list in customization still wins and may use `{active_initiative}`. |
| Config | Worktree mode calls `{project-root}/_bmad/scripts/resolve_config.py` (with the running interpreter, not `uv run`, to keep latency down) for `core.output_folder` and `core.active_initiative`, and `resolve_customization.py --skill {skill-root}` for settings. The built-in reader stays only for git revision snapshots and projects without `_bmad/scripts/`; `status` names which reader ran. |
| Customization shape | One `[workflow]` table in `customize.toml`, whose arrays of tables mirror the overlay tables and carry `id` so team and user layers can replace them (BMad keyed merge). |
| Tickets | `bmad-ticket` tree: an initiative `tickets.toml` with or without `[[epic]]`, keyed by the `initiative-` folder prefix; `backlog/` leaves; `next_id`, `after` (sibling, `<epic>.<entry>`, `epic-<slug>`, `{epic, needs}`), `dropped`/`blocked`, alphanumeric ids; status from plans; specs at `spec-<slug>/spec-<slug>.md`. |
| Bindings | The v7 profile pins the installed templates, `lint_spine.py`, the `bmad-ticket` assets and `bmod-method/bmod.toml` at their current hashes. Drift shows as `profile … (unverified)`, as in M1. Validator commands use the running interpreter. |
| Packaging | Pass Toolsmith validate: install messages in `bmod.toml`, a `bmad` entry in `required_skills`, `uv run` in `SKILL.md`, a description under 500 characters that names the owning skills (`bmad-prd`, `bmad-ux`, `bmad-architecture`, `bmad-spec`, `bmad-ticket`), `SKILL.md` at about 800 tokens with output-reading detail moved to `references/`, profiles moved to `assets/profile-*.toml`, a shipped `scripts/tests/test_specdex.py` smoke test, `evals/triggers.json`, and no install mechanics in `help.md`. |
| Kept deviations | Running `bmad-architecture/scripts/lint_spine.py` (hash-pinned, read-only); the unprefixed name `specdex`; the `scripts/specdexlib/` package; text output by default (`--json` available); `update_source` stays `file:` until the repository is published. Each is listed in `SKILL.md`'s references and the report. |

## Phases and checks

1. **Fixtures and failing tests.** A synthetic v7 project (`tests/fixtures/v7-project/`) with two initiatives, loose and archived documents, every artifact type, a `bmad-ticket` tree, `_bmad/config.toml`, `_bmad/custom/config.user.toml` and a copy of BMad's resolver scripts. Check: the new tests fail on the baseline for the expected reasons; the 176 M1 tests pass.
2. **Config, customization and profile selection.** Check: resolver and fallback paths give identical variables on both fixtures; the legacy overlay still works and is flagged.
3. **v7 profile.** Check: every fixture file has its expected type and role; `unsupported-layout` is gone on v7 and still raised for sharded v6.
4. **Record selection.** Check: switching `active_initiative` switches the records; an unset value gives the diagnostic; customization `records` wins.
5. **Tickets.** Check: `covers` and `coverage` on the fixture match hand-derived expectations.
6. **Packaging.** Check: `validate_manifests.py` passes; `init_skill.py --check`, `scan_paths.py` and `scan_scripts.py` report nothing beyond the kept deviations; prepass reports `SKILL.md` at no more than 900 tokens and a description under 500 characters.
7. **Evaluation** (below).
8. **Report** in `docs/m2-report.md`, with the worklog in `docs/m2-worklog.md`.

## Evaluation

- **Corpus:** `eval/corpora/barracuda-2026-10-09/` (git-ignored), a copy of Barracuda as of 2026-10-09 (`_bmad/`, `_bmad-output/`, `.agents/skills/`). Barracuda-specific gold, results and customization live in `eval/local/` (git-ignored); generic harness changes are committed.
- **Layer A (retrieval):** 24 development tasks (8 section, 6 exact, 6 citation, 4 history) labelled under `eval/m1-tamagai/GOLD-SPEC.md`, drafted by subagents and checked by an independent verifier. Scoring, tokenizer and baselines B0/B1 as in M1. No held-out set or agent replay in M2: M1 established both, and M2 changes indexing, not search.
- **Layer B (maintenance):** the 12 M1 mutation classes and 4 identity cases, re-targeted to the v7 corpus, each with a clean control.
- **v6 regression:** M1's Layer A development run and Layer B run on the tamagai corpus.
- **Gates:** all tests pass; every deterministic gold case is correct; zero authority or freshness failures; ambiguous scopes never return false-clean results; Layer A median lookup tokens on section and exact tasks at least 30% below the stronger baseline; Layer B at least 11 of 12 mutations flagged with zero false-clean and 4 of 4 identity cases; the v6 regression matches the M1 report's numbers; at 1× on Barracuda, warm verified lexical p95 at or below 500 ms with the resolver calls included, and full rebuild at or below 5 s.
