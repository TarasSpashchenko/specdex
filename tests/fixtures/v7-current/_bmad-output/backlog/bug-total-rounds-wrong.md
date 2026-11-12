---
type: bug
title: "The cart total rounds each line instead of the total"
parent: none
covers: [FR-5]
after: []
refined: false
hitl: false
risk: medium
severity: P2
---

# The cart total rounds each line instead of the total

## Description

Three lines priced 0.333 each show a total of 0.99 instead of 1.00: each line is rounded before the sum.

## Reproduction

Add three products priced 0.333 to an empty cart. Actual total 0.99; expected 1.00.

## Cause Hypothesis

The cart sums rounded line prices instead of taking the total from the pricing source.

## References

- parent — none
- prd — _bmad-output/initiative-cart/prd-cart/prd-cart.md, section Features and requirements
