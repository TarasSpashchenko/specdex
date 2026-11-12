---
type: epic
title: "Shoppers fill a cart and check it out"
parent: initiative-cart
covers: [R1, R2, R3]
sources: [_bmad-output/initiative-cart/initiative-cart.md, _bmad-output/initiative-cart/tickets/epic-checkout/prd-checkout/prd-checkout.md]
companions: [_bmad-output/initiative-cart/tickets/epic-checkout/architecture-checkout/architecture-checkout.md]
after: []
status: in-progress
risk: medium
---

# Shoppers fill a cart and check it out

## Description

A shopper adds, changes and removes cart lines and sees the pricing source's total, through to checkout. It delivers the initiative's cart lines and pricing rule; its PRD adds the edge cases.

## Outcome

Shoppers check out the cart they built; the PRD's checkout-completion metric is the signal.

## Requirements

- R1 (parent R1): A shopper adds an item to the cart from its page and sees it listed.
- R2 (parent R1): A shopper changes a line's quantity, and a quantity of zero removes the line.
- R3 (parent R2): A shopper removes a line, and the total no longer includes it.
- R4 (parent R3): The cart total is the pricing source's total for the lines.
- R5 (prd FR-8): A shopper who removes the last line sees an empty cart that links back to the catalogue.

## Constraints

- Only the order total is rounded, never a line (RULE-3).

## Done when

1. Add, change and remove work on the live site for every shopper.
2. Every total shown equals the pricing source's total for the same lines.
3. The empty cart links back to the catalogue.

## Boundaries

Cart lines, totals and the empty cart. Not saved items (epic-wishlist), not payment.

## References

- parent — _bmad-output/initiative-cart/initiative-cart.md, section Requirements
- prd — _bmad-output/initiative-cart/tickets/epic-checkout/prd-checkout/prd-checkout.md, section Features and requirements
- architecture — _bmad-output/initiative-cart/tickets/epic-checkout/architecture-checkout/architecture-checkout.md, AD-3

## Notes

- Decision: the tracer bullet is entry 1, adding an item end to end (2026-10-15).
