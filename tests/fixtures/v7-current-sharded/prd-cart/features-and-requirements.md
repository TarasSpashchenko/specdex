---
part_of: ./prd-cart.md
title: Features and requirements
summary: Every functional requirement for cart lines and totals, including the withdrawn gift-wrapping one.
group: Requirements
related:
- ./users-and-journeys.md
- ./rules-and-scope.md
---

## Features and requirements

Cart lines and totals, in dependency order; they realize both journeys.

### FR-1: Add an item

A shopper adds a product to the cart from its page, quantity one.

### Change and remove

- **FR-2.** A shopper changes a line's quantity; zero removes the line.
- FR-3: A shopper removes a line from the cart.

FR-4. A shopper sees the cart's line count in the page header.

FR-1, FR-2 and FR-3 share one cart per shopper, kept for 30 days.

### Totals

| Id | Requirement |
| --- | --- |
| FR-5 | A shopper sees the cart total, taken from the pricing source, update after every change. |

| Feature | Requirement |
| --- | --- |
| Pricing | **FR-6** A shopper sees each line's unit price as the pricing source states it. |

- FR-7: (withdrawn) Gift wrapping at checkout; out of the first release.

