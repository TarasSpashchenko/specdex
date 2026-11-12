---
title: Shelf
created: 2026-09-15
updated: 2026-09-15
---

# PRD: Shelf

## 0. Document Purpose

For the PM and the ticketing and build workflows. Features are grouped with their FRs nested; FRs are numbered globally.

## 1. Vision

Shelf keeps one personal reading list a reader trusts: what they own, what they have read, and what they thought of it.

## 3. Glossary

- **Book** — one edition, identified by its ISBN.
- **Reading list** — the books one reader has added. One per reader.

## 4. Features

### 4.1 Reading list

**Description:** A reader builds the list by ISBN and records what they have read and how they rated it.

**Functional Requirements:**

#### FR-1: Add a book by ISBN

A reader can add a book to the reading list by its ISBN.

**Consequences (testable):**
- The added book shows its title and author.
- An ISBN the catalogue does not know is refused, with the reason shown.

#### FR-2: Mark a book read

A reader can mark a book on the list as read; the date is kept.

#### FR-3: Rate a read book

A reader can rate a read book from 1 to 5 stars.

### 4.2 CSV transfer

**Functional Requirements:**

#### FR-4: Export the list as CSV

A reader can export the whole reading list as CSV, one row per book.

#### FR-5: Import a list from CSV

A reader can import a CSV in the export's format; rows that do not parse are listed and nothing is half-imported.

### 4.3 Sharing

**Functional Requirements:**

#### FR-6: Share a public reading list

A reader can publish a read-only link to the reading list.

## 5. Non-Goals (Explicit)

- Shelf is not a bookshop and never sells books.

## 6. MVP Scope

### 6.1 In Scope

- FR-1–FR-5.

### 6.2 Out of Scope for MVP

- FR-6, public lists: deferred to v2.
