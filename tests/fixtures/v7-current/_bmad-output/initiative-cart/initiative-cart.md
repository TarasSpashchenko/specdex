---
type: initiative
title: "Shoppers keep a cart and check out"
sources: [_bmad-output/initiative-shop/initiative-shop.md, _bmad-output/initiative-cart/prd-cart/prd-cart.md, _bmad-output/initiative-cart/brd-cart/brd-cart.md]
companions: [_bmad-output/initiative-cart/ux-cart/DESIGN.md]
after: []
status: in-progress
risk: medium
---

# Shoppers keep a cart and check out

## Description

A shopper fills a cart, sees one total from the pricing source and checks out. The cart PRD owns the capabilities, the BRD the business commitments, and the parent initiative the pricing rule.

## Outcome

Shoppers who start a cart finish checking out; the PRD's checkout-completion metric is the signal.

## Requirements

- R1 (FR-1, FR-2): A shopper adds an item to the cart and changes its quantity, and the cart lists each line with its quantity.
- R2 (prd FR-3): A shopper removes a line, and neither the cart nor its total includes it any more.
- R3 (parent R1): Every cart total comes from the pricing source.
- R4 (brd BR-1): A signed-in shopper saves an item for later and finds it on the next visit.
- R5 (Scope): A cart started signed out carries over when the shopper signs in.

## Constraints

- Only the order total is rounded, never a line (prd RULE-3).
- A saved item shows its current price, not the price when saved (brd RULE-4).

## Done when

1. Shoppers add, change and remove cart lines on the live site.
2. Every cart total matches the pricing source.
3. Checkout completion reaches the PRD's target in the first month.

## Boundaries

The cart and checkout of the storefront. Not search (initiative-search), not payment beyond the provider's hosted page.

- Touch point: pricing source — read for every total; owner: epic-checkout
- Tracer path: add one item, see its total from the pricing source, check out.

## References

- parent — _bmad-output/initiative-shop/initiative-shop.md, section Requirements
- prd — _bmad-output/initiative-cart/prd-cart/prd-cart.md, section Features and requirements
- brd — _bmad-output/initiative-cart/brd-cart/brd-cart.md, sections Business requirements and Scope
- design — _bmad-output/initiative-cart/ux-cart/DESIGN.md

## Notes

- Decision: one checkout epic, and saved items as a second epic (2026-10-08).
- Parked: R5, signed-out carts, until sign-in exists; the user knows (2026-10-08).
