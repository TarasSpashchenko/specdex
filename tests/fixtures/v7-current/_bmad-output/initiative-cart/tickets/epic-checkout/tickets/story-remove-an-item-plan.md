---
title: 'Remove an item'
type: feature # feature | bugfix | refactor | chore
ticket: '2' # the entry id from the ticket tree, or the story file's stem when the entry has no id; empty outside it
created: '2026-10-21'
status: in-progress # draft | ready-for-dev | in-progress | in-review | built | done | blocked | dropped
baseline_revision: '9d03e51'
route: 'full'
route_source: 'auto'
risk: 'low'
review: ''
review_source: ''
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A shopper cannot change or remove a cart line.

**Approach:** A quantity stepper and a remove action on each line; zero lines render the empty cart.

</frozen-after-approval>

## Tasks & Acceptance

**Execution:**
- [ ] `cart/domain/cart.py` -- set a line's quantity, zero removes it -- one rule for both actions

**Acceptance Criteria:**
- Given a cart with one line, when the shopper removes it, then the empty cart links to the catalogue
