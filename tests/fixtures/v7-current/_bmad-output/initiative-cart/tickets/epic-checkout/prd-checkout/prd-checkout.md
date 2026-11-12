---
title: "Checkout cart"
template: prd
version: 1.1.0
status: final
created: "2026-10-12"
updated: "2026-10-14"
---

# Checkout cart

## Table of Contents

- [Document purpose](#document-purpose) — epic altitude, the cart PRD as parent
- [Vision](#vision) — the cart a shopper checks out
- [Users and journeys](#users-and-journeys) — UJ-1, UJ-2 from the cart PRD
- [Glossary](#glossary) — the cart PRD's terms
- [Features and requirements](#features-and-requirements) — FR-8, FR-9; extends FR-1 and FR-3
- [Non-goals](#non-goals) — no saved items
- [MVP scope](#mvp-scope) — this epic's slice
- [Success metrics](#success-metrics) — SM-3
- [Open questions](#open-questions) — none open

## Document purpose

For the builders of epic-checkout. It cites the cart PRD's ids and adds the edge cases this epic meets.

## Vision

The cart a shopper checks out is the cart they built, line for line.

## Users and journeys

UJ-1 and UJ-2 from the cart PRD apply unchanged.

## Glossary

Uses the cart PRD's glossary.

## Features and requirements

Extends FR-1 and FR-3 with their edge cases.

- **FR-8:** A shopper who removes the last line sees an empty cart with a link back to the catalogue.
- **FR-9:** Adding a product already in the cart raises that line's quantity instead of adding a second line.

## Non-goals

No saved items and no change to how totals are priced.

## MVP scope

In: FR-8, FR-9 and the cart PRD's FR-1 to FR-3. Out: anything FR-5 does not already state about totals.

## Success metrics

SM-3 from the cart PRD; no epic-level metric.

## Open questions

None open.
