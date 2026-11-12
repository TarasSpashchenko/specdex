# specdex M3 worklog (current BMad v7)

## 2026-11-11

**Baseline:** `1f6279d` (M2 plus BMad `a867e160` installed by the Skills CLI and `bmad setup`). Branch `m3-bmad-v7-current`. Plan: `docs/m3-plan.md`; the owner delegated every decision, and the proposed owner decisions were taken as written.

**Phase 1, fixtures.** Built by a subagent from BMad's own templates and accepted by BMad's own scripts:
- `tests/fixtures/v7-current/`:
  - a parent initiative with a charter, and two child initiatives (one active, one without epics);
  - initiative and epic PRDs, a BRD, a brief, UX, spines at both altitudes and a dropped epic;
  - the backlog, an archive and `.template.md` copies;
  - byte-identical copies of `check_ids.py` and `tickets.py`.
  - `tickets.py status` exits 0 with no problems on every folder, and `check_ids.py` reports nothing.
- `tests/fixtures/v7-current-sharded/prd-cart/`: the PRD after `bmad-shard-pro`'s `shard_tool.py build`.
- `tests/fixtures/v7-folded/`: `v7-project` after `migrate_v6.py --fold-specs` and migration-2's moves. The fold ran first, as `bmad migrate` orders them.
- The resolver copies in `v7-project` were refreshed (X5).

The first run on the fixture reproduced the plan's breakages:
- epic R ids were demoted below the initiative's by owner rank;
- epic-spine R binds dangled;
- a withdrawn ID's own line was a `citation-historical`.

The fixture brief also gave the epic spine its own `AD-1` beside the inherited one, which specdex rightly flags as `inherited-conflict`. The fixture was corrected to `AD-3`.

**Phases 2–4, implementation:**
- **`layout.py` (new):** both ticket layouts. Covers the `tickets/` folder rule, parent initiatives from `[[initiative]]`, and the container map that document-scoped resolution walks.
- **`tickets.py` (rewritten around one trace):**
  - Requirements-line items: `parent R3`, typed `prd FR-2`, a section, or a folded CAP alias.
  - A ticket's sources are its `sources:` (project root, then the ticket's folder, since the fold writes relative paths). References lines count only when `sources:` is absent, as BMad's tree check requires.
  - Child initiative records, and kind taken from the container file's `type`.
  - The same `trace()` serves ticket chains and architecture coverage.
- **`extract.py`:**
  - `template:` classification, and shards classified as their main file.
  - The check_ids definition forms, with table groups and withdrawn marks.
  - R ids are recorded only in covers, Requirements and binds contexts.
  - Word and dash range separators, with bold ends.
  - Only the first occurrence of an ID on its line defines it (`R1 (parent R1)`).
- **`resolve.py`:**
  - The active initiative plus its parents are the current folders.
  - Records are grouped per (type, container) under an active initiative.
  - Shards follow their main file's role and are read in the map's order.
  - Tickets define the R ids they own, and rank competes only within a scope.
  - Re-citing tables are decided across files, parents first.
  - Document-scoped citations go to the citing document's container.
- **`store.py`:** schema 6 (`cand.grp`, `cand.withdrawn`, `files.part_of`).
- **`coverage.py` and `maintenance.py`:**
  - Coverage exits 1 on an empty population or an incomplete scope.
  - `lint` adds `ticket-*` findings at the covers' location.
  - A withdrawn ID's own line is no citation.
- **Profile `bmad-v7` release 2:**
  - New families: RULE, OQ, BR, SC and R (with contexts).
  - `[templates]`, the srs/brd/agent-spec/charter owners, and new trail rules: `archive/`, `.source/`, map pages, the identifier lookup, `.template.md`.
  - `[current] hint`, `[tickets] backlog` set to `backlog/` only, and `alias_families`.
  - Range separators, and bindings re-pinned to `a867e160`.

**Two decisions taken during the work:**
- **Engine documents only.** The first October-v7 regression run on tamagai showed 11 Layer A differences. tamagai's PRD lists assumptions as `- FR-2 — Default bedtime …`, which check_ids reads as definitions, giving 29 false duplicates. The check_ids forms now apply only to documents `bmad-facilitate` wrote (a `template:` key) and to their shards. Older PRDs keep M2's forms. After this the regression is identical.
- **Sentence leads.** `**FR-2 is verified by …**` stays a citation when the file defines FR-2 elsewhere, as in M2. This is a documented deviation from check_ids.

**Tests:** 278 pass (241 from M2, one of them rewritten for `backlog/` only; 31 in `test_v7_current.py`; 6 in `test_conformance.py`). The conformance tests capture `check_ids.py`'s own per-line definitions and references and compare them with specdex's line by line. They run BMad's `tickets.py status` through `uv`.

**Packaging:**
- `bmod.toml` 0.3.0.
- Routing text names `bmad-agent-pm`, `bmad-agent-analyst`, `bmad-ux`, `bmad-architecture` and `bmad-agent-po`.
- `SKILL.md` is 952 tokens (the gate) with a 464-character description.
- `validate_manifests.py`, `init_skill.py --check --any-name`, `scan_paths.py`, `scan_scripts.py` and `prepass.py` report nothing.

**Drift check:** upstream `main` is still `a867e160`.

**Evaluation tooling (subagents):**
- `eval/m3-v7-current/make_v7_current.py` applies migration-2 to a copy of a corpus, including its path rewrites and BMad's spec fold. Neither corpus has much to convert: tamagai-v7 has no ticket tree, so the copy is byte-identical, and Barracuda only moves one `tickets.toml`.
- `compare_current.py` reruns M2's Layer A under the path map and captures `status`, `lint`, `covers` and `coverage`.
- `layer_b_current.py` reuses M1's Layer B harness:
  - re-targets B07–B09 to a ticket tree in the current layout inside tamagai, which BMad's `tickets.py status` accepts;
  - adds B14 (a Requirements line loses its parent), B15 (the PRD leaves `sources:`) and B16 (an FR edited inside a shard; the PRD is sharded with BMad's `shard_tool.py`).

The first Layer B run found four specdex bugs, which were fixed test-first:
- a bare epic line `- R2:` passed as clean; it is now `no-source`;
- a story's R id that its epic lacks fell through to the initiative's R id of the same number;
- a shard of a pre-engine PRD was read with the engine's forms; a shard now keeps both rule sets and derive picks the one its main file's `template` calls for, idempotently when only the main file changes;
- `diff` compared only the last definition of a duplicated ID.

**Review (workflow: four dimension reviewers, adversarial verification of the top two findings each).** 21 findings; the 6 verified ones were all confirmed real. The 15 unverified ones were triaged here: 13 were fixed, one is the Layer B shard finding already fixed, and one was a claim about the conformance test that is now covered by a test. Fixes, each with a regression test:
- **Ticket tree:**
  - a story's R id falling through to the parent's;
  - an unsliced initiative's spine binds were dropped (containers now also come from container files);
  - `R4 (parent)` with no parent id;
  - a source ID must sit in the ticket's own `sources:` (October tickets keep walking up);
  - cycle guards on parent initiatives;
  - ranges inside Requirements parentheses;
  - the own-folder covers exemption applies to epics only (it had regressed October initiatives);
  - an undefined CAP is a folded alias only once no spec remains;
  - a per-container cache of source files;
  - `refs` on an R id lists `tickets.toml` entries.
- **Records and IDs:**
  - the `records` setting decides per container inside the active tree;
  - a container's own R definitions never resolve against its parent;
  - parent initiatives are read first, by ancestry, not by name;
  - sentence leads are decided per sharded document.
- **check_ids port and profile:**
  - CRLF files;
  - IDs in fenced code and comments are no citations in engine documents;
  - an ID of an unknown family opening a table row ends the row;
  - October PRDs define OQ and RULE with bold leads.
- **Declined T11:** the backlog stays `backlog*`, because the v6→v7 migration wrote `backlog-<slug>/` folders. The M2 test is restored.

**Trigger evals (`bmad-eval`, 16 queries × 3 runs, 0.2.0 vs 0.3.0):**
- No regression: 14/16 real loads on both, failing the same two queries (q7 under-triggers, q10 fires on an edit request).
- The runner itself counted 7 false loads, where the canary token appeared in tool output; this is a `run_triggers.py` issue, not specdex's.
- The harness was recorded in the personal `_bmad/custom/bmad-eval.user.toml`.

**Tests:** 298 pass, plus 5 smoke tests.
