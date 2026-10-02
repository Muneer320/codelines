# codelines

[![PyPI](https://img.shields.io/pypi/v/codelines)](https://pypi.org/project/codelines/)
[![Python](https://img.shields.io/pypi/pyversions/codelines)](https://pypi.org/project/codelines/)
[![CI](https://github.com/Muneer320/codelines/actions/workflows/ci.yml/badge.svg)](https://github.com/Muneer320/codelines/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Count physical lines in recognized source and text files, grouped by extension and directory. The count includes blank lines and comments. Files without a final newline still count their last line; files containing NUL bytes are treated as binary and contribute zero lines.

## Install

Python 3.9 or newer is required.

```bash
python -m pip install codelines
codelines --version
```

## Use

```bash
codelines .
codelines . --format json > count.json
codelines . --format csv > count.csv
codelines . --include .py .rs --max-depth 2
codelines . --sort-by ext --top 10
codelines . --no-default-ignores
```

The table is for terminal reading. JSON and CSV contain every extension and directory, regardless of `--top`, and write only the result to stdout. `--quiet` suppresses status and progress while keeping the report. Errors go to stderr.

`--max-depth 0` scans root files; depth 1 also scans direct child directories. `--sort-by lines` orders each group by descending line count. `--sort-by ext` orders extensions alphabetically; `--sort-by dir` orders directories alphabetically. `--top` limits only table rows.

The scanner reads `.gitignore` and `.ignore` in the root and nested directories, with Git-style negation and anchored patterns. It skips common dependency, cache, build and VCS directories by default, including `node_modules`, `.venv`, `__pycache__`, `dist` and `.git`. Use `--no-default-ignores` to disable that built-in list; ignore files still apply. `--ignore-file PATH` adds another ignore file.

Known extensions include Python, JavaScript, TypeScript, Rust, Go, Java, HTML, CSS, JSON, Markdown and YAML. Files named `Dockerfile`, `Makefile` and `CMakeLists.txt` are also counted. `--include` and `--exclude` filter by extension; `--include` can also name a recognized filename.

## Library use

```python
from pathlib import Path
from codelines.ignore import IgnoreMatcher
from codelines.scanner import collect_files
from codelines.counter import count_lines

root = Path(".").resolve()
files, skipped_dirs, skipped_files = collect_files(root, IgnoreMatcher(root))
total, by_extension, by_directory = count_lines(files)
```

Library functions do not print progress unless `verbose=True` is passed.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
