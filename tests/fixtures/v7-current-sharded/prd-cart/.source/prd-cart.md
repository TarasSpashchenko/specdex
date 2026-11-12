---
title: "Cart"
template: prd
version: 1.1.0
status: final
created: "2026-10-02"
updated: "2026-10-06"
---

# Cart

## Table of Contents

- [Document purpose](#document-purpose) — readers and inputs
- [Vision](#vision) — one cart, one total
- [Users and journeys](#users-and-journeys) — UJ-1, UJ-2
- [Glossary](#glossary) — cart, line, total
- [Features and requirements](#features-and-requirements) — FR-1 to FR-6
- [Rules](#rules) — RULE-3 rounding
- [Non-goals](#non-goals) — gift wrapping, shared carts
- [MVP scope](#mvp-scope) — journeys in the first release
- [Success metrics](#success-metrics) — SM-3 checkout completion
- [Open questions](#open-questions) — OQ-1

## Document purpose

For the team building the cart, at initiative altitude. It builds on the shop charter and the cart BRD without repeating them.

## Vision

A shopper keeps one cart and always sees the total the shop will charge, so checking out holds no surprise.

## Users and journeys

Shoppers on the storefront, signed in or not.

UJ-1. Mia fills her cart on the bus. Signed in on her phone, she adds two mugs, raises one line to three and sees the total change at once. Realized by FR-1, FR-2 and FR-5.

UJ-2. Omar trims his cart before paying. He removes a line, sees the total drop and checks out. Realized by FR-3 and FR-5.

## Glossary

- Cart: the shopper's lines before checkout; one per shopper.
- Line: one product in the cart, with a quantity of one or more.
- Total: the sum of the lines as the pricing source prices them.

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

## Rules

- **RULE-3:** Only the order total is rounded, half up to the cent; a line is never rounded.

## Non-goals

No gift wrapping and no carts shared between shoppers.

## MVP scope

In: FR-1 to FR-4 and the totals. Out: saved items, which the BRD asks for later.

| Journey | Requirements |
| --- | --- |
| UJ-1 | FR-1, FR-2 |
| UJ-2 | FR-3 to FR-5 |

## Success metrics

- SM-3: Checkout completion, carts checked out over carts started, rises to 40% in the first month; validates FR-1 to FR-5. Counter-metric: carts abandoned after a price complaint stay under 1%.

## Open questions

- OQ-1: Does a cart survive sign-out? Owner: Lee; needed before the last checkout story; blocks FR-3.
