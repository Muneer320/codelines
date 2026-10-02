"""Single-pass file discovery with depth and Git-style ignore rules."""

import os
from pathlib import Path
from typing import List, Optional, Set, Tuple, Union

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codelines.config import CODE_EXTENSIONS
from codelines.ignore import IgnoreMatcher, should_ignore


CODE_FILENAMES = {"dockerfile", "makefile", "cmakelists.txt"}


def collect_files(
    folder: Path,
    ignore_patterns: Union[Set[str], IgnoreMatcher],
    include_exts: Optional[Set[str]] = None,
    exclude_exts: Optional[Set[str]] = None,
    max_depth: Optional[int] = None,
    verbose: bool = False,
) -> Tuple[List[Path], List[str], int]:
    """Return matching files, pruned directories and skipped file count.

    Depth zero includes root files, depth one includes files in direct children.
    """
    folder = folder.resolve()
    files: List[Path] = []
    skipped_dirs: List[str] = []
    skipped_files = 0

    def ignored(path: Path) -> bool:
        if isinstance(ignore_patterns, IgnoreMatcher):
            return ignore_patterns.matches(path)
        return should_ignore(path, ignore_patterns)

    def walk(progress=None, task=None) -> None:
        nonlocal skipped_files
        for root, dirs, names in os.walk(folder):
            root_path = Path(root)
            depth = len(root_path.relative_to(folder).parts)
            if isinstance(ignore_patterns, IgnoreMatcher) and root_path != folder:
                ignore_patterns.add_directory(root_path)
            if max_depth is not None and depth >= max_depth:
                dirs.clear()
            else:
                kept = []
                for name in dirs:
                    child = root_path / name
                    if ignored(child):
                        skipped_dirs.append(str(child))
                    else:
                        kept.append(name)
                dirs[:] = kept
            for name in names:
                file = root_path / name
                ext = file.suffix.lower()
                recognized = ext in CODE_EXTENSIONS or file.name.lower() in CODE_FILENAMES
                if include_exts is not None:
                    recognized = ext in include_exts or file.name.lower() in include_exts
                if (not ignored(file) and recognized
                        and (exclude_exts is None or
                             (ext not in exclude_exts and file.name.lower() not in exclude_exts))):
                    files.append(file)
                else:
                    skipped_files += 1
            if progress is not None:
                progress.update(task, advance=1)

    if verbose:
        with Progress(SpinnerColumn(), TextColumn("Scanning {task.completed} directories"),
                      console=Console(stderr=True)) as progress:
            task = progress.add_task("Scanning", total=None)
            walk(progress, task)
    else:
        walk()
    return files, skipped_dirs, skipped_files
