# specdex

specdex is a read-only search and maintenance engine for BMAD specifications: PRD and addendum, UX `DESIGN.md`/`EXPERIENCE.md`, the architecture spine, specs, and preview tickets. It indexes them by ID, section and wording, and returns exact units with `path:start-end` ranges and labels that say whether the text is current, historical or trail. Agents use it through the `specdex` skill instead of grepping and reading whole files.

It ships as a one-skill BMAD module (`skills/specdex/`):
- `SKILL.md`: the agent routing guide, with `references/reading-results.md`;
- `bmod.toml`: the module record and the skill in one file;
- `help/help.md`: what the `bmad` help skill routes from;
- `customize.toml`: project settings;
- `assets/profile-*.toml`: one profile per BMAD layout;
- a standard-library Python CLI in `scripts/`, with a shipped smoke test in `scripts/tests/`;
- `evals/triggers.json`: trigger cases for `bmad-eval`.

## Requirements

Python 3.11+ (standard library only), `uv` to run it the way the skill does, git for `diff` and `--rev`, Node.js for `npx skills`.

Supported layouts, chosen automatically per project (`--profile` overrides):

| Profile | Layout | Chosen when |
|---|---|---|
| `bmad-v7` | BMad v7 initiative folders: `{output_folder}/{active_initiative}/<type>-<slug>/<type>-<slug>.md`; the `bmad-agent-po` ticket tree with each container's breakdown in its `tickets/` folder (BMAD-METHOD `a867e160`, 2026-11), or beside its file (the October 2026 layout) | `core.active_initiative` is set or v7 planning documents exist; also the default |
| `bmad-6.13.0-next` | dated v6 planning folders (`planning-artifacts/prds/prd-*/prd.md` …) plus the preview ticket tree | dated v6 planning documents exist and no v7 signal does |

Under v7 the specs of record are the owners inside the active initiative and the parent initiatives that list it (`[[initiative]]` in a parent's `tickets.toml`): one record of each type per container, so an epic's PRD, UX and spine stand beside its initiative's, while two of one type in one folder are `ambiguous`. Other initiatives (their research, UX routers and tickets included), loose documents and archives are not current; backlog tickets are. BMAD-METHOD still reports version `6.13.0-next` for every layout, which is why the layout, not the version, decides.

What the `bmad-v7` profile reads on the current layout:

| Artifact | How |
|---|---|
| Planning documents (`bmad-facilitate`) | Their `template:` frontmatter gives the type: `prd`, `prd-light`, `srs`, `brd`, `agent-spec`, `brief` and `charter` define IDs (FR, UJ, SM, RULE, OQ, BR, SC); the other templates (business case, narrative, pitch …) are rationale. IDs are defined where BMad's `check_ids.py` says they are, with its ranges (`FR-1 to FR-4`) and `withdrawn` marks; documents without `template:` keep the earlier forms. |
| Ticket tree | Requirements lines `R1 (FR-2, FR-5)`, `R1 (prd FR-2)`, `R1 (parent R3)`, `R1 (<section>)`; `sources:` and `companions:` from the project root; folded specs (`R2 (CAP-1)`). A ticket's R ids are definitions; `covers` chains and architecture coverage follow them to the source IDs. |
| Sharded documents (`bmad-shard-pro`) | A shard (`part_of:`) is part of its document; `.source/`, map pages and the identifier lookup are trail. |

## Install (per project)

From the project root:

```sh
npx skills add ~/TS/ts/specdex --skill specdex -a claude-code -y    # from a local checkout
npx skills add <owner>/specdex --skill specdex -a claude-code -y    # once the repo is published
```

`-a claude-code` copies the skill to `.claude/skills/specdex/`. Adding an agent that uses the shared folder (for example `-a claude-code -a codex`) puts it in `.agents/skills/specdex/` with a `.claude/skills/specdex` symlink, the layout BMAD itself uses. Omit `-a` to choose agents interactively.

In a BMAD project, `bmad status` lists the `specdex` module and `bmad` help can recommend the skill. specdex asks no setup questions.

## First run

```sh
uv run .claude/skills/specdex/scripts/specdex.py status
uv run .claude/skills/specdex/scripts/specdex.py resolve FR-1
```

`status` shows:
- the profile and why it was chosen (`verified` when the installed BMAD files match the ones it was built from);
- the record scope;
- the files by role;
- diagnostics such as `no-active-initiative`, `ambiguous-current` or `unsupported-layout`. The first call builds the index in a second or two; later calls verify it against the files and reindex only what changed.

## Settings

Project conventions are BMad customization. The skill's `customize.toml` lists every key under `[workflow]`. A project overrides them in `_bmad/custom/specdex.toml` (team, committed) or `specdex.user.toml` (personal), normally through the `bmad-customize` skill. specdex merges them with BMad's own rules (the same result as BMad's `resolve_customization.py`, which a test checks) but never runs the project's scripts: a read-only tool executes no project code. Arrays of tables carry `id`, so a later layer replaces an item with the same id.

```toml
[workflow]
records = ["{output_folder}/{active_initiative}/prd-myproject/prd-myproject.md"]   # decides the PRD; other types follow the initiative

[[workflow.family]]          # an ID family the project adds; id is the family name
id = "NFR"
pattern = 'NFR-(?P<key>\d+)'
key = "int"
owner = ["prd"]

[[workflow.define]]          # where it is defined
id = "nfr-in-prd"
family = "NFR"
artifact = "prd"
shape = "item-lead"

[[workflow.historical]]      # text inside a record that is history, not current
id = "declined"
artifact = "prd-addendum"
section = "1.9 Declined proposals"

[workflow.coverage]
tickets = ["FR"]
```

`records` decides only the document types it names: a listed file is the record of its type and the other files of that type are noncurrent. Other keys: `positional` (FR-n.k list items), `elaborate`, `superseded`, `role` (rationale or trail for supporting files; a matching rule outranks the profile's rationale and trail defaults, while memlogs and tickets keep theirs, so put specific globs before a catch-all), `replica`, `marker`, `artifact`, and the tables `aliases`, `doc_aliases`, `frontmatter_types`, `tokens`. `coverage` defaults to FR for tickets and architecture and UJ for UX. A key specdex does not read raises `unknown-setting`; a malformed setting exits 3 with one line.

**Legacy overlay.** A `_bmad/custom/specdex-overlay.toml` (or `--overlay FILE`) is still read for this release and combined with the customization. The default-location file raises `deprecated-overlay`. To move it, put each table under `[workflow]` (`[[family]]` becomes `[[workflow.family]]` with `id` set to its `name`), turn `[current] records` into `[workflow] records`, give each array item an `id`, and drop `[overlay]`. A complete real overlay: `eval/m1-tamagai/overlay.toml`.

## Commands

Global options come before the command: `--project DIR --profile FILE --overlay FILE --rev REV --db FILE --json`.

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

specdex never writes inside the project. The index lives in `$XDG_CACHE_HOME/specdex/` (default `~/.cache/specdex/`), or at `--db`. `--rev` and `diff` read git objects without touching the worktree, and `lint` runs BMAD's own read-only `lint_spine.py` only when its bytes match the profile's recorded hash (otherwise lint reports `validator-not-run`). An index location inside the project is refused. Spec edits belong to the owning BMAD skills (`bmad-agent-pm` on `bmad-facilitate`, `bmad-agent-analyst`, `bmad-ux`, `bmad-architecture`, `bmad-agent-po`).

## BMad Toolsmith compliance

The package passes Toolsmith's checks: `validate_manifests.py`, `init_skill.py --check`, `scan_paths.py`, `scan_scripts.py`, and `prepass.py`, with `SKILL.md` under about 900 tokens and a description under 500 characters. Deliberate deviations:

| Rule | specdex | Why |
|---|---|---|
| No paths into other skills | Runs `bmad-architecture/scripts/lint_spine.py` | It is BMAD's own spine check. It runs only when its bytes match the profile's recorded hash, in Python's isolated mode (no module beside it is imported), and it only reads |
| Folders stay flat | `scripts/specdexlib/` package | A 4,000-line engine split by responsibility |
| Prefer a personal prefix | Name `specdex` | Renaming would break installs |
| JSON when a model reads the result | Text by default, `--json` available | Text is what agents read best at this size; JSON is for tools |
| Read config and customization through BMad's resolver scripts | Reads the same files with BMad's merge rules | Running `_bmad/scripts/*.py` would execute project code from a read-only tool and double its latency; a test proves the result equals the resolvers' |
| `update_source = "github:…"` | `file:` | Until the repository is published |
| `init_skill.py --check` expects a prefixed name | Run with `--any-name` | The unprefixed name is kept (see above) |

Deliberate deviations from BMad's own checkers:

| BMad | specdex | Why |
|---|---|---|
| `check_ids.py` defines an ID opening any bold list item | A bold lead reading as a sentence (`**FR-2 is verified by …**`) defines only an ID the file defines nowhere else | Such a line cites the requirement; reading it as a second definition would make the ID ambiguous |
| `check_ids.py` applies to any document it is given | Only to documents `bmad-facilitate` wrote (`template:` frontmatter) and their shards | Earlier PRDs list IDs as `- FR-2 — …` in assumption and question lists, which check_ids reads as definitions |
| `check_ids.py` reads the files it is given in order | Reads the specs of record parents first (a parent initiative's, the active initiative's, then an epic's), a sharded document in its map's order | specdex sees the whole tree at once; this is the order BMad passes a document with its parent's |

## Limits

- Sharded documents other than `bmad-shard-pro`'s (a v6 `index.md`, or a main file linking to section files beside it, which is how the v6→v7 migration leaves them) are reported as `unsupported-layout`, not indexed; empty answers become `unknown` and the skill falls back to `rg`.
- Only the active initiative's tree (with its parent initiatives and the backlog) is checked; a sibling initiative's tickets are another initiative's work. Tracker stores are read only through what is mirrored into the files.
- IDs a sponsor document (business case, narrative) lists are not definitions: those templates are rationale.
- Supporting files the profile does not know (a user's own notes in a run folder) stay `unverified` until a `role` setting classifies them.
- Search is lexical (SQLite FTS5); a paraphrase with no shared words can miss.
- `lint` is mechanical: a clean result does not mean the documents agree in meaning.
- Positional IDs (FR-n.k) and project ID families need project settings.
- `bmod.toml` uses a `file:` update source until the repository has a remote.

## Development

`python3 -m unittest discover -s tests` runs the unit tests; the skill also ships a smoke test (`python3 -m unittest discover -s skills/specdex/scripts/tests`). The synthetic fixtures under `tests/fixtures/` are:
- `mini-project`: dated v6;
- `preview-tickets`: the v6 preview ticket tree;
- `v7-project`: the October 2026 v7 initiative layout, carrying byte-identical copies of BMad's MIT-licensed resolver scripts;
- `v7-current`: the current layout (parent initiative, epic-level documents, `tickets/` folders), carrying byte-identical copies of BMad's `check_ids.py` and `tickets.py`, which `tests/test_conformance.py` compares specdex with; `v7-current-sharded` is its PRD after `bmad-shard-pro`;
- `v7-folded`: `v7-project` after BMad's spec fold (`migrate_v6.py --fold-specs`) and migration-2.

`docs/` holds the milestone plans, reports and worklogs. `eval/m1-tamagai/` holds the M1 evaluation: `run_eval.py` (retrieval, Layer A), `layer_b.py` (maintenance mutations, identity, freshness, latency) and the gold sets; the frozen corpus itself is not in the repository.
