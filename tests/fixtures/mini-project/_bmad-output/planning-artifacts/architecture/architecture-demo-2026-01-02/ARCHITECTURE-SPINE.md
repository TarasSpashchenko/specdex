---
title: Demo Architecture Spine
type: architecture-spine
---

# Demo Architecture Spine

## AD-1: Signed session cookie

- **Binds:** FR-1, FR-1.2
- **Rule:** Sessions live in a signed, HTTP-only cookie.

## AD-2: Streaming export

- **Binds:** FR-3
- **Rule:** Exports stream rows to disk instead of buffering them.
