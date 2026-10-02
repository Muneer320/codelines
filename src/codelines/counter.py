"""Parallel line counter — counts lines in files using thread pools."""

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from codelines.config import CHUNK_SIZE, DEFAULT_WORKERS

def fast_count(file_path: Path) -> int:
    """Count newlines in a file using chunked binary reading.

    Args:
        file_path: Path to the file.

    Returns:
        Number of lines in the file, or 0 on error.
    """
    try:
        with file_path.open("rb") as f:
            lines = 0
            last_byte = b""
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                if b"\x00" in chunk:
                    return 0
                lines += chunk.count(b"\n")
                last_byte = chunk[-1:]
            return lines + int(bool(last_byte) and last_byte != b"\n")
    except (OSError, PermissionError, UnicodeError):
        return 0


def count_lines(
    files: List[Path],
    workers: Optional[int] = None,
    verbose: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[int, Dict[str, int], Dict[str, int]]:
    """Count lines in a list of files using parallel workers.

    Args:
        files: List of file paths to count.
        workers: Number of worker threads (default: CPU count × 2, capped at 32).
        verbose: Show progress bars and live display.
        progress_callback: Optional callback(completed, total) for external tracking.

    Returns:
        Tuple of (total_lines, ext_stats, dir_stats).
        - ext_stats: dict mapping file extension → total lines
        - dir_stats: dict mapping directory → total lines
    """
    if workers is None:
        workers = DEFAULT_WORKERS

    total = 0
    ext_stats: Dict[str, int] = defaultdict(int)
    dir_stats: Dict[str, int] = defaultdict(int)

    if not files:
        return total, dict(ext_stats), dict(dir_stats)

    def run(progress=None, task=None) -> None:
        nonlocal total
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fast_count, f): f for f in files}
            for completed, future in enumerate(as_completed(futures), start=1):
                file = futures[future]
                lines = future.result()
                total += lines
                if lines > 0:
                    ext_stats[file.suffix.lower() or "(no ext)"] += lines
                    dir_stats[str(file.parent)] += lines
                if progress is not None:
                    progress.update(task, advance=1)
                if progress_callback:
                    progress_callback(completed, len(files))

    if verbose:
        with Progress(SpinnerColumn(), TextColumn("Counting {task.completed}/{task.total} files"),
                      console=Console(stderr=True)) as progress:
            task = progress.add_task("Counting", total=len(files))
            run(progress, task)
    else:
        run()

    return total, dict(ext_stats), dict(dir_stats)
