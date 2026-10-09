"""Load and merge a BMAD profile with a project overlay.

The profile states what BMAD fixes; the overlay states what one project adds.
Both are TOML. Arrays of tables from the overlay are appended to the profile's,
except artifact rules, which the overlay places first so its more specific
globs win. Nothing in this module knows about any particular project.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


VARIABLE = re.compile(r"\{([a-z_-]+)\}")
# Extraction rules live in this package's code: a changed module must never reuse an index built by another.
CODE_DIGEST = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()


class ConfigError(Exception):
    """The profile, overlay or project configuration cannot be used."""


@dataclass(frozen=True, slots=True)
class Family:
    name: str
    kind: str                 # "id" | "token" | "term"
    pattern: str | None
    key: str | None           # "int" | "alpha"
    owners: tuple[str, ...]
    scope: str                # "project" | "document"


@dataclass(frozen=True, slots=True)
class DefineRule:
    family: str
    artifact: str
    shape: str                # heading | item-lead | row-key | yaml-tokens | item-lead-term
    section: str | None
    roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ElaborateRule:
    families: tuple[str, ...]
    artifact: str
    section: str
    shape: str                # heading | row-key | row-any


@dataclass(frozen=True, slots=True)
class PositionalRule:
    family: str
    container: str            # after-marker | first-list
    marker: str | None
    source: str | None        # where the project states the convention, e.g. "prd §0"


@dataclass(frozen=True, slots=True)
class HistoricalRule:
    artifact: str
    section: str | None
    label: str | None
    rows: bool
    disposition_column: str | None


@dataclass(frozen=True, slots=True)
class ArtifactRule:
    type: str
    regex: re.Pattern
    kind: str                 # owner | memlog | ticket | trail
    scope: str


@dataclass(frozen=True, slots=True)
class RoleRule:
    regex: re.Pattern
    role: str


@dataclass(frozen=True, slots=True)
class Superseded:
    path: str
    by: str
    except_sections: tuple[str, ...]


@dataclass(slots=True)
class Config:
    project_root: Path
    profile_id: str
    profile_path: Path
    overlay_path: Path | None
    variables: dict[str, str]
    scan_roots: list[str]
    include: list[str]
    skip_dirs: set[str]
    artifacts: list[ArtifactRule]
    frontmatter_types: dict[str, str]
    families: dict[str, Family]
    defines: list[DefineRule]
    elaborations: list[ElaborateRule]
    positional: dict[str, PositionalRule]
    historical: list[HistoricalRule]
    markers: list[tuple[str, re.Pattern]]
    records: list[str]
    superseded: list[Superseded]
    roles: list[RoleRule]
    replicas: list[tuple[str, ...]]
    aliases: dict[str, str]
    coverage: dict[str, list[str]]
    range_separators: list[str]
    range_short_form: bool
    range_max: int
    spine: dict[str, str]
    fields: dict[str, str]
    token_bare_backtick: bool
    memlog_entry: re.Pattern
    binding: dict
    layout_unsupported: list[dict]
    validators: list[dict]
    doc_aliases: dict[str, list[str]]
    fingerprint: str
    id_regex: re.Pattern = field(init=False)
    family_groups: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.id_regex, self.family_groups = compile_id_regex(self.families)

    def expand(self, text: str) -> str:
        return expand(text, self.variables)


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a path glob (** spans directories, * stays within one) to an anchored regex."""
    out, index = [], 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        elif char == "[":
            close = pattern.find("]", index)
            out.append(pattern[index:close + 1] if close > index else re.escape(char))
            index = close + 1 if close > index else index + 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def expand(text: str, variables: dict[str, str]) -> str:
    for _ in range(8):  # bounded: variables may reference each other
        expanded = VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)
        if expanded == text:
            break
        text = expanded
    return text.strip("/")


def compile_id_regex(families: dict[str, Family]) -> tuple[re.Pattern, dict[str, str]]:
    """One alternation over every ID family; longer literal prefixes first."""
    groups, parts = {}, []
    id_families = [f for f in families.values() if f.kind == "id" and f.pattern]
    for number, family in enumerate(sorted(id_families, key=lambda f: -len(f.pattern))):
        group = f"f{number}"
        groups[group] = family.name
        parts.append(f"(?P<{group}>{family.pattern.replace('(?P<key>', f'(?P<k{number}>')})")
    if not parts:
        return re.compile(r"(?!x)x"), groups
    # The tail guard rejects "FR-1.2foo" outright instead of backtracking to "FR-1".
    return re.compile(r"(?<![\w-])(?:" + "|".join(parts) + r")(?:\.(?P<sub>\d+))?(?![\w-]|\.\w)"), groups


def deep_merge(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_dotted(data: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def load_project_variables(project_root: Path, profile: dict) -> dict[str, str]:
    section = profile.get("config", {})
    merged: dict = {}
    for relative in section.get("files", []):
        candidate = project_root / relative
        if candidate.is_file():
            try:
                merged = deep_merge(merged, tomllib.loads(candidate.read_text(encoding="utf-8")))
            except tomllib.TOMLDecodeError as error:
                raise ConfigError(f"{relative}: {error}") from error
    variables = {"project-root": ""}
    for name, default in section.get("defaults", {}).items():
        value = get_dotted(merged, section.get("variables", {}).get(name, ""))
        variables[name] = value if isinstance(value, str) else default
    return {name: expand(value, variables) for name, value in variables.items()}


def load(project_root: Path, profile_path: Path, overlay_path: Path | None) -> Config:
    profile_bytes = profile_path.read_bytes()
    overlay_bytes = overlay_path.read_bytes() if overlay_path else b""
    try:
        profile = tomllib.loads(profile_bytes.decode("utf-8"))
        overlay = tomllib.loads(overlay_bytes.decode("utf-8")) if overlay_path else {}
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(str(error)) from error
    expected = overlay.get("overlay", {}).get("profile")
    profile_id = profile["profile"]["id"]
    if expected and expected != profile_id:
        raise ConfigError(f"overlay targets profile {expected}, loaded {profile_id}")
    variables = load_project_variables(project_root, profile)

    def both(key: str) -> list:
        return list(profile.get(key, [])) + list(overlay.get(key, []))

    families: dict[str, Family] = {}
    for raw in both("family"):
        families[raw["name"]] = Family(
            name=raw["name"], kind=raw.get("kind", "id"), pattern=raw.get("pattern"),
            key=raw.get("key"), owners=tuple(raw.get("owner", [])), scope=raw.get("scope", "project"))
    artifacts = [ArtifactRule(r["type"], glob_to_regex(expand(r["glob"], variables)), r.get("kind", "owner"), r.get("scope", "project"))
                 for r in list(overlay.get("artifact", [])) + list(profile.get("artifact", []))]
    ranges = profile.get("ranges", {})
    effective = json.dumps(variables, sort_keys=True).encode()  # project config can move the output folders
    fingerprint = hashlib.sha256(b"\0".join([profile_bytes, overlay_bytes, effective, CODE_DIGEST.encode()])).hexdigest()[:16]
    return Config(
        project_root=project_root,
        profile_id=profile_id,
        profile_path=profile_path,
        overlay_path=overlay_path,
        variables=variables,
        scan_roots=[expand(root, variables) for root in profile.get("scan", {}).get("roots", ["{output_folder}"])],
        include=list(profile.get("scan", {}).get("include", ["*.md"])),
        skip_dirs=set(profile.get("scan", {}).get("skip_dirs", [".git"])),
        artifacts=artifacts,
        frontmatter_types={**profile.get("frontmatter_types", {}), **overlay.get("frontmatter_types", {})},
        families=families,
        defines=[DefineRule(r["family"], r["artifact"], r["shape"], r.get("section"), tuple(r.get("roots", []))) for r in both("define")],
        elaborations=[ElaborateRule(tuple(r["families"]), r["artifact"], r["section"], r["shape"]) for r in both("elaborate")],
        positional={r["family"]: PositionalRule(r["family"], r["container"], r.get("marker"), r.get("source")) for r in both("positional")},
        historical=[HistoricalRule(r["artifact"], r.get("section"), r.get("label"), bool(r.get("rows")), r.get("disposition_column")) for r in both("historical")],
        markers=[(r["name"], re.compile(r["pattern"])) for r in both("marker")],
        records=[p.strip("/") for p in overlay.get("current", {}).get("records", [])],
        superseded=[Superseded(r["path"], r["by"], tuple(r.get("except_sections", []))) for r in both("superseded")],
        roles=[RoleRule(glob_to_regex(expand(r["glob"], variables)), r["role"]) for r in both("role")],
        replicas=[tuple(r["paths"]) for r in both("replica")],
        aliases=dict(overlay.get("aliases", {})),
        coverage={k: list(v) for k, v in overlay.get("coverage", {}).items()},
        range_separators=list(ranges.get("separators", ["–"])),
        range_short_form=bool(ranges.get("short_form", False)),
        range_max=int(ranges.get("max_members", 200)),
        spine=dict(profile.get("spine", {})),
        fields=dict(profile.get("fields", {})),
        token_bare_backtick=bool(overlay.get("tokens", {}).get("bare_backtick", False)),
        memlog_entry=re.compile(profile.get("memlog", {}).get("entry", r"^- (?P<text>.*)$")),
        binding=dict(profile.get("binding", {})),
        layout_unsupported=[{"glob": expand(r["glob"], variables), "reason": r["reason"]} for r in profile.get("layout", {}).get("unsupported", [])],
        validators=list(profile.get("validator", [])),
        doc_aliases={k.lower(): list(v) for k, v in {**profile.get("doc_aliases", {}), **overlay.get("doc_aliases", {})}.items()},
        fingerprint=fingerprint,
    )
