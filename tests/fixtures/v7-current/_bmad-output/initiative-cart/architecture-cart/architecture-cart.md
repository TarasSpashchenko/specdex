---
name: 'Cart'
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'hexagonal'
scope: 'The cart service and its calls to the pricing source'
status: final
created: '2026-10-07'
updated: '2026-10-08'
binds: [R1, R2, R3, R4]
sources: [_bmad-output/initiative-cart/initiative-cart.md]
---

# Architecture Spine — Cart

## Design Paradigm

Hexagonal: `cart/domain` holds the cart and its lines, `cart/ports` the pricing and storage ports, `cart/adapters` their implementations.

## Invariants & Rules

### AD-1 — The cart service owns its lines

- **Binds:** R1, R2
- **Prevents:** two services editing one cart's lines.
- **Rule:** Only the cart service writes cart lines; every other service calls its API.

### AD-2 — Prices come from the pricing port

- **Binds:** R3, R4
- **Prevents:** a total or a saved item's price computed apart from the pricing source.
- **Rule:** The cart asks the pricing port for every total and every saved item's price, and never sums prices itself.

```mermaid
flowchart LR
  web --> cart
  cart --> pricing
```

## Stack

| Name | Version |
| --- | --- |
| Python | 3.12 |

## Capability → Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| R1 | cart/domain | AD-1 |
| R2 | cart/domain | AD-1 |
| R3 | cart/ports/pricing | AD-2 |
| R4 | cart/adapters/saved-items | AD-2 |

## Deferred

- Deployment and environments: the storefront platform's hosting decides them; nothing here depends on it.
