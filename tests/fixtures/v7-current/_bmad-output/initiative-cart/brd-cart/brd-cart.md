---
title: "Cart for the online shop"
template: brd
version: 1.1.0
status: final
created: "2026-09-25"
updated: "2026-09-30"
---

# Cart for the online shop

## Table of Contents

- [Summary](#summary) — what changes and why now
- [Objectives](#objectives) — the charter's benefits
- [Stakeholders](#stakeholders) — sponsor, owner, builder
- [Scope](#scope) — signed-out carts in, payments out
- [Current and future process](#current-and-future-process) — phone orders to online
- [Business requirements](#business-requirements) — BR-1, BR-2
- [Business rules](#business-rules) — RULE-4 saved-item price
- [Traceability](#traceability) — BR-1, BR-2 to later documents
- [Open questions](#open-questions) — launch staffing
- [Approval](#approval) — who signs

## Summary

Shoppers who phone in orders today need to order online. The agency building the storefront delivers the cart against this baseline.

## Objectives

Serves the shop charter's online-orders and phone-orders benefits.

## Stakeholders

Lee (sponsor, approves), Dana (sales, owns the outcome), the storefront agency (builds).

## Scope

In: a cart for signed-in and signed-out shoppers, kept across sign-in. Out: payments and delivery.

## Current and future process

Today a shopper phones and staff key the order. After, the shopper builds the cart online and staff only pack it.

## Business requirements

| Id | Requirement | Owner | Source | Priority | Verify |
| --- | --- | --- | --- | --- | --- |
| BR-1 | Shoppers keep items for a later visit. | Dana | Sales interviews | Should | A saved item is still there a week later. |
| BR-2 | Every order reaches the warehouse with its lines and total. | Dana | Warehouse | Must | Ten test orders match the warehouse list. |

## Business rules

- RULE-4: A saved item shows its current price, not the price when it was saved. Owner: Dana; source: pricing policy.

## Traceability

| Id | PRD line | Test | Ticket |
| --- | --- | --- | --- |
| BR-1 | | | |
| BR-2 | | | |

## Open questions

- Who answers shoppers' cart questions in the first month? Owner: Dana; blocks launch staffing.

## Approval

| Name | Role | Decision | Date |
| --- | --- | --- | --- |
| Lee | Sponsor | Approved | 2026-09-30 |
