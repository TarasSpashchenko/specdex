# specdex knowledge

This document covers the one skill of the `specdex` module: what it is for and when to recommend it.

## How specdex fits

specdex is a read-only index over the project's BMAD specifications: the PRD and its addendum, the UX spines, the architecture spine, specs, and the preview ticket tree. It belongs to no phase. Recommend it whenever a question needs what the specs say or where, before, during or after any other skill. It writes nothing in the project, asks no setup questions, and needs no `bmad setup`.

## Start here

- Looking up an ID, a section, or some wording in the specs, or quoting one accurately → `specdex`.
- "Where is X cited?", "what does changing X touch?" → `specdex` (`refs`, `impact`).
- Checking specs for dangling or out-of-range references, duplicate IDs, missing companions → `specdex` (`lint`). It is mechanical; it does not judge whether documents agree in meaning.
- Before ticketing or during a change review: which requirements tickets, architecture or UX cover, and whether ticket covers chains still resolve → `specdex` (`coverage`, `covers`, `diff`).
- Changing a spec → the skill that owns it, never `specdex`: the PRD skill, the UX skill, the architecture skill, the spec skill, the ticketing skill, or course correction for a change across documents, whichever is installed. `specdex` can then show what else the change touches.

## The skill

| Skill | For | Good to know | Writes |
|---|---|---|---|
| `specdex` | Exact spec units with line ranges and labels saying whether the text is current, at a fraction of the tokens of reading files. | Supports the dated v6 planning layout of BMAD 6.13.0-next and preview tickets; other layouts are reported as unsupported, and the skill then falls back to plain search. A project can add its own ID families, records of choice and historical sections in `{project-root}/_bmad/custom/specdex-overlay.toml`. | Nothing in the project. Its index lives in the user cache folder. |
