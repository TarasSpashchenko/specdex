---
name: 'Checkout cart'
type: architecture-spine
purpose: build-substrate
altitude: epic
paradigm: 'hexagonal'
scope: 'Cart lines and the empty cart in epic-checkout'
status: final
created: '2026-10-14'
updated: '2026-10-14'
binds: [R1, R2, R5]
sources: [_bmad-output/initiative-cart/tickets/epic-checkout/epic-checkout.md, _bmad-output/initiative-cart/architecture-cart/architecture-cart.md]
---

# Architecture Spine — Checkout cart

## Inherited Invariants

| Inherited | From parent | Binds here |
| --- | --- | --- |
| AD-1 | architecture-cart | Only the cart service writes the lines these stories add, change and remove. |

## Invariants & Rules

### AD-3 — One line per product

- **Binds:** R1, R2, R5
- **Prevents:** two lines for one product, and an empty cart rendered as an error.
- **Rule:** The cart merges an add into the product's existing line, and a cart with no lines renders the empty state.

## Deferred

- A cap on lines per cart: no requirement asks for one yet.
