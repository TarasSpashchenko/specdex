---
name: Shelf
type: architecture-spine
purpose: Keep the list service and the catalogue adapter consistent.
altitude: product
status: final
created: 2026-10-02
updated: 2026-10-02
binds: [FR-1, FR-4, FR-5]
---

# Shelf — Architecture Spine

## Decisions

### AD-1 — One list store per reader

**Binds:** FR-1, FR-2

**Prevents:** two lists drifting apart.

**Rule:** every list write goes through the list service.

### AD-2 — CSV goes through the same validator as the UI

**Binds:** FR-4, FR-5

**Prevents:** half-imported lists.

**Rule:** import validates every row before writing any.
