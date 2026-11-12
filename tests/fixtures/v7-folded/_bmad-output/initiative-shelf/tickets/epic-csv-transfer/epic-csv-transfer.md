---
type: epic
title: "Readers move their list in and out as CSV"
parent: initiative-shelf
covers: [FR-4, FR-5]
assignee: ""
risk: medium
---

# Readers move their list in and out as CSV

## Description

A reader takes the whole list out as CSV and brings it back in, and a list that makes the round trip is unchanged.

## Outcome

Readers trust Shelf with their list because they can always take it with them; no reader-reported data loss is the signal.

## Requirements

- FR-4: A reader exports the whole list as CSV, one row per book. (PRD, 4.2)
- FR-5: A reader imports a CSV in the export's format; rows that do not parse are listed and nothing is half-imported. (PRD, 4.2)
- R1 (CAP-1): — Write one row per book with ISBN, title, author, read date and rating.

## Done when

1. An exported list opens in the three most used spreadsheet apps without an import prompt.
2. Exporting a list and importing it into an empty account gives the same list.
3. A file with one bad row imports nothing and names the row.

## Boundaries

CSV export and import of the reading list. Not the book record itself (epic-reading-list).

## References

- parent — _bmad-output/initiative-shelf/initiative-shelf.md
- prd — _bmad-output/initiative-shelf/prd-shelf/prd-shelf.md, section 4.2 CSV transfer

## Notes

- Waits on epic-reading-list because: export and import write the book record it defines.
