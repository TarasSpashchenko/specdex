---
name: specdex
description: 'Looks up, cites and checks the project''s BMAD specs read-only: PRD and addendum, UX DESIGN.md and EXPERIENCE.md, architecture spine, specs, tickets. Use when an answer depends on what the specs say or where: an ID such as FR-12 or AD-3, "prd §4.2", wording, every citation of an ID, what a change touches, dangling references, ticket coverage; use it before grep. Not for editing specs: bmad-prd, bmad-ux, bmad-architecture, bmad-spec and bmad-ticket do that.'
---
# specdex

specdex returns the exact spec unit an answer needs, with its `path:start-end` range and labels saying whether the text is current, for a fraction of the tokens of reading files. Cite what it says; say plainly when it cannot answer.

## Run

```bash
uv run {skill-root}/scripts/specdex.py [--json] <command> ...
```

Run it inside the project (the folder holding `_bmad/`) or pass `--project DIR`. `--help` lists every option. It picks its BMAD profile from the project's layout (v7 initiative folders or v6 dated folders); under v7 the specs of record are the active initiative's.

| The question has | Run |
|---|---|
| An ID: FR-12, AD-3, UJ-2, a glossary term, a design token | `resolve FR-12` for where it is defined; `get FR-12` for its text |
| A heading, `doc §n`, `path:line`, `path:a-b` or `path#Heading` | `get "prd §4.2"` |
| Wording or a paraphrase | `search <words>`, then `get` the top hit (`--expand 1` inlines it) |
| Every place citing X | `refs FR-12` (`--children` adds FR-12.k; `--kind binds` narrows) |
| A document's shape | `outline [file] --level 2` |
| A change to review | `diff <old-rev>`, then `impact <ID or path:a-b>`, then `lint` |
| Tickets | `covers`; `coverage --by tickets\|architecture\|ux [--only gaps]` |
| Whether the index can be trusted here | `status` |

One unit answers what it says, not what other units add: when other rules may constrain the concept (ownership, a limit, an exception), also `search` its key term and name the units you checked. Keep the default `--scope record` unless the question is why or when something was decided.

## Read the result

Each hit starts `path:start-end [labels] — heading path`. Quote only `record` text without `historical` as a current requirement, and cite it as `path:start-end` with its labels. A `resolve` status other than `defined` (`ambiguous`, `out-of-bounds`, `not defined`, `historical only`) is the answer: report it and never pick a candidate. An empty answer is `none in a fully indexed scope` (a real negative) or `unknown (...)` (not one). `lint` is mechanical, and its last lines say what it did not check. Labels, statuses and flags in full: `references/reading-results.md`.

## When it fails

Exit 1 means findings, not failure. Exit 2 (usage or unknown reference) and exit 3 (configuration or source error) print one line on stderr: report it. Say that specdex could not answer and use `rg -n` over the output folder with bounded reads when it exits 3; when `status` shows `unsupported-layout`, `ambiguous-current`, `no-active-initiative` or no `record` files; when an empty answer is `unknown (...)`; or when `search` misses a paraphrase after one retry.

specdex only reads; its index lives in the user cache. Spec edits belong to `bmad-prd`, `bmad-ux`, `bmad-architecture`, `bmad-spec`, `bmad-ticket` or `bmad-correct-course`; afterwards `impact` and `lint` show what else needs attention. Project settings (ID families, records, historical sections) go in `_bmad/custom/specdex.toml` through `bmad-customize`; the keys are in this skill's `customize.toml`.
