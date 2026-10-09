---
name: specdex
description: Read-only lookup, citation, impact and consistency checks for this project's BMAD specifications (PRD and addendum, UX DESIGN.md and EXPERIENCE.md, architecture spine, specs, preview tickets). Use when an answer depends on what the specs say or where - an ID such as FR-12, NFR-3, UJ-2, AD-7 or CQ-4, a section such as "prd §4.2", wording to locate, every place that cites an ID, what a change touches, dangling or out-of-range references, or which requirements tickets, architecture or UX cover - and use it before grep or reading whole spec files. It never edits specs.
---

# specdex

## Overview

This skill returns the exact spec unit an answer needs, with its `path:start-end` range and labels that say whether the text is current. It costs a fraction of the tokens of reading files and keeps trail or historical text from being quoted as a current requirement. Act as a careful spec librarian: cite what the record says, and say plainly when the index cannot answer.

## On Activation

```text
python3 {skill-root}/scripts/specdex.py [--json] [--project DIR] <command> ...
```

`{skill-root}` is the folder holding this file. It needs Python 3.11+ and nothing else; if `python3` is older, use `uv run {skill-root}/scripts/specdex.py`. Run it from inside the project (it walks up to the BMAD project root, failing that the git root) or pass `--project`. Global options go before the command. The project overlay `{project-root}/_bmad/custom/specdex-overlay.toml` is picked up when present. The first call builds the index in a second or two; every later call re-hashes the files and reindexes only what changed, so an answer reflects the files as they were at that call.

## Pick the command

| The question has | Run |
|---|---|
| An ID: FR-12, AD-3, UJ-2, a glossary term, a design token | `resolve FR-12` for where it is defined, its positional items and its elaborations; `get FR-12` for the text |
| A heading, `doc §n`, `path:line`, `path:a-b` or `path#Heading` | `get "prd §4.2"` |
| Wording or a paraphrase | `search <words>`, then `get` the top hit's reference (`--expand 1` inlines it) |
| "All" or "every" place citing X | `refs FR-12`: includes lines inside ranges such as FR-9–FR-12; `--children` adds FR-12.k, `--kind binds` narrows |
| The shape of a document | `outline [file] --level 2` |
| A change to review | `diff <old-rev> [<new-rev>]` (default new: the worktree; flags shifted FR-n.k lists and added IDs already in the file's history), then `impact <ID or path:a-b>`, then `lint` |
| Tickets | `covers` checks every ticket's covers chain; `coverage --by tickets\|architecture\|ux [--only gaps]` |
| Whether specdex can be trusted here | `status` |

One unit answers what it says, not what other units add. When the question is about a concept other rules may also constrain (who owns something, a limit, an exception, whether something exists at all), also `search` the concept's key term before answering, and say which units you checked.

`get` takes several references in one call; `--budget N` gives each reference about N tokens (estimated as characters/4) and never cuts a single unit. Paths are project-relative; cite them exactly as printed. `get`, `outline` and `impact` also accept any unique path suffix; `refs` takes an ID.

`--scope` chooses which files count: `record` (default) is the specs of record; `current` adds rationale and tickets; `rationale`, `trail`, `memlog` and `all` reach the history. Stay on the default unless the question is about why or when something was decided.

## Read the output

Each hit starts `path:start-end [labels] — heading path`. Labels read `[role; temporal; decision: ...; flags; authority]`, with the parts that apply:

- **role**: `record` is the current spec of record, the only text that states current requirements. `ambiguous` is one of several candidate documents of one type with no overlay choice between them. `rationale` explains current decisions but requires nothing. `ticket`, `noncurrent` (an older document of a type that was not selected), `trail` (reviews, drafts, discussions), `memlog` and `unverified` (no rule matched) are not current requirements.
- **historical**: text kept as history inside a record, such as declined proposals, retired claims, or change requests as raised. It is true about the past, not about now.
- **decision: X**: on a change-request row, the decision taken. The decision is current; the request text is not.
- **flags** such as `assumption`, `note-for-pm`, `non-goal`, `conditional`: the unit is provisional or deliberately out of scope; say so when citing it.
- **superseded by prd [except ...]**: the PRD wins over this file, except in the named sections, which show `authoritative exception (...)`.

Quote only `record` text without `historical` as a current requirement, and cite it as `path:start-end` with its labels.

Statuses in `resolve`, `refs`, `impact` and `lint`:

- `defined`: exactly one definition.
- `ambiguous`: several definitions or candidate documents. Do not pick one; report them. When the definitions sit in different document scopes (AD in two spines, CAP in two specs), the citing document decides; otherwise suggest choosing the record in the overlay's `[current] records`.
- `out-of-bounds`: a positional ID past the end of its list (FR-12.9 when FR-12 has 5 items); the note gives the count.
- `not defined` or `unresolved`: a dangling reference.
- `historical only` (in `resolve`; `historical` in `refs` and `lint`): the ID is defined only in history, such as a retired or declined section. A current line citing it is a finding.
- `elaborated only`: elaborated somewhere but not defined in its owner document.
- `textual`: a phrase such as "all MVP FRs" may bind the ID; read the line to decide.

An empty answer says `none in a fully indexed scope`, which is a real negative, or `unknown (...)`, which is not: part of the scope could not be indexed. Every output ends with `generation <hash>`, the verified index state the answer came from.

`lint` is mechanical: duplicates, dangling or out-of-range references, unknown tokens, missing companions, replica drift, and BMAD's own spine validator. A validator that could not run (missing, changed since the profile was built, failed, or a revision snapshot) appears as a `validator-not-run` or `validator-failed` finding, never as silence. Its last lines say what it did not check: a clean lint does not mean the specs agree, and contradictions in meaning still need reading.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | Findings: `resolve` not `defined`, `lint` high severity, `coverage` gaps, `covers` problems |
| 2 | Usage error, unknown reference or scope, or the files kept changing during the call |
| 3 | Configuration or source error: unreadable profile or overlay, unreadable git revision |

## When to fall back

Say that specdex could not answer and use `rg -n` over the output folder (usually `_bmad-output/`) plus bounded reads of the matching section when:

- it exits 3;
- `status` shows `diagnostic unsupported-layout` (sharded v6 `index.md`, initiative-v7 folders) or `ambiguous-current`;
- `status` shows no `record` files: specdex found no specs where the profile looks, so its negatives mean nothing;
- an empty answer is `unknown (...)`;
- `search` misses a paraphrase after one retry with other words.

`status` showing `profile ... (unverified)` means the installed BMAD differs from the version the profile was built for; results still come, but check surprising ones by reading.

## Read-only

specdex never writes inside the project and refuses an index location inside it. The one program it runs, BMAD's own `lint_spine.py` validator, which only reads, runs only when it is byte-identical to the version the profile was built against. The index lives in the user cache, `$XDG_CACHE_HOME/specdex/` (default `$HOME/.cache/specdex/`), or at `--db`. It reports evidence; changing a spec is the owning BMAD skill's job: `bmad-prd` for the PRD and addendum, `bmad-ux` for DESIGN.md and EXPERIENCE.md, `bmad-architecture` for the spine, `bmad-spec` for specs, `bmad-preview-ticketing` for tickets, `bmad-correct-course` for a change across documents. After such an edit, `impact` and `lint` show what else needs attention. The overlay is the project's configuration; edit it only when the user asks.
