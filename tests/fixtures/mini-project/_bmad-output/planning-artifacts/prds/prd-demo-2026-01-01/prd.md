---
title: Demo PRD
status: final
tags: [demo, sample]
owners:
  - pm
  - architect
---

# Demo Product Requirements

## 0. Conventions

FR-n.k names the k-th top-level bullet in an FR's consequences list.

## 1. Functional Requirements

### FR-1: Account sign-in

A user signs in with a LinkCredential issued by the host.

**Consequences (testable):**

- Sign-in succeeds for a known user.
- Sign-in fails after three wrong attempts
and the account locks for ten minutes.
  - The lock message names the unlock time.
- Sign-out clears the session.

### FR-2: Profile editing

A signed-in user edits their display name.

**Consequences (testable):**

- The new name appears on the next page load.
- Names longer than forty characters are rejected.

### FR-3: Data export

A user exports their history as a CSV file.

**Consequences (testable):**

- The export contains one row per recorded session.

## 2. Release Scope

FR-1–3 ship in the first release; FR-1.2 is the riskiest consequence.

| Requirement | Owner |
|---|---|
| FR-1 | Identity team |
| FR-3 | Data team |
