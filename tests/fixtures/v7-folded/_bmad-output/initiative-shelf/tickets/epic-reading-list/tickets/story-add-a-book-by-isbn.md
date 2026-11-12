---
id: 1
type: story
title: "Add a book by ISBN"
parent: epic-reading-list
covers: [E1, E2]
refined: true
risk: low
---

# Add a book by ISBN

## Description

A reader adds a book by its ISBN and sees its title and author; an unknown ISBN is refused with the reason.

## Acceptance Criteria

Verify: Adding 9780141439518 shows Pride and Prejudice by Jane Austen; adding 9780000000000 shows "ISBN not found" and the list is unchanged.

## References

- parent — _bmad-output/initiative-shelf/tickets/epic-reading-list/epic-reading-list.md
- catalogue — docs/catalogue-api.md, section ISBN lookup
