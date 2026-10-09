#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write or verify the frozen corpus lock: sha256 of every file (symlinks recorded by target)."""
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpora" / "tamagai-2026-10-04"
LOCK = HERE / "corpus.lock.json"


def inventory(root: Path) -> dict:
    entries = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]):
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                entries[rel] = "symlink:" + os.readlink(full)
            elif full.is_file():
                entries[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
    return entries


def main() -> int:
    current = inventory(CORPUS)
    if sys.argv[1:] == ["--write"]:
        LOCK.write_text(json.dumps({"source": "tamagai worktree at 502a77a + uncommitted 2026-10-04 edits", "files": current}, indent=0, sort_keys=True))
        print(f"wrote {len(current)} entries")
        return 0
    locked = json.loads(LOCK.read_text())["files"]
    changed = sorted(k for k in set(locked) | set(current) if locked.get(k) != current.get(k))
    print("corpus OK" if not changed else f"CORPUS CHANGED: {changed[:20]}")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
