# Reading specdex results

## Labels

Each hit starts `path:start-end [labels] — heading path`. Labels read `[role; temporal; decision: ...; flags; authority]`, with the parts that apply:

- **role**: `record` is the current spec of record, the only text that states current requirements. Under the v7 layout the records are the active initiative's documents and its parent initiatives', one of each type per initiative or epic (an epic's PRD stands beside its initiative's); a bmad-shard-pro shard is part of its document. A current ticket also defines its own requirement IDs (`R1`). The other roles state no current requirement:
  - `ambiguous`: one of several candidate documents of one type in one place, with no active initiative or records setting to choose between them;
  - `rationale`: explains current decisions but requires nothing (UX router, research, intent);
  - `noncurrent`: a document of a type that was not selected, or another initiative's rationale or tickets (another initiative, a loose or older copy);
  - `ticket`, `trail` (reviews, drafts, discussions, archives), `memlog`;
  - `unverified`: no rule matched.
- **historical**: text kept as history inside a record, such as declined proposals, retired claims, or change requests as raised. It is true about the past, not about now.
- **decision: X**: on a change-request row, the decision taken. The decision is current; the request text is not.
- **flags** such as `assumption`, `note-for-pm`, `non-goal`, `conditional`: the unit is provisional or deliberately out of scope; say so when citing it.
- **superseded by prd [except ...]**: the PRD wins over this file, except in the named sections, which show `authoritative exception (...)`.

## Statuses

Statuses appear in `resolve`, `refs`, `impact` and `lint`:

- `defined`: exactly one definition.
- `ambiguous`: several definitions or candidate documents. Do not pick one; report them.
  - When the definitions sit in different document scopes (AD in two spines, R1 in two tickets), the citing document decides: a story's or spine's R id is its own ticket's, a ticket's `covers` and `(parent R3)` its parent's, and an AD the nearest spine up the tree.
  - Otherwise, suggest setting the active initiative (the `bmad` skill) or the `records` setting.
- `out-of-bounds`: a positional ID past the end of its list (FR-12.9 when FR-12 has 5 items); the note gives the count.
- `not defined` or `unresolved`: a dangling reference.
- `historical only` (in `resolve`; `historical` in `refs` and `lint`): the ID is defined only in history, such as a retired or declined section. A current line citing it is a finding.
- `elaborated only`: elaborated somewhere but not defined in its owner document.
- `textual`: a phrase such as "all MVP FRs" may bind the ID; read the line to decide.

## Empty answers and lint

An empty answer says either:
- `none in a fully indexed scope`, which is a real negative; or
- `unknown (...)`, which is not: part of the scope could not be indexed.

Every output ends with `generation <hash>`, the verified index state the answer came from.

`lint` is mechanical. It checks duplicates, dangling or out-of-range references, unknown tokens, missing companions, replica drift, ticket covers chains that reach no defined ID (`ticket-*`, as `covers` reports them), and BMAD's own spine validator.
- A validator that could not run appears as a `validator-not-run` or `validator-failed` finding, never as silence. Reasons: it is missing, it changed since the profile was built, it failed, or the index is a revision snapshot.
- Its last lines say what it did not check. A clean lint does not mean the specs agree; contradictions in meaning still need reading.

## status

`status` prints:
- the profile and why it was chosen;
- whether the installed BMAD files match it (`verified`), or the profile is `unverified`, in which case check surprising results by reading;
- the record scope;
- the files by role;
- diagnostics.

Diagnostics that mean answers are partial:
- `unsupported-layout`, `ambiguous-current`, `missing-record`, `source-skipped`;
- `no-active-initiative` (v7 with no initiative chosen and no `records` setting).

`unsupported-layout` also marks a sharded document whose section files this profile does not index: a main file linking to files beside it that no rule reads (bmad-shard-pro's shards, which name their main file in `part_of`, are read).

`unknown-setting` names a `[workflow]` key specdex ignores, usually a misplaced one; fix it in `_bmad/custom/specdex.toml`.

`deprecated-overlay` means a legacy `_bmad/custom/specdex-overlay.toml` is still being read. Its tables belong in `_bmad/custom/specdex.toml` under `[workflow]`; the diagnostic spells out the mapping.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | Findings: `resolve` not `defined`, `lint` high severity, `coverage` gaps or no clean count (nothing to count, or a scope not fully indexed), `covers` problems |
| 2 | Usage error, unknown reference or scope, or the files kept changing during the call |
| 3 | Configuration or source error: unreadable profile, settings or config, unreadable git revision |
