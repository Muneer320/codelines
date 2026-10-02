"""CLI entry point — argument parsing and orchestration."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from codelines import __version__
from codelines.config import DEFAULT_TOP_N, DEFAULT_WORKERS
from codelines.ignore import IgnoreMatcher
from codelines.scanner import CODE_FILENAMES, collect_files
from codelines.counter import count_lines
from codelines.reporters import format_output

console = Console()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the codelines CLI."""
    parser = argparse.ArgumentParser(
        prog="codelines",
        description="A blazing-fast, parallel Lines of Code counter with Rich terminal UI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  codelines .                        Count lines in current directory
  codelines ~/projects               Count lines in ~/projects
  codelines . --format json          Output as JSON
  codelines . --include .py .js      Only count Python and JavaScript
  codelines . --exclude .json .md    Skip JSON and Markdown files
  codelines . --max-depth 3          Limit to 3 directory levels
  codelines . --workers 8            Use 8 worker threads
  codelines . --sort-by ext --top 10 Show top 10 extensions
  codelines . --ignore-file .custom  Use .custom as additional ignore file
        """,
    )

    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )

    parser.add_argument(
        "--format", "-f",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )

    parser.add_argument(
        "--include", "-i",
        nargs="+",
        metavar="EXT",
        help="Only count files with these extensions (e.g., .py .js)",
    )

    parser.add_argument(
        "--exclude", "-e",
        nargs="+",
        metavar="EXT",
        help="Skip files with these extensions (e.g., .json .md)",
    )

    parser.add_argument(
        "--max-depth", "-d",
        type=int,
        default=None,
        metavar="N",
        help="Maximum directory depth to traverse",
    )

    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of worker threads (default: {DEFAULT_WORKERS})",
    )

    parser.add_argument(
        "--ignore-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Additional ignore file to use (beyond .gitignore and .ignore)",
    )

    parser.add_argument(
        "--no-default-ignores", action="store_true",
        help="Scan dependency and build directories unless ignored by a file",
    )

    parser.add_argument(
        "--sort-by", "-s",
        choices=["ext", "dir", "lines"],
        default="lines",
        help="Sort results by (default: lines)",
    )

    parser.add_argument(
        "--top", "-t",
        type=int,
        default=DEFAULT_TOP_N,
        metavar="N",
        help=f"Show top N results (default: {DEFAULT_TOP_N})",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress bars and live display",
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"codelines {__version__}",
    )

    return parser


def main(args: Optional[list] = None) -> int:
    """Main entry point for the codelines CLI.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = build_parser()
    opts = parser.parse_args(args)

    # Validate directory
    folder = Path(opts.directory).resolve()
    if not folder.is_dir():
        print(f"Error: '{opts.directory}' is not a valid directory", file=sys.stderr)
        return 1
    if opts.workers < 1 or opts.top < 1 or (opts.max_depth is not None and opts.max_depth < 0):
        print("Error: workers and top must be positive; max-depth must be nonnegative", file=sys.stderr)
        return 1

    # Normalize extensions (add leading dot if missing)
    def normalized(value: str) -> str:
        value = value.lower()
        return value if value in CODE_FILENAMES or value.startswith(".") else f".{value}"

    include_exts = None
    if opts.include:
        include_exts = {normalized(ext) for ext in opts.include}

    exclude_exts = None
    if opts.exclude:
        exclude_exts = {normalized(ext) for ext in opts.exclude}

    # Load ignore patterns
    extra = None
    if opts.ignore_file:
        extra = Path(opts.ignore_file)
        if not extra.is_absolute():
            extra = folder / extra
        if not extra.is_file():
            print(f"Error: ignore file does not exist: {extra}", file=sys.stderr)
            return 1
    ignore_patterns = IgnoreMatcher(folder, defaults=not opts.no_default_ignores, extra_file=extra)

    verbose = not opts.quiet and opts.format == "table"

    if verbose:
        console.rule("[bold blue]codelines")
        console.print(f"Scanning: {folder}")
        if include_exts:
            console.print(f"[dim]Including only: {', '.join(sorted(include_exts))}[/dim]")
        if exclude_exts:
            console.print(f"[dim]Excluding: {', '.join(sorted(exclude_exts))}[/dim]")
        if opts.max_depth is not None:
            console.print(f"[dim]Max depth: {opts.max_depth}[/dim]")
        console.print()

    # Step 1: Collect files
    files, skipped_dirs, skipped_files = collect_files(
        folder,
        ignore_patterns,
        include_exts=include_exts,
        exclude_exts=exclude_exts,
        max_depth=opts.max_depth,
        verbose=verbose,
    )

    if verbose:
        console.print(f"[green][FILES][/green] {len(files)} collected")
        console.print(f"[red][SKIPPED DIRS][/red] {len(skipped_dirs)}")
        console.print(f"[red][SKIPPED FILES][/red] {skipped_files}")
        if skipped_dirs:
            console.print("[bold red]Ignored Directories:[/bold red]")
            for d in skipped_dirs[:10]:
                console.print(f"   [dim]- {d}[/dim]")
            if len(skipped_dirs) > 10:
                console.print(f"   [dim]... and {len(skipped_dirs) - 10} more[/dim]")
        console.print()

    if verbose and not files:
        console.print("[yellow]No files found to count.[/yellow]")
    if verbose and files:
        console.print(f"[magenta][THREADS][/magenta] Using {opts.workers} workers")
        console.print()

    # Step 2: Count lines
    total_lines, ext_stats, dir_stats = count_lines(
        files,
        workers=opts.workers,
        verbose=verbose,
    )

    # Step 3: Format output
    output = format_output(
        fmt=opts.format,
        total_lines=total_lines,
        total_files=len(files),
        workers=opts.workers,
        skipped_dirs=len(skipped_dirs),
        skipped_files=skipped_files,
        ext_stats=ext_stats,
        dir_stats=dir_stats,
        top=opts.top,
        sort_by=opts.sort_by,
    )

    if output:
        if opts.format in {"json", "csv"} and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    if verbose:
        console.rule("[bold green]DONE")

    return 0


if __name__ == "__main__":
    sys.exit(main())
