"""Git-style ignore rules, including rules in nested directories."""

from pathlib import Path
from typing import Dict, List, Optional, Set

from pathspec import GitIgnoreSpec


DEFAULT_IGNORES = (
    ".git/", ".hg/", ".svn/", "node_modules/", ".venv/", "venv/",
    "__pycache__/", ".mypy_cache/", ".pytest_cache/", ".tox/",
    "dist/", "build/", ".next/", "coverage/",
)


def load_ignore_patterns(ignore_file: Path) -> Set[str]:
    """Compatibility helper for callers that supply a simple pattern set."""
    if not ignore_file.is_file():
        return set()
    return {
        line.strip().rstrip("/")
        for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def should_ignore(path: Path, ignore_patterns: Set[str]) -> bool:
    """Match a simple pattern set; use IgnoreMatcher for nested rules."""
    if not ignore_patterns:
        return False
    return GitIgnoreSpec.from_lines(sorted(ignore_patterns)).match_file(path.as_posix())


class IgnoreMatcher:
    """Apply each ignore file relative to its directory, in ancestor order."""

    def __init__(self, root: Path, defaults: bool = True, extra_file: Optional[Path] = None):
        self.root = root.resolve()
        self.rules: Dict[Path, List[GitIgnoreSpec]] = {}
        self._loaded_directories: Set[Path] = set()
        if defaults:
            self.rules.setdefault(self.root, []).append(GitIgnoreSpec.from_lines(DEFAULT_IGNORES))
        self.add_directory(self.root)
        if extra_file is not None:
            self._add_file(self.root, extra_file)

    def _add_file(self, base: Path, file: Path) -> None:
        if file.is_file():
            lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
            self.rules.setdefault(base, []).append(GitIgnoreSpec.from_lines(lines))

    def add_directory(self, directory: Path) -> None:
        if directory in self._loaded_directories:
            return
        self._loaded_directories.add(directory)
        for name in (".gitignore", ".ignore"):
            self._add_file(directory, directory / name)

    def matches(self, path: Path) -> bool:
        ignored = False
        try:
            path.relative_to(self.root)
        except ValueError:
            return False
        bases = []
        is_dir = path.is_dir()
        base = path if is_dir else path.parent
        while True:
            bases.append(base)
            if base == self.root:
                break
            base = base.parent
        for base in reversed(bases):
            relative = path.relative_to(base).as_posix()
            if is_dir:
                relative += "/"
            for spec in self.rules.get(base, []):
                result = spec.check_file(relative)
                if result.include is not None:
                    ignored = bool(result.include)
        return ignored
