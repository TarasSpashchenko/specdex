"""Load and merge a BMAD profile with a project's settings.

The profile states what BMAD fixes; the project's settings state what one project adds. Settings come from the
skill's `customize.toml` with the project's `_bmad/custom/specdex.toml` and `specdex.user.toml` layered on top
(BMad customization), plus a legacy `specdex-overlay.toml` while projects migrate off it. Arrays of tables from the
settings are appended to the profile's, except artifact rules, which the settings place first so their more
specific globs win. Project variables come from BMad's central config. Both are read here with BMad's own merge
rules, never by running the project's resolver scripts: a read-only tool executes no project code. Nothing in this
module knows about any particular project.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import posixpath
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


VARIABLE = re.compile(r"\{([a-z_-]+)\}")
CONFIG_FILES = ("_bmad/config.toml", "_bmad/custom/config.toml", "_bmad/custom/config.user.toml")  # BMad's central layers
UNORDERED = 99  # detection order of a profile that states none
# Customization keys that mirror the overlay's arrays of tables and its tables (see customize.toml).
SETTING_ARRAYS = ("artifact", "family", "define", "elaborate", "positional", "historical", "superseded", "role", "replica", "marker")
SETTING_TABLES = ("aliases", "coverage", "doc_aliases", "frontmatter_types", "tokens")
SETTING_LISTS = ("records",)
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
    kind: str                 # owner | rationale | memlog | ticket | trail
    scope: str
    main: bool                # the file must be its folder's main file: <name>/<name>.md

    def matches(self, path: str) -> bool:
        if not self.regex.match(path):
            return False
        return not self.main or posixpath.splitext(posixpath.basename(path))[0] == posixpath.basename(posixpath.dirname(path))


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
    profile_reason: str = "given"
    current_scope: str | None = None        # owners under this folder are the candidate records
    backlog: str | None = None              # folder of standalone tickets
    diagnostics: list[tuple[str, str, str, int, str]] = field(default_factory=list)  # code, severity, path, line, detail
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
    return re.sub(r"/{2,}", "/", text).strip("/")  # an empty variable drops its segment, as BMad does


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


def get_dotted(data: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def structural_merge(base, override):
    """BMad's merge rule (its config_utils.structural_merge): tables merge recursively; arrays of tables keyed by
    `code` or `id` replace by key; other arrays append."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = structural_merge(merged[key], value) if key in merged else value
        return merged
    if isinstance(base, list) and isinstance(override, list):
        items = base + override
        key = next((k for k in ("code", "id") if items and all(isinstance(i, dict) and k in i for i in items)), None)
        if key is None:
            return base + override
        result: dict = {}
        for item in items:
            result[item[key]] = item
        return list(result.values())
    return override


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from error


def read_project_config(project_root: Path) -> dict:
    """BMad's merged central config: `_bmad/config.toml`, then the team and user layers in `_bmad/custom/`."""
    merged: dict = {}
    for relative in CONFIG_FILES:
        merged = structural_merge(merged, _load_toml(project_root / relative))
    return merged


def read_customization(project_root: Path, skill_root: Path) -> dict:
    """The skill's merged `[workflow]` customization: customize.toml, then the project's team and user layers."""
    merged = _load_toml(skill_root / "customize.toml")
    for layer in (f"{skill_root.name}.toml", f"{skill_root.name}.user.toml"):
        merged = structural_merge(merged, _load_toml(project_root / "_bmad" / "custom" / layer))
    return merged.get("workflow", {})


def unknown_settings(workflow: dict) -> list[str]:
    """`[workflow]` keys specdex does not read; a misplaced key would otherwise be ignored without a word."""
    return sorted(set(workflow) - set(SETTING_ARRAYS) - set(SETTING_TABLES) - set(SETTING_LISTS))


def settings_from_customization(workflow: dict) -> dict:
    """Customization `[workflow]` keys in the overlay's shape. BMad's keyed merge needs `id` on array items; a
    family's id is its name."""
    _check_shapes(workflow)
    settings: dict = {}
    for key in SETTING_ARRAYS:
        items = [dict(item) for item in workflow.get(key, [])]
        if key == "family":
            for item in items:
                item.setdefault("name", item.get("id"))
        if items:
            settings[key] = items
    settings.update({key: dict(workflow[key]) for key in SETTING_TABLES if workflow.get(key)})
    if workflow.get("records"):
        settings["current"] = {"records": list(workflow["records"])}
    return settings


def _check_shapes(workflow: dict) -> None:
    for key in SETTING_ARRAYS:
        value = workflow.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ConfigError(f"setting workflow.{key} must be an array of tables ([[workflow.{key}]])")
    for key in SETTING_TABLES:
        if not isinstance(workflow.get(key, {}), dict):
            raise ConfigError(f"setting workflow.{key} must be a table ([workflow.{key}])")
    records = workflow.get("records", [])
    if not isinstance(records, list) or not all(isinstance(path, str) for path in records):
        raise ConfigError("setting workflow.records must be a list of paths")


def combine_settings(legacy: dict, settings: dict) -> dict:
    """A legacy overlay and customization together: arrays append, tables merge, records append."""
    combined = dict(legacy)
    for key, value in settings.items():
        if key == "current":
            records = combined.get("current", {}).get("records", []) + value["records"]
            combined["current"] = {**combined.get("current", {}), "records": records}
        elif isinstance(value, list):
            combined[key] = list(combined.get(key, [])) + value
        else:
            combined[key] = {**combined.get(key, {}), **value}
    return combined


def project_variables(project_config: dict, profile: dict) -> dict[str, str]:
    section = profile.get("config", {})
    variables = {"project-root": ""}
    for name, default in section.get("defaults", {}).items():
        value = get_dotted(project_config, section.get("variables", {}).get(name, ""))
        variables[name] = value if isinstance(value, str) else default
    return {name: expand(value, variables) for name, value in variables.items()}


def _scope_is_set(requires: dict[str, str], variables: dict[str, str]) -> bool:
    """True when every required variable is set and names the kind of folder the scope needs (e.g. an initiative,
    not a backlog folder)."""
    return all(variables.get(name) and fnmatch.fnmatchcase(variables[name], pattern) for name, pattern in requires.items())


def worktree_matcher(project_root: Path) -> Callable[[str], bool]:
    return lambda pattern: next(project_root.glob(pattern), None) is not None


def listing_matcher(paths: list[str]) -> Callable[[str], bool]:
    """Glob matching against a file listing, such as a git revision's tree."""
    return lambda pattern: any(glob_to_regex(pattern).match(path) for path in paths)


def select_profile(profile_paths: list[Path], project_config: dict, exists: Callable[[str], bool],
                   use_config_keys: bool = True) -> tuple[Path, str]:
    """The profile whose layout detection matches the project, tried in each profile's `[detect] order`. `exists`
    tells whether a glob matches any project file. A git revision passes use_config_keys=False: the user's config
    layer belongs to today's worktree, not to the revision."""
    candidates = []
    for path in profile_paths:
        try:
            profile = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigError(f"{path.name}: {error}") from error
        candidates.append((profile.get("detect", {}), profile, path))
    candidates.sort(key=lambda c: c[0].get("order", UNORDERED))
    for detect, profile, path in candidates:
        variables = project_variables(project_config, profile)
        for name in detect.get("config_keys", []) if use_config_keys else []:
            if variables.get(name):
                return path, f"{name} is set ({variables[name]})"
        for pattern in detect.get("globs", []):
            if exists(expand(pattern, variables)):
                return path, f"found {expand(pattern, variables)}"
    default = next((path for detect, _, path in candidates if detect.get("default")), None)
    if default is None:
        raise ConfigError("no profile matches this project's layout and none is marked default")
    return default, "no layout matched; default profile"


def load(project_root: Path, profile_path: Path, overlay_path: Path | None = None, *, skill_root: Path | None = None,
         profile_reason: str = "given", legacy_default_overlay: bool = False,
         project_config: dict | None = None) -> Config:
    """Merge the profile with the project's settings. `overlay_path` is a legacy overlay file; with `skill_root`,
    the skill's BMad customization is read too. `project_config` is read_project_config's result when already known."""
    profile_bytes = profile_path.read_bytes()
    try:
        profile = tomllib.loads(profile_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(str(error)) from error
    if overlay_path and not overlay_path.is_file():
        raise ConfigError(f"{overlay_path}: no such overlay file")
    legacy = _load_toml(overlay_path) if overlay_path else {}
    expected = legacy.get("overlay", {}).get("profile")
    profile_id = profile["profile"]["id"]
    if expected and expected != profile_id:
        raise ConfigError(f"overlay targets profile {expected}, but {profile_id} was selected ({profile_reason}); "
                          "pass --profile or update the overlay")
    variables = project_variables(project_config if project_config is not None else read_project_config(project_root), profile)
    workflow = read_customization(project_root, skill_root) if skill_root else {}
    overlay = combine_settings(legacy, settings_from_customization(workflow))
    records = [expand(p, variables) for p in overlay.get("current", {}).get("records", [])]
    diagnostics: list[tuple[str, str, str, int, str]] = []
    if legacy_default_overlay and overlay_path:
        diagnostics.append(("deprecated-overlay", "low", overlay_path.relative_to(project_root).as_posix(), 0,
                            "specdex-overlay.toml is read for one more release; move it into _bmad/custom/specdex.toml: "
                            "each table under [workflow] ([[family]] becomes [[workflow.family]] with id = its name), "
                            "[current] records becomes [workflow] records, and [overlay] is dropped"))
    diagnostics += [("unknown-setting", "medium", "", 0, f"workflow.{key} (_bmad/custom/specdex.toml or specdex.user.toml) "
                     "is not a specdex setting and is ignored; the keys are in the skill's customize.toml")
                    for key in unknown_settings(workflow)]
    current = profile.get("current", {})
    current_scope = None
    if current.get("scope") and _scope_is_set(current.get("requires", {}), variables):
        current_scope = expand(current["scope"], variables)
    elif current.get("scope") and not records and not any(variables.get(name) for name in current.get("requires", {})):
        diagnostics.append(("no-active-initiative", "medium", "", 0,
                            "core.active_initiative is not set, so no initiative decides the specs of record; "
                            "choose one with the bmad skill"))

    def both(key: str) -> list:
        return list(profile.get(key, [])) + list(overlay.get(key, []))

    families: dict[str, Family] = {}
    for family in _build("family", both("family"), lambda r: Family(
            name=r["name"], kind=r.get("kind", "id"), pattern=r.get("pattern"),
            key=r.get("key"), owners=tuple(r.get("owner", [])), scope=r.get("scope", "project"))):
        families[family.name] = family
    artifacts = _build("artifact", list(overlay.get("artifact", [])) + list(profile.get("artifact", [])), lambda r: ArtifactRule(
        r["type"], glob_to_regex(expand(r["glob"], variables)), r.get("kind", "owner"), r.get("scope", "project"), bool(r.get("main"))))
    ranges = profile.get("ranges", {})
    # Settings, config and the diagnostics they raise all shape the index; dates in a legacy overlay print as text.
    effective = json.dumps([variables, overlay, diagnostics], sort_keys=True, default=str).encode()
    fingerprint = hashlib.sha256(b"\0".join([profile_bytes, effective, CODE_DIGEST.encode()])).hexdigest()[:16]
    backlog = profile.get("tickets", {}).get("backlog")
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
        defines=_build("define", both("define"), lambda r: DefineRule(r["family"], r["artifact"], r["shape"], r.get("section"), tuple(r.get("roots", [])))),
        elaborations=_build("elaborate", both("elaborate"), lambda r: ElaborateRule(tuple(r["families"]), r["artifact"], r["section"], r["shape"])),
        positional={rule.family: rule for rule in _build("positional", both("positional"), lambda r: PositionalRule(
            r["family"], r["container"], r.get("marker"), r.get("source")))},
        historical=_build("historical", both("historical"), lambda r: HistoricalRule(
            r["artifact"], r.get("section"), r.get("label"), bool(r.get("rows")), r.get("disposition_column"))),
        markers=_build("marker", both("marker"), lambda r: (r["name"], re.compile(r["pattern"]))),
        records=records,
        superseded=_build("superseded", both("superseded"), lambda r: Superseded(r["path"], r["by"], tuple(r.get("except_sections", [])))),
        roles=_build("role", both("role"), lambda r: RoleRule(glob_to_regex(expand(r["glob"], variables)), r["role"])),
        replicas=_build("replica", both("replica"), lambda r: tuple(r["paths"])),
        aliases=dict(overlay.get("aliases", {})),
        coverage={k: list(v) for k, v in {**profile.get("coverage", {}), **overlay.get("coverage", {})}.items()},
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
        profile_reason=profile_reason,
        current_scope=current_scope,
        backlog=expand(backlog, variables) if backlog else None,
        diagnostics=diagnostics,
    )


def _build(kind: str, raws: list[dict], build: Callable[[dict], object]) -> list:
    """Each profile or settings item built by `build`; an incomplete or malformed item is a configuration error
    naming the item, never a traceback."""
    items = []
    for raw in raws:
        try:
            items.append(build(raw))
        except KeyError as error:
            raise ConfigError(f"{kind} item {_item_name(raw)} lacks the key {error}") from error
        except (TypeError, ValueError, re.error) as error:
            raise ConfigError(f"{kind} item {_item_name(raw)} is malformed: {error}") from error
    return items


def _item_name(raw: dict) -> str:
    return repr(raw.get("id") or raw.get("name") or raw.get("type") or raw.get("family") or raw)
