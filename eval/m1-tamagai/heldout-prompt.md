# Held-out labelling for the specdex M1 evaluation

You are CODEX, the independent labeller agreed in the Codex–Claude discussions on BMAD spec search (round 1 outcome §4, round 2 outcome §6). Claude is building a read-only search-and-maintenance tool for BMAD specifications and is drafting the 32 development tasks. You write and label the **16 held-out tasks**, before anyone has seen any ranking. Claude will not read your file until the final evaluation, and nobody tunes the tool on it, so your independence is what makes the held-out score meaningful.

## Do this

1. Read `/home/taras_spashchenko/TS/ts/specdex/eval/m1-tamagai/GOLD-SPEC.md` completely. It is the labelling contract: corpus root, the 9 record files, authority and history rules, the task schema, the evidence-unit rules and the five categories.
2. Explore the frozen corpus at `/home/taras_spashchenko/TS/ts/specdex/eval/corpora/tamagai-2026-10-04/` with `rg`, `sed -n`, `nl -ba` and `python3`. Read enough of the record files to choose good tasks.
3. Write exactly 16 tasks, ids `H01`…`H16`, all with `"split": "heldout"`:
   - **8 `paraphrase`** tasks (H01–H08). Phrase each prompt the way a developer, tester or parent-facing designer would ask it in everyday words, deliberately avoiding the distinctive words and IDs of the target text (use synonyms; do not quote headings). Each must still have 1–3 record-file evidence units that clearly answer it. Spread them over at least five different record files. These are the hardest and most important tasks: they decide whether the tool needs semantic search.
   - **2 `section`** (H09–H10), **2 `exact`** (H11–H12), **2 `citation`** (H13–H14) and **2 `history`** (H15–H16), following GOLD-SPEC's category table. At least one `history` task must contain a trap (`forbidden` non-empty) or be `not_found`. Citation tasks must give the complete `citations.lines` list for a precisely stated scope.
4. Avoid these development-set topics (Claude's starter queries), so the two splits stay disjoint: FR-68–FR-75 and their matrices; FR-7 versus FR-7.3; FR-73.6; citations of AD-12; FR-69's beyond-default row; AD-5's schedule and fallback; resting ears for offline versus heat; the glossary term "Day"; the `sleep-dim` token; FR-7's bindings inside ranges; microphone ownership per process versus per visit; authority after Arwen was declined; retired portrait/tablet wording; pending deletion credentials when offline.
5. Verify every line number twice (`nl -ba FILE | sed -n 'a,bp'`). For citation lists, generate candidates with a script that also expands ranges, then check each line by eye.
6. Save the array to `/home/taras_spashchenko/TS/ts/specdex/eval/m1-tamagai/gold/heldout.json` and validate it with `python3 -c 'import json; d=json.load(open("/home/taras_spashchenko/TS/ts/specdex/eval/m1-tamagai/gold/heldout.json")); assert len(d)==16'`.

## Boundaries

- Write only that one file (scratch files under `/tmp` are fine). Never edit the corpus.
- Do not open anything under `/home/taras_spashchenko/TS/ts/specdex/skills/`, `/home/taras_spashchenko/TS/ts/specdex/tests/`, any other file in `eval/m1-tamagai/gold/`, or `eval/m1-tamagai/results/`; do not run any `specdex` command.
- No network access is needed.

Finish with a one-paragraph summary: the 16 ids with category and target file, and anything you were unsure about.
