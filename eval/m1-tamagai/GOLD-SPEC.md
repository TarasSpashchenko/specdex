# M1 gold set: labelling contract

This file tells a labeller (a person or an agent) how to write retrieval tasks and their gold answers for the M1 evaluation of a search-and-maintenance tool for BMAD specifications. The tool itself is **not** involved in labelling: never run it, never read its source, and never look at another labeller's files. Use only `rg`/`grep`, `sed -n`, `nl -ba`, `wc`, `python3`, and reading the files.

## Corpus

- **Root (frozen, read-only):** `/home/taras_spashchenko/TS/ts/specdex/eval/corpora/tamagai-2026-10-04/` — a frozen copy of the Tamagai project (an Android virtual pet for children, specified with BMAD). Every path in a task is relative to this root. Every line number is 1-based and refers to this frozen copy. Never edit the corpus.
- **Specs of record (the 9 record files):**

  | Short name | Path |
  |---|---|
  | PRD | `_bmad-output/planning-artifacts/prds/prd-tamagai-2026-09-29/prd.md` |
  | PRD addendum | `_bmad-output/planning-artifacts/prds/prd-tamagai-2026-09-29/addendum.md` |
  | DESIGN | `_bmad-output/planning-artifacts/ux-designs/ux-tamagai-2026-09-30/DESIGN.md` |
  | EXPERIENCE | `_bmad-output/planning-artifacts/ux-designs/ux-tamagai-2026-09-30/EXPERIENCE.md` |
  | SPINE | `_bmad-output/planning-artifacts/architecture/architecture-tamagai-2026-10-03/ARCHITECTURE-SPINE.md` |
  | OVERVIEW | `_bmad-output/planning-artifacts/architecture/architecture-tamagai-2026-10-03/ARCHITECTURE-OVERVIEW.md` |
  | CHANGE-REQUESTS | `_bmad-output/planning-artifacts/architecture/architecture-tamagai-2026-10-03/CHANGE-REQUESTS.md` |
  | brief | `_bmad-output/planning-artifacts/briefs/brief-tamagai-2026-09-29/brief.md` |
  | brief addendum | `_bmad-output/planning-artifacts/briefs/brief-tamagai-2026-09-29/addendum.md` |

- **Authority:** the brief and its addendum are superseded by the PRD where they differ, except economics, where brief addendum §1.2 stays the authority (PRD §0).
- **Historical text inside record files** (true as a record of the past, not current requirements): PRD addendum §1.9, §6 and Appendix A; EXPERIENCE "PRD change requests" and "Architecture change requests"; the request texts in CHANGE-REQUESTS.md (each row's Decision column is current); the PRD §9 and EXPERIENCE "Retired claims" lists.
- **Everything else is supporting material:** discussion outcomes, research reports and spike results are current rationale; reviews, reconcile reports, extracts, digests, prompts, boards, fix and remediation plans, `.diff` files, `.working/` and `.memlog.md` files are the working trail (often stale). A current requirement is never answered from the trail.
- **ID conventions:** FR-n and NFR-n are PRD `####` headings. FR-n.k / NFR-n.k are positional (PRD §0, last bullet of "How to read it"): in an FR, k counts only the top-level bullets under **Consequences (testable)**; in an NFR, k counts its top-level bullets. UJ-n are PRD §2.3 list leads (elaborated as EXPERIENCE Key Flows `###` headings). CR, SM/SM-C, OQ, CQ are PRD §7, §13, §15, §15.1 rows or list items. AD-n are SPINE `###` headings; A-n are rows of the SPINE Open Questions table. ACR-x and UX-x are CHANGE-REQUESTS table rows. Design tokens are the YAML frontmatter keys of DESIGN.md (e.g. `colors.sleep-dim`). Ranges such as `FR-9–FR-11` or `ACR-A…ACR-Y` cite every member.

## Task schema

Write a JSON array; each task is an object:

```json
{
  "id": "S01",
  "split": "dev",
  "category": "section",
  "prompt": "The request exactly as a developer or agent would phrase it.",
  "answer": "A concise expected answer (1–4 sentences), stating qualifiers such as conditions or provisional status.",
  "evidence": [
    {"path": "_bmad-output/.../prd.md", "start": 394, "end": 415, "why": "FR-7 defining section"}
  ],
  "citations": null,
  "forbidden": [
    {"path": "...", "start": 10, "end": 12, "why": "stale draft-1 ID map; must not be presented as current"}
  ],
  "not_found": false,
  "notes": "How you derived the label; anything a reviewer should double-check."
}
```

- **evidence** — the minimal complete units a correct answer rests on, all required. A unit is one of: a whole heading section (from its heading line through the line before the next heading of the same or higher level; for an FR, the `####` line through the line before the next `####`/`###`/`##`), one table row (a single line; the table's header is implied), one list item (its lead line through its last nested continuation line), or one YAML key line. Give exact `start`/`end` lines, checked with `nl -ba FILE | sed -n 'a,bp'`. Prefer the smallest unit that fully answers: a row over its whole table, an FR section over its feature group. Use 1–4 evidence units; list several only when the answer genuinely needs all of them.
- **citations** — only for exhaustive citation tasks, otherwise `null`. An object `{"scope": "...", "target": "...", "lines": [{"path": "...", "line": 123}, ...]}` listing **every** line in the stated scope that cites the target, including lines where the target hides inside a range (`FR-3–FR-9` cites FR-7) and lines inside the target's own defining unit only if the scope says so. State the scope precisely (for example "the 9 record files, excluding the target's own definition line"). Count each line once.
- **forbidden** — spans that look like answers but must not be presented as current: historical sections, the trail, superseded brief text, a different ID that shares words. Use `[]` when there is no trap.
- **not_found** — `true` when the correct answer is that the requested thing does not exist or is invalid (for example a positional citation past the end of its list). Then `evidence` holds the units that prove the absence (for example the FR section showing only 2 bullets), and `answer` says it does not exist.
- **notes** — your derivation, briefly.

## Categories

| Category | What it tests | Shape |
|---|---|---|
| `section` | Read the right complete section or table row: by ID, by heading, or by topic named with the spec's own words | "Show me FR-69 with its table" · "What does EXPERIENCE say about the resting ears for heat?" |
| `exact` | Exact definitions: an ID, a positional FR-n.k, a glossary term (PRD §3), a design token | "Define Day" · "What is FR-21.4?" · "Value of the sleep-dim token" |
| `citation` | Exhaustive citations or bindings: every place that cites an ID (including inside ranges), every AD whose Binds covers an FR, every row of a table matching a condition | "Every current citation of AD-12 in the record files" |
| `history` | Provisionality, history and negative traps: conditional or counsel-gated status, superseded or retired text, a stale trail statement versus the current spec, an absent requirement | "Is the portrait-only rule for phones current?" · "Which requirement covers push notifications to the child?" (absent → not_found) |
| `paraphrase` | Discovery in different words: the prompt deliberately avoids the distinctive words of the target text (synonyms, a user's everyday wording), yet one or a few record units answer it | "What happens if a kid says something scary?" → helpline screen units |

Rules for every task:
- The prompt must be answerable from the corpus, and phrased like a real request during spec work (what is X, show me Y, where is Z cited, is W still current).
- Prefer record files as evidence. Supporting material may be evidence only when the task explicitly asks about rationale or history.
- No two tasks may share the same target unit and question.
- Mix the documents: PRD, addendum, EXPERIENCE, DESIGN, SPINE, OVERVIEW and CHANGE-REQUESTS should all appear across a split.
- Verify every line number twice before writing it. A wrong line number makes the task useless.

Write the array with `python3 -c 'import json; json.load(open(PATH))'` passing before you finish.
