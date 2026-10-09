# specdex

specdex is a read-only search and maintenance engine for BMAD specifications: PRD and addendum, UX `DESIGN.md`/`EXPERIENCE.md`, the architecture spine, specs, and preview tickets. It indexes them by ID, section and wording, and returns exact units with `path:start-end` ranges and labels that say whether the text is current, historical or trail. Agents use it through the `specdex` skill instead of grepping and reading whole files.

It ships as a one-skill BMAD module (`skills/specdex/`): `SKILL.md` (agent routing guide), `bmod.toml` (module record and skill in one file), `help/help.md` (what the `bmad` help skill routes from), `profiles/`, and a standard-library Python CLI in `scripts/`.

## Requirements

Python 3.11+ (standard library only), git for `diff` and `--rev`, Node.js for `npx skills`. Supported layout: BMAD 6.13.0-next dated planning folders plus the preview ticket tree.

## Install (per project)

From the project root:

```sh
npx skills add ~/TS/ts/specdex --skill specdex -a claude-code -y    # from a local checkout
npx skills add <owner>/specdex --skill specdex -a claude-code -y    # once the repo is published
```

`-a claude-code` copies the skill to `.claude/skills/specdex/`. Adding an agent that uses the shared folder (for example `-a claude-code -a codex`) puts it in `.agents/skills/specdex/` with a `.claude/skills/specdex` symlink, the layout BMAD itself uses. Omit `-a` to choose agents interactively.

In a BMAD project, `bmad status` lists the `specdex` module and `bmad` help can recommend the skill. Run `bmad setup` once so status reports it current (setup only creates an empty `_bmad/specdex/scripts/`); specdex asks no setup questions.

## First run

```sh
python3 .claude/skills/specdex/scripts/specdex.py status
python3 .claude/skills/specdex/scripts/specdex.py resolve FR-1
```

`status` shows the profile (`verified` when the installed BMAD files match the ones it was built from), the overlay, the files by role, and diagnostics such as `ambiguous-current` or `unsupported-layout`. The first call builds the index in a second or two; later calls verify it against the files and reindex only what changed.

## Overlay

Without an overlay, the profile's defaults apply: one document of a type is the record; several (say, two dated PRD folders) are `ambiguous` until you choose. Project conventions go in `_bmad/custom/specdex-overlay.toml` (or `--overlay FILE`):

```toml
[overlay]
project = "myproject"
profile = "bmad-6.13.0-next"

[current]          # the specs of record when several candidates exist
records = ["_bmad-output/planning-artifacts/prds/prd-myproject-2026-09-29/prd.md"]

[[family]]         # an ID family the project adds
name = "NFR"
pattern = 'NFR-(?P<key>\d+)'
key = "int"
owner = ["prd"]

[[historical]]     # text inside a record that is history, not current
artifact = "prd-addendum"
section = "1.9 Declined proposals"
```

Other tables: `[[define]]` (where a family is defined), `[[positional]]` (FR-n.k list items), `[[elaborate]]`, `[[superseded]]`, `[[role]]` (rationale vs trail for supporting files), `[[marker]]`, `[doc_aliases]`, `[coverage]`. A complete real overlay: `eval/m1-tamagai/overlay.toml`.

## Commands

Global options come before the command: `--project DIR --overlay FILE --profile FILE --rev REV --db FILE --json`.

| Command | Does |
|---|---|
| `status` | Index generation, profile binding, roles, diagnostics |
| `outline [file] [--level N]` | Heading tree with line ranges |
| `resolve ID [--text]` | Where an ID, glossary term or token is defined and elaborated |
| `get REF... [--budget N]` | Whole units by ID, `doc §n`, `path:line`, `path:a-b` or `path#heading` |
| `refs ID [--scope S] [--children] [--kind K]` | Every citing line, including inside ranges such as FR-9–FR-12 |
| `search WORDS [--scope S] [-k N] [--expand N]` | Ranked full-text search over sections and table rows |
| `lint [--scope S] [--no-validators]` | Duplicates, dangling or out-of-range references, tokens, companions, replicas, BMAD's spine validator |
| `impact ID\|path:a-b` | What cites, binds, elaborates or covers the target |
| `diff OLD [NEW]` | IDs, positional items and sections changed between revisions (default NEW: the worktree) |
| `covers` / `coverage --by tickets\|architecture\|ux [--only gaps]` | Ticket covers chains; declared coverage of requirements |

Scopes: `record` (default), `current`, `rationale`, `trail`, `memlog`, `all`. Exit codes: 0 ok, 1 findings, 2 usage error or not found, 3 configuration or source error.

## Read-only guarantee

specdex never writes inside the project. The index lives in `$XDG_CACHE_HOME/specdex/` (default `~/.cache/specdex/`), or at `--db`. `--rev` and `diff` read git objects without touching the worktree, and `lint` runs BMAD's own read-only `lint_spine.py` only when its bytes match the profile's recorded hash (otherwise lint reports `validator-not-run`). An index location inside the project is refused. Spec edits belong to the owning BMAD skills (`bmad-prd`, `bmad-ux`, `bmad-architecture`, `bmad-spec`, `bmad-preview-ticketing`, `bmad-correct-course`).

## Limits

- Other layouts (sharded v6 `index.md`, initiative-v7) are reported as `unsupported-layout`, not indexed; the skill then falls back to `rg`.
- Search is lexical (SQLite FTS5); a paraphrase with no shared words can miss.
- `lint` is mechanical: a clean result does not mean the documents agree in meaning.
- Positional IDs (FR-n.k) and project ID families need an overlay.
- `bmod.toml` uses a `file:` update source until the repository has a remote.

## Development

`python3 -m unittest discover -s tests` runs the unit tests (synthetic fixtures under `tests/fixtures/`). `eval/m1-tamagai/` holds the M1 evaluation: `run_eval.py` (retrieval, Layer A), `layer_b.py` (maintenance mutations, identity, freshness, latency) and the gold sets; the frozen corpus itself is not in the repository.
