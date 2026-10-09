---
type: epic
title: "Readers build their reading list"
parent: initiative-shelf-v1
covers: [FR-1, FR-2, FR-3]
assignee: ""
status: in-progress
risk: medium
---

# Readers build their reading list

## Description

A reader adds books by ISBN, marks them read, and rates the ones they have read; every refusal says why.

## Outcome

Readers can keep their whole list in Shelf; the PRD's retention signal is the measure.

## Requirements

- E1 (FR-1): A reader adds a book by ISBN and sees its title and author. (PRD, 4.1)
- E2 (FR-1): An ISBN the catalogue does not know is refused, with the reason shown. (PRD, 4.1)
- E3 (FR-2): A reader marks a book read; the date it was marked is kept. (PRD, 4.1)
- E4 (FR-3): A reader rates a read book from 1 to 5 stars. (PRD, 4.1)

## Done when

1. A reader adds a book by ISBN on the deployed app and sees its title and author.
2. An unknown ISBN is refused with the reason, and the list is unchanged.
3. A book marked read keeps its date and accepts a rating; an unread book offers none.

## Boundaries

The reading-list UI and the book store. Not CSV (epic-csv-transfer).

## References

- parent — _bmad-output/initiative-shelf-v1/initiative-shelf-v1.md
- prd — _bmad-output/planning-artifacts/prds/prd-shelf-2026-09-15/prd.md, section 4.1 Reading list

## Notes

- Decision: the reading history (E5) moves to a later initiative (user's decision, 2026-09-28).
- Decision: tracer bullet is entry 1; entries 2 and 3 follow it (2026-09-26).
