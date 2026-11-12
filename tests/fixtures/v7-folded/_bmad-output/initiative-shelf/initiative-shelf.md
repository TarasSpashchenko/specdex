---
type: initiative
title: "Readers keep one reading list they trust"
parent: none
assignee: ""
status: in-progress
risk: medium
sources: [prd-shelf/prd-shelf.md]
---

# Readers keep one reading list they trust

## Description

A reader builds a reading list by ISBN, records what they have read and how they rated it, and moves the list in and out as CSV. The PRD owns the capabilities and non-goals; this initiative delivers Shelf v1.

## Outcome

Readers who add five books come back to mark one read within a month; the PRD's retention signal is the measure.

## Requirements

- R1 (CAP-1): — Import a CSV in the export's format. Success: the list equals the exported one.
- R2 (CAP-2): — List rows that do not parse. Success: nothing is half-imported.

## Done when

1. FR-1 to FR-5 are live for every reader, not behind a flag.
2. A list exported and imported into an empty account is the same list.
3. No reader-reported data loss in the first month.

## Boundaries

The Shelf web app and its book store. Not the catalogue provider beyond the ISBN lookup, not sharing. Tracer path: one book added by ISBN, marked read, exported and imported.

- Touch point: catalogue provider — ISBN lookup, configuration only; owner: epic-reading-list

## References

- prd — _bmad-output/initiative-shelf/prd-shelf/prd-shelf.md, section 4 Features

## Notes

- Parked: FR-6 (public reading lists) is on no epic; deferred to v2, user's call 2026-09-20.
