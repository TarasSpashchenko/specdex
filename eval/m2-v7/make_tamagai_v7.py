#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Build the tamagai-v7 corpus: the frozen M1 tamagai corpus moved into the BMad v7 initiative layout.

Only paths change, never bytes, so every M1 gold line range stays valid after remapping its path. The moves
follow bmod-method's migration-1 (dated run folders become `<type>-<slug>/` inside the initiative, main files
take the folder's name). The project gets `core.active_initiative` and its specdex settings as BMad
customization (`_bmad/custom/specdex.toml`, from tamagai-v7-specdex.toml). Beside this script it writes
`path-map.json`, Layer B's explicit overlay (`overlay-tamagai-v7.toml`, the M1 overlay with v7 paths, pinned to
the bmad-v7 profile) and the M1 gold set with remapped paths (`gold-tamagai-v7/`).
Usage: uv run make_tamagai_v7.py
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPORA = HERE.parent / "corpora"
SOURCE = CORPORA / "tamagai-2026-10-04"
TARGET = CORPORA / "tamagai-v7-2026-10-09"
SETTINGS = HERE / "tamagai-v7-specdex.toml"
PATH_MAP = HERE / "path-map.json"
M1 = HERE.parent / "m1-tamagai"
LAYER_B_OVERLAY = HERE / "overlay-tamagai-v7.toml"
GOLD = HERE / "gold-tamagai-v7"
# Overlay globs over the dated planning folders, and their v7 equivalents.
GLOB_MOVES = [("{planning_artifacts}/architecture/architecture-*/", "{output_folder}/**/architecture-*/"),
              ("{planning_artifacts}/research/*/", "**/research-*/")]

PA = "_bmad-output/planning-artifacts"
INITIATIVE = "_bmad-output/initiative-tamagai"
# Ordered: whole files before their folders; the first matching prefix wins.
MOVES = [
    (f"{PA}/prds/prd-tamagai-2026-09-29/prd.md", f"{INITIATIVE}/prd-tamagai/prd-tamagai.md"),
    (f"{PA}/prds/prd-tamagai-2026-09-29/", f"{INITIATIVE}/prd-tamagai/"),
    (f"{PA}/briefs/brief-tamagai-2026-09-29/brief.md", f"{INITIATIVE}/brief-tamagai/brief-tamagai.md"),
    (f"{PA}/briefs/brief-tamagai-2026-09-29/", f"{INITIATIVE}/brief-tamagai/"),
    (f"{PA}/ux-designs/ux-tamagai-2026-09-30/", f"{INITIATIVE}/ux-tamagai/"),
    (f"{PA}/architecture/architecture-tamagai-2026-10-03/ARCHITECTURE-SPINE.md", f"{INITIATIVE}/architecture-tamagai/architecture-tamagai.md"),
    (f"{PA}/architecture/architecture-tamagai-2026-10-03/", f"{INITIATIVE}/architecture-tamagai/"),
    (f"{PA}/research/", f"{INITIATIVE}/research-"),
    (f"{PA}/", f"{INITIATIVE}/"),
    ("_bmad-output/brainstorming/", f"{INITIATIVE}/"),
]


def moved(path: str) -> str:
    for old, new in MOVES:
        if path.startswith(old):
            return new + path[len(old):]
    return path


def v7_overlay(text: str) -> str:
    for old, new in GLOB_MOVES:
        text = text.replace(old, new)
    text = re.sub(r'"(_bmad-output/planning-artifacts/[^"]+)"', lambda m: f'"{moved(m.group(1))}"', text)
    return text.replace('profile = "bmad-6.13.0-next"', 'profile = "bmad-v7"')


def v7_gold(tasks: list[dict]) -> list[dict]:
    for task in tasks:
        for unit in task.get("evidence", []) + task.get("forbidden", []):
            unit["path"] = moved(unit["path"])
        citations = task.get("citations") or {}
        for line in citations.get("lines", []):
            line["path"] = moved(line["path"])
        if "scope" in citations:
            citations["scope"] = re.sub(r"_bmad-output/planning-artifacts/\S+?\.md", lambda m: moved(m.group(0)), citations["scope"])
    return tasks


def main() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    path_map = {}
    for source in sorted(p for p in SOURCE.rglob("*") if p.is_file()):
        relative = source.relative_to(SOURCE).as_posix()
        target = moved(relative)
        path_map[relative] = target
        (TARGET / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, TARGET / target)
    user_config = TARGET / "_bmad" / "custom" / "config.user.toml"
    user_config.parent.mkdir(parents=True, exist_ok=True)
    user_config.write_text('[core]\nactive_initiative = "initiative-tamagai"\n', encoding="utf-8")
    shutil.copy(SETTINGS, TARGET / "_bmad" / "custom" / "specdex.toml")
    PATH_MAP.write_text(json.dumps({k: v for k, v in path_map.items() if k != v}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    LAYER_B_OVERLAY.write_text(v7_overlay((M1 / "overlay.toml").read_text(encoding="utf-8")), encoding="utf-8")
    GOLD.mkdir(exist_ok=True)
    for split in ("dev", "heldout"):
        tasks = json.loads((M1 / "gold" / f"{split}.json").read_text(encoding="utf-8"))
        (GOLD / f"{split}.json").write_text(json.dumps(v7_gold(tasks), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{TARGET.name}: {len(path_map)} files, {sum(k != v for k, v in path_map.items())} moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
