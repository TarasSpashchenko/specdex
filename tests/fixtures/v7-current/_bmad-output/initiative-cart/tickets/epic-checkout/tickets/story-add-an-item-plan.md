---
title: 'Add an item'
type: feature # feature | bugfix | refactor | chore
ticket: 1 # the entry id from the ticket tree, or the story file's stem when the entry has no id; empty outside it
created: '2026-10-16'
status: done # draft | ready-for-dev | in-progress | in-review | built | done | blocked | dropped
baseline_revision: '4f1c2ab'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'auto'
lenses_ran: [edge-case-hunter]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A shopper cannot put a product in a cart.

**Approach:** An add-to-cart action on the product page writes one line through the cart service.

</frozen-after-approval>

## Code Map

- `cart/domain/cart.py` -- the cart and its lines

## Tasks & Acceptance

**Execution:**
- [x] `cart/domain/cart.py` -- add a line with quantity one -- the story's one path

**Acceptance Criteria:**
- Given an empty cart, when a shopper adds a mug, then the cart shows one line with quantity one

## Verification

**Commands:**
- `pytest cart` -- expected: all pass
