# specdex M3 plan: current BMad v7 (2026-11-11)

specdex 0.2.0 was built against BMAD-METHOD `2fe54695` (2026-10-03). The BMad installed in this repository is `a867e160` (2026-11-07). Since then:
- Sofia (`bmad-agent-po`) replaced `bmad-spec`, `bmad-ticket` and `bmad-correct-course` (`3a67c86f`);
- each container's breakdown moved into a `tickets/` folder (`49fd27e4`, `bmod-method/migration-2.toml`);
- PRDs and the other planning documents moved to `bmad-agent-pm` and `bmad-agent-analyst` on the `bmad-facilitate` engine, with new templates (`7687d077`, `a867e160`);
- `bmad-shard-pro` joined core-tools (`dc9fbb14`).

On sample projects built from the current templates, specdex:
- reports every FR `missing` in `coverage --by tickets` and `--by architecture`;
- raises `ambiguous-current` on epic-level documents;
- treats as undefined the FR, UJ and SM ids written in forms that BMad's own `check_ids.py` accepts.

Its 241 tests pass only because the fixtures use the October layout. Packaging still passes Toolsmith. This plan makes specdex correct on the current layout without losing v6 or the October v7 layout (no `tickets/` folder).

## Findings

| ID | Finding | Severity |
|---|---|---|
| T1 | Breakdown, epic folders, leaves and plans sit in `<container>/tickets/`, so containers are not found and every chain is unresolved | breaks |
| T2 | An initiative with no epics is typed by folder name; under `tickets/` it becomes an epic with no parent | breaks |
| T3 | Leaf refs lose their epic id (`1` instead of `1.1`), as a consequence of T1 | degrades |
| T4 | Epic Requirements lines are `R1 (parent R3)`; `parent R3` is read as one id | breaks |
| T5 | Initiative lines carry several ids, type prefixes or section names: `R1 (FR-2, FR-5)`, `prd FR-2` | breaks |
| T6 | The PRD is named in frontmatter `sources:`, not by a `prd —` References line | breaks |
| T7 | Specs fold into tickets (`migrate_v6.py --fold-specs`); `CAP-n` survives only inside a Requirements line's parentheses | degrades |
| T8 | `R<n>` ids are definitions now ("the ticket is the spec at its altitude"); `resolve R1` says not defined | degrades |
| T9 | Parent initiatives (`[[initiative]]` tables); a child's chains cannot reach the parent's file | degrades |
| T10 | `sources:` and `companions:` are paths from the project root; specdex resolves companions from the file's folder | degrades |
| T11 | Backlog is `backlog/` only; `backlog*` still counts other folders | cosmetic |
| P1 | The spine binds the ticket's `R<n>` ids, not FR ids | breaks |
| P2 | PRD and UX documents at epic level are owners beside the initiative's, which raises `ambiguous-current` | breaks |
| P3 | A v6 migration keeps dated PRD folders in the initiative; two of them stay ambiguous with no actionable hint | breaks |
| P4 | Ids are defined in forms `check_ids.py` accepts but the profile does not: `- FR-2:`, `FR-4.`, plain `UJ-3.` lines, table first cells | breaks |
| P5 | New id families: RULE, OQ (prd), BR (brd, srs), SC (agent-spec) | degrades |
| P6 | Ranges `to`, `through`, `—`, `-` are not expanded | degrades |
| P7 | Engine documents carry `template: <id>`, not `type:`; brd, srs, agent-spec and the sponsor templates end up unverified | degrades |
| P8 | `bmad-shard-pro` shards (`part_of:` frontmatter, original in `.source/`) are not indexed | degrades |
| P9 | `archive/` (no dash), `.template.md` (engine copy) and shard `.source/` are not trail | cosmetic |
| X1 | Bindings: 5 pinned files are gone and 2 have changed, so every answer is `unverified` | degrades |
| X2 | `SKILL.md`, `help/help.md` and `README.md` route edits to skills that no longer exist | degrades |
| X3 | `coverage` exits 0 on an empty population or an incomplete scope | breaks (scripts) |
| X4 | `lint` has no ticket checks, so a tree specdex cannot read looks clean | degrades |
| X5 | The resolver copies in `tests/fixtures/v7-project` no longer match BMad's bytes (the behavior is the same) | cosmetic |

## Owner decisions (taken as proposed under the owner's delegation, 2026-11-11; deviations in `docs/m3-report.md`)

| Item | Proposal |
|---|---|
| October v7 trees | Keep reading them with the same reader until projects migrate. `tests/fixtures/v7-project` stays as their regression. |
| Profiles | Update `bmad-v7` in place, pinned to `a867e160`; no third profile. Projects on an older BMad show `profile … (unverified)` but are read correctly. |
| Shards | In scope (phase 5). It can move to M4 without touching the other phases. |
| Corpus | A committed fixture, `tests/fixtures/v7-current/`. The eval corpus `tamagai-v7-current` is generated from M2's tamagai-v7 corpus by a committed script. Barracuda is checked live only after you migrate it (`bmad setup` offers migration-2). |
| Git | Branch `m3-bmad-v7-current` from `1f6279d`. Commits only on request; no push. |

## Design decisions (delegated)

| Item | Decision |
|---|---|
| Target | BMad `a867e160`. A drift check against BMad HEAD closes the milestone. Later changes go to M4 unless they break a gate. |
| Ticket tree (T1–T3, T11) | One reader for both layouts:<br>• a `tickets/` folder holding `tickets.toml` belongs to its parent folder, which is the container (file `<container>/<container>.md`);<br>• epic folders are `<container>/tickets/<epic-slug>/`;<br>• without a `tickets/` folder, the October rule applies;<br>• kind comes from the container file's `type`, then the folder prefix;<br>• display refs stay `<epic>.<id>`;<br>• backlog is `{output_folder}/backlog`. |
| Requirements lines (T4, T5, T7) | `R<n> (<items>): …`, with comma-separated items:<br>• an `R` id, with or without `parent`, is the parent link;<br>• another id, optionally type-prefixed (`prd FR-2`), is a source id;<br>• a `CAP-<n>` from the spec fold is an alias of `R<n>` with no source;<br>• anything else is a section citation, and the chain is `local` (unknown, never `missing`).<br>The October `R1 (FR-1)` is the one-item case. |
| Sources (T6, T10) | A container's requirement sources, in order:<br>1. frontmatter `sources:`;<br>2. `prd —`/`spec —` References lines (October trees);<br>3. a `spec-*` folder inside it.<br>`sources:` and `companions:` resolve from the project root. |
| Parent initiatives (T9) | Read `[[initiative]]` tables. The current scope is the active initiative plus its ancestors; only the active tree is checked. A child's parent links resolve in the parent's file. |
| R ids (T8) | Family `R`, document scope:<br>• defined only by the Requirements lines of container files;<br>• cited only in `covers` (frontmatter and `tickets.toml`), Requirements parentheses and spine binds (frontmatter and `**Binds:**` lines), never in prose.<br>Document-scoped resolution moves from "same folder" to "nearest container ancestor of the citing file", so a story under `epic-x/tickets/` resolves `R1` in `epic-x/epic-x.md`. |
| Requirement trace (P1) | One function in `tickets.py` follows `R<n>` through parent links to source ids. Ticket chains and architecture coverage both use it. A spine binds the R ids of the container its run folder sits in; binds to FR ids still count. |
| Id definitions (P4, P6) | One shape for planning documents mirrors `bmad-facilitate/scripts/check_ids.py`. An id is defined where it opens:<br>• a heading;<br>• a table row's first cell;<br>• a bold table cell, list item or line;<br>• an unbolded list item or line only when punctuation follows.<br>Not definitions:<br>• an id opening a list of ids;<br>• rows of a table that mostly re-cites earlier ids.<br>Other rules:<br>• `withdrawn`/`removed`/`dropped`/`superseded` definitions are historical;<br>• fenced code and HTML comments are skipped;<br>• ranges are `–`, `—`, `-`, `to`, `through`, plus `…` and `..`.<br>The v6 profile and project `[[workflow.define]]` shapes are unchanged. |
| Families (P5) | Add RULE and OQ (owner prd), BR (brd, then srs) and SC (agent-spec); FR also owned by agent-spec. SM-C and CAP stay for older documents. |
| Document types (P7, P9) | The profile maps frontmatter `template` as well as `type`.<br>• Owners: prd (with prd-light), srs, brd, agent-spec, brief, the UX pair, the spine.<br>• Rationale: the other engine templates (opportunity, business-case, charter, narrative, pitch, launch, experiment, prototype-plan, prfaq, decision-record, postmortem, security-review, proposal, pitch-deck).<br>• Trail: `{output_folder}/archive/**` and `**/.source/**`.<br>• `.template.md` is skipped. |
| Altitude and records (P2, P3) | Owners are grouped by type and container (the folder that holds the run folder), not by type alone, so an epic PRD and its initiative's PRD are both records. Two owners of one type in one container stay `ambiguous-current`; the diagnostic names the `records` setting and `archive/` as the fixes. PRD ids are global across altitudes: template-prd.md:23 says "Ids … are global", and :19 says an epic PRD "cites its parent's ids rather than restating them". So an id defined at two altitudes is a `duplicate`, as `check_ids.py` reports it. |
| Shards (P8) | A `.md` whose frontmatter `part_of` names a main file is part of that document: same type and role; its definitions count as the document's; citations point at the shard's lines. The v6 `index.md` probe stays. |
| Exit codes and lint (X3, X4) | `coverage` exits 1 on an empty population or an incomplete scope. `lint` adds the `covers` chain problems as `ticket-*` findings. |
| Bindings (X1) | Re-pin these files; not `tickets.py`, which changes with every fix and is covered by the conformance test:<br>• `bmod-method/bmod.toml`;<br>• `bmad-agent-pm/assets/template-prd.md`;<br>• `bmad-architecture/assets/spine-template.md` and `scripts/lint_spine.py`;<br>• `bmad-ux/references/design-md-spec.md`;<br>• `bmad-agent-po/assets/ticket-template.md` and `tickets-template.toml`;<br>• `bmad-facilitate/scripts/check_ids.py`. |
| Routing text (X2) | `SKILL.md`, `help/help.md`, `README.md` and `references/reading-results.md` name the current owners:<br>• `bmad-agent-pm` through `bmad-facilitate`: PRD and planning documents;<br>• `bmad-agent-analyst`: brief and BRD;<br>• `bmad-ux`;<br>• `bmad-architecture`;<br>• `bmad-agent-po`: tickets and specs.<br>The description stays under 500 characters. |
| Conformance oracles (X5) | As M2 did with the resolvers, the new fixture carries byte-identical copies of `check_ids.py` and `_bmad/method/scripts/tickets.py`. Tests compare:<br>• specdex's defined and referenced ids per prefix, duplicates and undefined ids with `check_ids.py`;<br>• its ticket list (refs, status, dropped) with `tickets.py status`.<br>`tickets.py` needs PyYAML, so that test runs through `uv` and is skipped without it. The resolver copies in `v7-project` are refreshed. |

## Phases and checks

1. **Fixtures and failing tests.** `tests/fixtures/v7-current/`, built from the current templates:
   - A parent initiative and two children. The active child holds:
     - an initiative PRD with ids in every `check_ids` form, plain-line UJs, RULE, SM, OQ, a withdrawn FR, a re-citing table and `FR-1 to FR-4`;
     - a brief, a BRD, DESIGN/EXPERIENCE, and a spine binding R ids;
     - `tickets/` with one epic carrying its own PRD, UX, spine, stories and plans;
     - a dropped container.
   - A second child with no epics.
   - `backlog/`, `archive/`, a sharded PRD and `.template.md` copies.
   - A spec folded by BMad's `migrate_v6.py --fold-specs` from a copy of `v7-project`.

   BMad's `tickets.py status` and `check_ids.py` must accept the fixture. Check: every finding has a test that fails on the baseline for the expected reason, and the 241 tests still pass.
2. **Ticket tree** (T1–T7, T9–T11). Check:
   - `covers` and `coverage --by tickets` match hand-derived expectations;
   - the ticket list equals `tickets.py status`;
   - `v7-project` and `preview-tickets` results are unchanged.
3. **R ids and the requirement trace** (T8, P1). Check: `coverage --by architecture` is the same with the R-binding spine and an FR-binding variant; `resolve R1` lists each container's R1, and citing files resolve to their own container's.
4. **Planning documents** (P2–P7, P9). Check:
   - `check_ids` conformance is exact on every fixture planning document;
   - epic and initiative documents are both records;
   - two PRDs in one container are still ambiguous, now with the hint;
   - parent documents are current;
   - `mini-project` (v6) results are unchanged.
5. **Shards** (P8). Check: `resolve`, `refs`, `get`, `coverage` and `lint` answer the same on sharded and unsharded copies of the PRD, apart from paths and lines.
6. **Surface and packaging** (X1–X5). Covers:
   - exit codes and the lint additions;
   - bindings, routing text and profile comments;
   - `bmod.toml` version 0.3.0;
   - in the README: layouts table, limits, and deviations (`init_skill.py --check` needs `--any-name` for the unprefixed name).

   Check:
   - Toolsmith's checks as in M2;
   - `prepass.py` reports no finding, with `SKILL.md` no larger than today's 952 tokens;
   - no trigger case in `evals/triggers.json` regresses against a `bmad-eval` run of 0.2.0 made at the start.
7. **Evaluation** (below).
8. **Report** in `docs/m3-report.md`, with the worklog in `docs/m3-worklog.md`.

## Evaluation

- **Regressions:**
  - v6: M1's Layer A development run and Layer B run on tamagai give results identical to M2's v6 regression.
  - October v7: `eval/m2-v7` on tamagai-v7 gives results identical to `eval/m2-v7/results-tamagai-v7`.
- **Current v7:** `eval/m3-v7-current/make_tamagai_v7_current.py` converts the tamagai-v7 corpus:
  - moves breakdowns into `tickets/`;
  - folds specs with BMad's `migrate_v6.py --fold-specs`;
  - adds `template:` frontmatter;
  - writes a path map.

  BMad's `tickets.py status` must accept the result.
  - Layer A (development and held-out) must equal the October v7 results under the path map. Tasks on folded specs are re-targeted to the ticket that absorbed them.
  - Layer B re-targets M2's mutation classes and adds three, each with a clean control: an R line loses its parent, a PRD leaves `sources:`, and an FR is edited inside a shard.
- **Barracuda:** after you migrate it, the profile is verified, the records are as expected and `lint` is clean. Results go in `eval/local/`.
- **Gates:**
  - all tests pass, and both conformance tests are exact;
  - zero false-clean results: no `missing` where the truth is declared, and no exit 0 on an incomplete scope;
  - both regressions are identical;
  - sharding is answer-invariant;
  - latency stays within M2's gates (warm p95 ≤ 500 ms, full rebuild ≤ 5 s at 1×), on Barracuda once migrated, otherwise on tamagai-v7-current.

## Risks and open questions

- BMad v7 is pre-release, with GA expected in mid-November 2026, and formats may move again. Mitigations: the pin, the conformance tests against BMad's own scripts, the closing drift check, and keeping each rule in the profile rather than in code.
- "PRD ids are global across altitudes" is inferred from the template and from `check_ids.py`'s cross-file duplicate rule; BMad does not state it outright. If BMad numbers epic PRD ids locally, PRD families switch to document scope with phase 3's nearest-container resolution, which is a profile change.
- Sponsor documents (business-case, narrative) may list ids in `## For requirements`. M3 indexes them as rationale, so those ids are not definitions. Revisit this if tickets cite them.
- `bmad-shard-pro` also writes an identifier lookup beside the shards; its role (trail or skipped) is settled in phase 5.
- Out of scope: remote content in tracker stores, and semantic agreement between documents.
