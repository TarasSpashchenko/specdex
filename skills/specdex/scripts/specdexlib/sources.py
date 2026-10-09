"""Read-only views of the project's files: the working tree or one git revision."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str        # project-relative POSIX path
    sha256: str
    data: bytes
    identity: str    # what the path ultimately names (resolved symlinks)
    is_link: bool


class SourceError(Exception):
    """The requested source (directory or revision) cannot be read."""


def _wanted(config: Config, name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in config.include)


class WorktreeSource:
    """The saved working tree, including untracked files; symlinks inside the project are followed once.
    A symlink leading out of the project or an unreadable file is skipped and reported, never silently lost."""

    label = "worktree"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.root = config.project_root.resolve()
        self.problems: list[tuple[str, str]] = []  # (path, why it was not indexed)

    def files(self) -> dict[str, SourceFile]:
        found: dict[str, SourceFile] = {}
        self.problems = []
        for scan_root in self.config.scan_roots:
            start = self.root / scan_root
            if start.is_dir():
                self._walk(start, found)
        return found

    def _walk(self, start: Path, found: dict[str, SourceFile]) -> None:
        seen_dirs: set[str] = set()
        def unreadable(error: OSError) -> None:
            self.problems.append((Path(error.filename).relative_to(self.root).as_posix(), f"unreadable directory: {error.strerror}"))

        for dirpath, dirnames, filenames in os.walk(start, followlinks=True, onerror=unreadable):
            real = os.path.realpath(dirpath)
            if real in seen_dirs:
                dirnames[:] = []
                continue
            seen_dirs.add(real)
            kept = []
            for name in sorted(d for d in dirnames if d not in self.config.skip_dirs):
                if self._inside(Path(dirpath) / name):
                    kept.append(name)
                else:
                    self.problems.append(((Path(dirpath) / name).relative_to(self.root).as_posix(), "directory symlink leads outside the project"))
            dirnames[:] = kept
            for name in sorted(filenames):
                if not _wanted(self.config, name):
                    continue
                full = Path(dirpath) / name
                rel = full.relative_to(self.root).as_posix()
                if not self._inside(full):
                    self.problems.append((rel, "symlink leads outside the project"))
                    continue
                try:
                    data = full.read_bytes()
                except OSError as error:
                    self.problems.append((rel, f"unreadable: {error.strerror or error}"))
                    continue
                identity = Path(os.path.realpath(full)).relative_to(self.root).as_posix()
                found[rel] = SourceFile(rel, hashlib.sha256(data).hexdigest(), data, identity, identity != rel)

    def _inside(self, path: Path) -> bool:
        return Path(os.path.realpath(path)).is_relative_to(self.root)


def run_git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise SourceError(f"git {' '.join(args)}: {getattr(error, 'stderr', b'').decode(errors='replace').strip() or error}") from error


class GitRevisionSource:
    """The tracked files of one commit: immutable, so its index never needs re-verification."""

    def __init__(self, config: Config, revision: str) -> None:
        self.config = config
        self.root = config.project_root.resolve()
        self.commit = run_git(self.root, "rev-parse", "--verify", f"{revision}^{{commit}}").decode().strip()
        self.problems: list[tuple[str, str]] = []
        self.label = f"commit:{self.commit[:12]}"

    def files(self) -> dict[str, SourceFile]:
        listing = run_git(self.root, "ls-tree", "-r", "-z", self.commit, "--", *self.config.scan_roots)
        entries = []
        for record in listing.split(b"\0"):
            if not record:
                continue
            meta, path = record.split(b"\t", 1)
            mode, kind, sha = meta.split()
            name = path.decode()
            if kind == b"blob" and _wanted(self.config, name.rsplit("/", 1)[-1]):
                entries.append((name, mode.decode(), sha.decode()))
        blobs = self._read_blobs([sha for _, _, sha in entries])
        targets: dict[str, tuple[str, str]] = {}  # symlink path -> (target path, target blob sha)
        for name, mode, sha in entries:
            if mode == "120000":  # symlink: the blob holds the target path
                target = os.path.normpath(os.path.join(os.path.dirname(name), blobs[sha].decode())).replace(os.sep, "/")
                targets[name] = (target, self._blob_of(target))
        missing = [sha for _, sha in targets.values() if sha and sha not in blobs]
        blobs.update(self._read_blobs(missing))
        found: dict[str, SourceFile] = {}
        for name, _mode, sha in entries:
            identity, data = name, blobs[sha]
            if name in targets:
                identity, target_sha = targets[name]
                data = blobs.get(target_sha, b"")
            found[name] = SourceFile(name, hashlib.sha256(data).hexdigest(), data, identity, identity != name)
        return found

    def _blob_of(self, path: str) -> str:
        out = run_git(self.root, "ls-tree", self.commit, "--", path).decode().split()
        return out[2] if len(out) >= 3 else ""

    def _read_blobs(self, shas: list[str]) -> dict[str, bytes]:
        if not shas:
            return {}
        output = run_git(self.root, "cat-file", "--batch", data=("\n".join(shas) + "\n").encode())
        blobs, position = {}, 0
        for _ in shas:
            header_end = output.index(b"\n", position)
            sha, _kind, size = output[position:header_end].decode().split()
            start = header_end + 1
            blobs[sha] = output[start:start + int(size)]
            position = start + int(size) + 1
        return blobs
