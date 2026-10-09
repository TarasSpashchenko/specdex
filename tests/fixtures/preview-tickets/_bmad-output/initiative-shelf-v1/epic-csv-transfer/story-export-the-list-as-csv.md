---
id: 1
type: story
title: "Export the list as CSV"
parent: epic-csv-transfer
covers: [FR-4, FR-5]
after: [1.1, 3]
refined: true
risk: low
---

# Export the list as CSV

## Description

A reader downloads the whole reading list as CSV, one row per book, in the column set import reads back.

## Acceptance Criteria

Verify: Exporting a list of three books gives a CSV with a header row and three rows, in the dialect spike 3 chose.

## References

- parent — _bmad-output/initiative-shelf-v1/epic-csv-transfer/epic-csv-transfer.md

## Notes

- Decision: this story fixes the column set that import (entry 2) reads, so it covers FR-5 as well (user's decision, 2026-10-01).
