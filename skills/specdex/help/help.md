# specdex knowledge

This document covers the one skill of the `specdex` module: what it is for and when to recommend it.

## How specdex fits

specdex is a read-only index over the project's BMAD specifications: the PRD and its addendum, the UX spines, the architecture spine, specs, and the ticket tree. It belongs to no phase. Recommend it whenever a question needs what the specs say or where, before, during or after any other skill. It never writes in the project and asks no setup questions.

## Start here

- Looking up an ID, a section, or some wording in the specs, or quoting one accurately → `specdex`.
- "Where is X cited?", "what does changing X touch?" → `specdex` (`refs`, `impact`).
- Checking specs for dangling or out-of-range references, duplicate IDs, missing companions → `specdex` (`lint`). It is mechanical; it does not judge whether documents agree in meaning.
- Before ticketing or during a change review: which requirements tickets, architecture or UX cover, and whether ticket covers chains still resolve → `specdex` (`coverage`, `covers`, `diff`).
- Changing a spec → the skill that owns it, never `specdex`: `bmad-prd`, `bmad-ux`, `bmad-architecture`, `bmad-spec`, `bmad-ticket`, or `bmad-correct-course` for a change across documents. `specdex` then shows what else the change touches.
- Teaching specdex a project convention (an extra ID family, which documents are the record, sections that are history) → `bmad-customize`, writing `_bmad/custom/specdex.toml`.

## The skill

| Skill | For | Good to know | Writes |
|---|---|---|---|
| `specdex` | Exact spec units with line ranges and labels saying whether the text is current, at a fraction of the tokens of reading files. | Reads BMAD's v7 initiative layout, where the active initiative's documents are the record, and the earlier dated v6 layout; it picks the profile from the project. On a layout it cannot read it says so, and the agent falls back to plain search. | Nothing in the project. Its index lives in the user cache folder. |
