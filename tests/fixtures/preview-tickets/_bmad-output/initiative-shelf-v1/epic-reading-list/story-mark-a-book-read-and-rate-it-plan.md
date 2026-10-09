---
title: 'Mark a book read and rate it'
type: 'feature' # feature | bugfix | refactor | chore
ticket: '2' # the entry id from the ticket tree, or the story file's stem when the entry has no id; empty outside it
created: '2026-10-02'
status: 'in-progress' # draft | ready-for-dev | in-progress | in-review | built | done | blocked
route: 'full' # oneshot | full — set by step-02
route_source: 'auto' # pinned | auto — set with route by step-02
review: '' # none | quick | thorough — set by step-04
review_source: '' # pinned | auto — set with review by step-04
lenses_ran: [] # ids of the lenses launched, set by step-04
review_loop_iteration: 0 # incremented by step-04 before each review loopback
context: [] # optional: `{project-root}/`-prefixed paths to project-wide standards/docs the implementation agent should load. Keep short — only what isn't already distilled into the plan body.
baseline_revision: '3f2a9c1'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A reader cannot record that a book is read or say what they thought of it.

**Approach:** Add a read date and a 1–5 rating to the book record, set from the book's row on the list.

## Boundaries & Constraints

**Always:** A rating exists only on a book marked read.

**Never:** Change how books are added (entry 1).

</frozen-after-approval>

## Code Map

- `src/books/record.py` -- the book record; gains `read_on` and `rating`

## Tasks & Acceptance

**Execution:**
- [x] `src/books/record.py` -- add `read_on` and `rating` -- the record owns both
- [ ] `src/web/list_row.py` -- add the mark-read and rating controls -- the row is where a reader acts

**Acceptance Criteria:**
- Given an unread book, when the reader marks it read, then today's date shows and a rating can be set

## Implementation Notes

## Verification

**Commands:**
- `python3 -m unittest tests.test_books` -- expected: all pass
