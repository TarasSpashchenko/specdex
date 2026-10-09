# Codex M1 re-check

**Verdict (judgment): 11 resolved, 18 partly; M1 acceptance remains unproven.** The fixes address most original reproductions, but read-only enforcement, complete negatives, scoped identity and independent evaluation remain incomplete. Four introduced regressions are reproduced below. **Facts:** all 154 unit tests pass; the saved dev Stage A gate correctly fails (16/20 completions versus B1's 19/20). No replay transcripts were opened; held-out gold was neither read nor edited. Repository writes were limited to this report; all reproduction indexes and fixture mutations were under `/tmp`.

| finding | status | evidence (`path:line` or output) | remaining action |
|---|---|---|---|
| A-01 | partly | `skills/specdex/scripts/specdexlib/maintenance.py:163` verifies the entry script; execution at :148 has no write containment. R2 replacement is blocked; hash-approved replacement still writes (`verified-validator-write [] 1`). | Contain verified adapters and their dependencies; hash checking fixes only the unverified-entry case. |
| A-02 | partly | `skills/specdex/scripts/specdexlib/index.py:49` rejects resolved in-project destinations. `skills/specdex/scripts/specdexlib/store.py:79` still recognizes foreign databases by three table names; a foreign `meta/chunks/files/valuable_notes` database loses `valuable_notes`. | Require reliable ownership before dropping tables; preserve unrelated tables. |
| A-03 | resolved | `skills/specdex/scripts/specdexlib/index.py:66`, :73, :87 pin reads and re-inventory under the lock. R1: `reader True 0`; `inventory False False 1`. | Root race fixed; none for the finding. |
| A-04 | resolved | `skills/specdex/scripts/specdexlib/extract.py:248` classifies overlapping history for every non-file span. R2 parent §1 is `[record; partly historical]`; §1.9 remains historical. | Root labelling fixed; repair coverage integration (N1). |
| A-05 | partly | `skills/specdex/scripts/specdexlib/resolve.py:179` excludes historical definitions from current citations. R1 citation becomes `historical`; `queries.py:246` misclassifies an existing retired positional child (N2). | Check historical candidates before bounds; preserve historical child lookup. |
| A-06 | resolved | `skills/specdex/scripts/specdexlib/resolve.py:239` rejects an ambiguous artifact even with one candidate; `queries.py:239` propagates it to resolve. R1 FR-99 is ambiguous. | Root ambiguity propagation fixed. |
| A-07 | partly | `skills/specdex/scripts/specdexlib/tickets.py:205` supplies covers edges to refs/impact; R2 now finds them. :223 guesses their line from key order and can cite `[[epic]]` instead of `covers` (N3). | Locate the field within the complete TOML block, independent of key order. |
| A-08 | partly | `skills/specdex/scripts/specdexlib/tickets.py:193`, :200 catch R2 ownership bypass and duplicate FR definitions. The global resolve check rejects a uniquely selected document scope (N4). | Resolve and carry a unique source-qualified definition through each chain. |
| A-09 | partly | `skills/specdex/scripts/specdexlib/queries.py:133` counts all parse gaps; `extract.py:188` diagnoses unclosed frontmatter. Input `companions: missing.md` plus `type: [prd]` produces no diagnostics and `none in a fully indexed scope`. | Validate interpretation-affecting field types, not just YAML syntax. |
| A-10 | partly | `skills/specdex/scripts/specdexlib/sources.py:71` blocks external files and reports read failures. :53 uses `os.walk` without `onerror`: a mode-000 source directory yields no `source-skipped` and a definite negative. | Report directory traversal failures as incomplete inventory. |
| A-11 | resolved | `eval/m1-tamagai/run_eval.py:440`, :262 prevent repeated actions/no-progress continuation. R3 S01: `B0 10 10 0.0` instead of 12 outputs/2 distinct. | Repetition root fixed; S01 remains a baseline miss. |
| A-12 | partly | `eval/m1-tamagai/run_eval.py:14` now explicitly calls the experiment oracle-assisted; :150 and :179 still obtain records, boundaries and definitions from specdex. Gold still selects reads/stopping (:256, :272). | Add independent corpus metadata and continuation for independent acceptance evidence. Disclosure fixes presentation only. |
| A-13 | partly | `eval/m1-tamagai/run_eval.py:647` separates per-span containment, first-five spans and workflow union for every condition; :750 computes the failed Stage A gate. Answers/negative claims remain unscored; dev Stage B is explicitly noncomputable. | Judge answers/negative claims independently; distinguish first-five shown spans from ranked retrieval results. |
| A-14 | partly | `eval/m1-tamagai/run_eval.py:660` now reports baseline authority as `None`, rather than a misleading zero; :722 uses overlap and :88 includes retired claims. Only labelled output and task-listed forbidden spans are judged. | Judge authority use uniformly in answers; a disclosed unmeasured baseline is not a verified authority pass. |
| A-15 | partly | `eval/m1-tamagai/replay/replay.py:286` enforces unique corpus paths; :12 identifies the separate judge-input producer. :308 still credits one overlapping heading line (`replay-heading 1.0`), now named `evidence_overlap`. | Use a complete-evidence criterion when claiming retrieval success; retain overlap only as a diagnostic. |
| A-16 | resolved | `skills/specdex/scripts/specdexlib/queries.py:408` offers phrases without requiring another explicit bind and filters named families. R1 returns `all FRs`; R2 `OQ-12-textual []`. | Root scope-discovery fix; interpretation remains explicitly textual. |
| A-17 | resolved | `skills/specdex/scripts/specdexlib/config.py:248` fingerprints effective project variables and code. R1: `variables False 4 unverified unverified`. | Root config invalidation fixed. |
| A-18 | partly | `skills/specdex/scripts/specdexlib/index.py:96` compares identity; R1 retarget reindexes and canonical becomes `second.md`. Generation hashing at :103 still omits identity: two different canonical states report the same generation. | Include identity and completeness-changing diagnostics in generation identity. |
| A-19 | partly | `skills/specdex/scripts/specdexlib/diffing.py:47` keys by folder basename, fixing R1 alpha/beta. Two distinct `spec-shared` folders still overwrite (`same-basename-diff 2 []`); :54 collects citations by bare ID across scopes. | Use full namespace scope for keys, citations and positional groups. |
| A-20 | partly | `skills/specdex/scripts/specdexlib/extract.py:354`, :625 fix R1 short/positional expansion and `config.py:185` rejects invalid tails. `FR-1–201` produces 201 members with `max_members=200`; alphabetic ranges at :634 ignore the bound (`3 26 []`). | Enforce the configured member count for every range form, including alphabetic ranges. |
| A-21 | resolved | `skills/specdex/scripts/specdexlib/queries.py:310` matches the complete numeric section identifier. R1 returns `2 Parent`, not `2.1 Child`. | Root section matching fixed. |
| A-22 | partly | `skills/specdex/scripts/specdexlib/maintenance.py:150` checks exit/JSON-object/`ok`; verified exit 7 produces `validator-failed`; :164 refuses revision adapters. Missing adapters at :134 still add no finding (`missing-validator [] ['lint_spine: not installed']`). | Emit an explicit unchecked finding for missing adapters; validate the findings-array/items contract too. |
| A-23 | partly | `eval/m1-tamagai/run_eval.py:328` adds Binds/exclusion filtering; :366 limits instrumentation to 60 rows. :369 still credits entire lines whose visible excerpt is truncated: `real-refs-hidden-tail False [('ARCHITECTURE-SPINE.md', 5, 5)]`. | Credit visible content only; page limiting alone does not fix excerpt inflation. |
| A-24 | resolved | `eval/m1-tamagai/layer_b.py:440`, :488, :643 add the missing gap/unique-ID/generation controls. B09/B12/F6 rerun PASS; B13 (:504) is explicitly a limitation-message check, and also passes. | Claimed scope and controls corrected; these remain finite cases. |
| A-25 | partly | `eval/m1-tamagai/replay/replay.py:15` states the accounting boundary; :210 counts non-shell tool items (R3 MCP calls = 1). :197 still omits model/config pinning; :139 supplies no B1 manifest/outline protocol. | Pin Codex model/config; replay the claimed B1 condition. Initial context remains outside the stated measurement. |
| A-26 | resolved | `skills/specdex/scripts/specdexlib/extract.py:289` propagates heading markers through descendants. R2 row 186 is `[record; assumption]`. | Root inheritance fixed. |
| A-27 | resolved | `eval/m1-tamagai/results/dev-gold-audit-changes.json` matches all eight current task edits; corrected corpus passages were checked. All 32 tasks' evidence/forbidden ranges remain valid; citation counts remain 9/6/4/7/21/5. | The selected answer-narrowing/removal alternatives address the original label errors. |
| A-28 | partly | `skills/specdex/SKILL.md:35` fixes refs syntax and per-reference soft character-estimated budget. :88 still promises no project writes (A-01); :63 promises missing-validator findings that are absent (A-22). | Align the remaining guarantees with enforcement. |
| A-29 | resolved | `skills/specdex/profiles/bmad-6.13.0-next.toml:246`, `skills/specdex/scripts/specdexlib/extract.py:78`, `skills/specdex/scripts/specdexlib/yamlfm.py:19` use neutral examples. | Documentation cleanup complete; no executable project-specific rule was established by the original finding. |

## Decisive rerun output

R1 ran unchanged from the audit. R2 retained its inputs but caught the newly expected cache/path refusals; the shortened chain output below is from an additional identical-input run. R3 required the new score/parser signatures and metric names. As originally, R3 used a token-count stub: it establishes logic, not independently measured costs. Saved completion/gate results are labelled separately.

```text
R1
range FR-1–60. 60 True ['FR-1', 'FR-2'] []
range FR-1–FR-60. 60 True ['FR-1', 'FR-60'] []
range FR-1.1–FR-1.202. 2 False ['FR-1.1', 'FR-1.202'] [('bad-range', 'medium', 1, 'cannot expand range FR-1.1–FR-1.202')]
range FR-1.2foo 0 False [] []
ambiguity ambiguous: defined in one of several candidate current documents; choose the record in the overlay ['ambiguous']
history historical only (retired or declined; not a current definition) [] ['historical']
reader True 0
inventory False False 1
yaml unknown (parse gaps in _bmad-output/planning-artifacts/prds/prd-demo-2026-01-01/prd.md) [('parse-gap', 'medium')]
section prd.md › PRD › 2 Parent
diff 2 [{'id': 'CAP-1 @ spec-alpha', 'old': '_bmad-output/specs/spec-alpha/SPEC.md:3-3', 'new': '_bmad-output/specs/spec-alpha/SPEC.md:3-3'}]
variables False 4 unverified unverified
retarget 1 _bmad-output/second.md second.md

R2
project-cache-refused ConfigError
project-cache False
external-symlink NotFound unknown (the current artifact set is ambiguous, partly unsupported or partly unreadable (see lint))
foreign-cache-refused ConfigError
unrelated-table-survives True
validator-write 0
bypass [('FR-4', 'not-in-container-covers', 'FR-4')]
ambiguous [('E1', 'ambiguous-source', 'FR-1'), ('E2', 'ambiguous-source', 'FR-1')]
covers-refs [('ticket 1', 5, 'resolved'), ('ticket 1.1', 6, 'resolved'), ('ticket 1.1', 6, 'resolved')]
verified-exit-7 ['validator-failed']
corpus-label addendum §1 21 116 [record; partly historical]
corpus-label addendum §1.9 109 116 [record; historical]
corpus-label prd-tamagai-2026-09-29/addendum.md:186 186 186 [record; assumption]
OQ-12-textual []

R3
B0 10 10 0.0
baseline-authority 0
baseline-authority-scored None
replay-heading 1.0
replay-suffix (0.0, 0.0)
replay-mcp-calls 1
saved lookup-complete [('specdex-A', 16, 20), ('specdex-B', 20, 20), ('B1', 19, 20)]
```

`baseline-authority 0` is the helper's original unlabelled-input result; the scored result is now correctly unmeasured (`None`). Saved dev gates: Stage A `proxy_passed=False`, Stage B `computable=False` (no dev paraphrases), authority `proxy_passed=True` with both baselines explicitly unmeasured. This is not an independent acceptance verdict.

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests`.

```text
Ran 154 tests in 1.582s

OK
```

## New defects introduced by the fixes

Each case ran on a private `/tmp` fixture. Introduction is inferred from the fix logic and original audit; no historical checkout was rerun.

**N1 — live requirements disappear from coverage after mixed-history labelling.** In the mini-project PRD, use this complete content:

```markdown
# PRD

### FR-1: Live requirement

Must work.

#### Retired

Old suggestion.
```

Append to its overlay:

```toml
[[historical]]
artifact="prd"
section="Retired"
```

Output: `mixed-coverage defined partly historical []` for resolve status, definition temporal label and `coverage(..., 'tickets', ['FR'])['rows']`. Expected: FR-1 remains in the population, with missing coverage. New `extract.py:254` labelling meets the old exact-`current` filter in `skills/specdex/scripts/specdexlib/coverage.py:47`. Select population by effective current definition, rather than whole-span purity.

**N2 — existing retired positional children become out-of-bounds and get returns no text.** Mini-project PRD: `## Retired`, `### FR-99: Old`, `**Consequences (testable):**`, one top-level `- Old rule.`, then `## Current` and `See FR-99.1.`; retain the fixture's FR positional rule and add the same historical overlay rule. Output:

```text
retired-child out-of-bounds 1 ['historical']
retired-child-get ([], ['FR-99.1 does not exist: FR-99 has 1 positional item(s); positional convention stated in prd §0; showing the parent'])
```

The child exists in `Resolution.historical`. `skills/specdex/scripts/specdexlib/queries.py:246` applies bounds before historical status; :296 then selects an empty current parent. Check history first and support historical retrieval.

**N3 — new covers edges point at the wrong TOML line.** In the preview fixture's initiative `tickets.toml`, move epic 1's unchanged `covers = ["FR-1", "FR-2", "FR-3"]` immediately after `[[epic]]`, before `id = 1`. Valid TOML, unchanged chain. Output: `covers-before-id [('ticket 1', 1, '[[epic]]')]`; expected line 2, the covers field. `skills/specdex/scripts/specdexlib/tickets.py:231` only starts looking after `id`. Parse block boundaries/field locations independently of ordering.

**N4 — unique source-scoped coverage is rejected as globally ambiguous.** Add two explicitly current files `_bmad-output/specs/spec-alpha/SPEC.md` and `spec-beta/SPEC.md`, each containing `- **CAP-1** — Local rule.`. Add `_bmad-output/initiative-demo/initiative-demo.md` with a References line `- spec — _bmad-output/specs/spec-alpha/SPEC.md`, and its `tickets.toml`:

```toml
[[epic]]
id=1
slug="epic-demo"
title="Demo"
covers=["CAP-1"]
```

Output: `unique-source-scoped-chain [('1', 'CAP-1', 'ambiguous-source', 'CAP-1')]`. Expected: resolved within the uniquely referenced alpha spec; beta is a legitimate separate CAP namespace. New `skills/specdex/scripts/specdexlib/tickets.py:200` discards the source context and calls global resolve. Carry the scoped definition identity through chain resolution.
