"""Tests for codelines package."""

import json
import tempfile
from pathlib import Path

import pytest

from codelines.ignore import IgnoreMatcher, load_ignore_patterns, should_ignore
from codelines.counter import fast_count, count_lines
from codelines.scanner import collect_files
from codelines.reporters import format_output, top_n
from codelines.cli import build_parser, main


# ── ignore tests ──────────────────────────────────────────────────────

class TestIgnore:
    def test_load_empty_when_file_missing(self):
        patterns = load_ignore_patterns(Path("/nonexistent/.gitignore"))
        assert patterns == set()

    def test_load_patterns(self, tmp_path: Path):
        ignore_file = tmp_path / ".gitignore"
        ignore_file.write_text("node_modules/\n.git/\n*.pyc\n# comment\n\nbuild/")
        patterns = load_ignore_patterns(ignore_file)
        assert "node_modules" in patterns
        assert ".git" in patterns
        assert "*.pyc" in patterns
        assert "build" in patterns
        assert "# comment" not in patterns

    def test_should_ignore_by_dir_name(self):
        patterns = {"node_modules"}
        assert should_ignore(Path("project/node_modules/foo.js"), patterns)
        assert not should_ignore(Path("project/src/main.js"), patterns)

    def test_should_ignore_by_pattern(self):
        patterns = {"*.pyc"}
        assert should_ignore(Path("main.pyc"), patterns)
        assert not should_ignore(Path("main.py"), patterns)

    def test_should_ignore_empty_patterns(self):
        assert not should_ignore(Path("anything.js"), set())


# ── counter tests ─────────────────────────────────────────────────────

class TestCounter:
    def test_fast_count_small_file(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n")
        assert fast_count(f) == 3

    def test_fast_count_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert fast_count(f) == 0

    def test_fast_count_no_newline_eof(self, tmp_path: Path):
        f = tmp_path / "noeol.py"
        f.write_text("line1\nline2")  # no trailing newline
        assert fast_count(f) == 2  # the final unterminated line counts

    def test_fast_count_binary_file(self, tmp_path: Path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02")
        assert fast_count(f) == 0

    def test_fast_count_nonexistent(self):
        assert fast_count(Path("/nonexistent/file.py")) == 0

    def test_count_lines_parallel(self, tmp_path: Path):
        files = []
        for i in range(10):
            f = tmp_path / f"file{i}.py"
            f.write_text("a\n" * (i + 1))
            files.append(f)

        total, ext_stats, dir_stats = count_lines(files, workers=2, verbose=False)
        assert total == sum(range(1, 11))  # 55
        assert ext_stats[".py"] == 55
        assert str(tmp_path) in dir_stats

    def test_count_lines_empty_list(self):
        total, ext_stats, dir_stats = count_lines([], verbose=False)
        assert total == 0
        assert ext_stats == {}
        assert dir_stats == {}


# ── scanner tests ─────────────────────────────────────────────────────

class TestScanner:
    def test_collect_files_basic(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("hello")
        (tmp_path / "readme.md").write_text("docs")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "image.png").write_text("fake")

        files, skipped, skipped_files = collect_files(
            tmp_path, set(), verbose=False
        )
        suffixes = {f.suffix for f in files}
        assert ".py" in suffixes
        assert ".md" in suffixes
        assert ".json" in suffixes
        assert ".png" not in suffixes  # not in CODE_EXTENSIONS

    def test_collect_files_with_ignore(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("code")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("code")
        (tmp_path / ".gitignore").write_text("node_modules/")

        patterns = load_ignore_patterns(tmp_path / ".gitignore")
        files, skipped, _ = collect_files(tmp_path, patterns, verbose=False)

        paths = [str(f) for f in files]
        assert any("main.py" in p for p in paths)
        assert not any("node_modules" in p for p in paths)

    def test_collect_files_include_exts(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("code")
        (tmp_path / "lib.js").write_text("code")
        (tmp_path / "readme.md").write_text("docs")

        files, _, _ = collect_files(
            tmp_path, set(), include_exts={".py"}, verbose=False
        )
        suffixes = {f.suffix for f in files}
        assert suffixes == {".py"}

    def test_collect_files_exclude_exts(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("code")
        (tmp_path / "data.json").write_text("{}")

        files, _, _ = collect_files(
            tmp_path, set(), exclude_exts={".json"}, verbose=False
        )
        suffixes = {f.suffix for f in files}
        assert suffixes == {".py"}

    def test_collect_files_max_depth(self, tmp_path: Path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "c").mkdir()
        (tmp_path / "a" / "foo.py").write_text("code")
        (tmp_path / "a" / "b" / "bar.py").write_text("code")
        (tmp_path / "a" / "b" / "c" / "baz.py").write_text("code")

        files, _, _ = collect_files(tmp_path, set(), max_depth=2, verbose=False)

        assert len(files) == 2  # only foo.py and bar.py (depth 1 and 2)

    def test_depth_is_same_with_progress_and_quiet(self, tmp_path: Path):
        (tmp_path / "one").mkdir()
        (tmp_path / "one" / "two").mkdir()
        for file in (tmp_path / "root.py", tmp_path / "one" / "first.py",
                     tmp_path / "one" / "two" / "second.py"):
            file.write_text("x")
        quiet = collect_files(tmp_path, IgnoreMatcher(tmp_path), max_depth=1, verbose=False)[0]
        shown = collect_files(tmp_path, IgnoreMatcher(tmp_path), max_depth=1, verbose=True)[0]
        assert {f.name for f in quiet} == {f.name for f in shown} == {"root.py", "first.py"}

    def test_nested_ignores_defaults_and_filenames(self, tmp_path: Path):
        (tmp_path / ".gitignore").write_text("*.py\n/root-only.md\n")
        (tmp_path / "root-only.md").write_text("x")
        (tmp_path / "child").mkdir()
        (tmp_path / "child" / ".gitignore").write_text("!keep.py\n")
        (tmp_path / "child" / "keep.py").write_text("x")
        (tmp_path / "child" / "drop.py").write_text("x")
        (tmp_path / "child" / "other.md").write_text("x")
        (tmp_path / "Dockerfile").write_text("FROM scratch")
        (tmp_path / "Makefile").write_text("all:")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("x")
        files, _, _ = collect_files(tmp_path, IgnoreMatcher(tmp_path))
        assert {f.name for f in files} == {"keep.py", "other.md", "Dockerfile", "Makefile"}
        all_files, _, _ = collect_files(tmp_path, IgnoreMatcher(tmp_path, defaults=False))
        assert "lib.js" in {f.name for f in all_files}


# ── reporters tests ───────────────────────────────────────────────────

class TestReporters:
    def test_top_n(self):
        d = {"a": 10, "b": 5, "c": 20, "d": 1}
        result = top_n(d, n=2)
        assert result == [("c", 20), ("a", 10)]

    def test_format_json(self, tmp_path: Path):
        output = format_output(
            fmt="json",
            total_lines=100,
            total_files=10,
            workers=8,
            skipped_dirs=2,
            skipped_files=5,
            ext_stats={".py": 60, ".js": 40},
            dir_stats={"/src": 100},
            top=5,
        )
        data = json.loads(output)
        assert data["summary"]["total_lines"] == 100
        assert data["summary"]["total_files"] == 10
        assert data["by_extension"][".py"] == 60

    def test_format_csv(self):
        output = format_output(
            fmt="csv",
            total_lines=42,
            total_files=3,
            workers=4,
            skipped_dirs=0,
            skipped_files=1,
            ext_stats={".py": 42},
            dir_stats={"/tmp": 42},
            top=5,
        )
        assert "summary,total_lines,42" in output
        assert "by_extension,.py,42" in output

    def test_format_table(self):
        output = format_output(
            fmt="table",
            total_lines=100,
            total_files=5,
            workers=8,
            skipped_dirs=1,
            skipped_files=2,
            ext_stats={".py": 100},
            dir_stats={"/test": 100},
            top=5,
        )
        # Table format prints to console, returns empty string
        assert output == ""

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_machine_formats_include_all_rows(self, fmt):
        output = format_output(fmt=fmt, total_lines=6, total_files=3, workers=2,
                               skipped_dirs=0, skipped_files=0,
                               ext_stats={".a": 1, ".b": 2, ".c": 3},
                               dir_stats={"a": 1, "b": 2, "c": 3}, top=1, sort_by="ext")
        assert all(ext in output for ext in (".a", ".b", ".c"))
        if fmt == "json":
            assert list(json.loads(output)["by_extension"]) == [".a", ".b", ".c"]

    def test_sort_options(self):
        kwargs = dict(fmt="json", total_lines=9, total_files=3, workers=2,
                      skipped_dirs=0, skipped_files=0,
                      ext_stats={".z": 8, ".a": 1}, dir_stats={"z": 8, "a": 1}, top=1)
        assert list(json.loads(format_output(**kwargs, sort_by="lines"))["by_extension"]) == [".z", ".a"]
        assert list(json.loads(format_output(**kwargs, sort_by="ext"))["by_extension"]) == [".a", ".z"]
        assert list(json.loads(format_output(**kwargs, sort_by="dir"))["by_directory"]) == ["a", "z"]


# ── CLI tests ─────────────────────────────────────────────────────────

class TestCLI:
    def test_parser_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["."])
        assert args.directory == "."
        assert args.format == "table"

    def test_parser_format(self):
        parser = build_parser()
        args = parser.parse_args([".", "--format", "json"])
        assert args.format == "json"

    def test_parser_include(self):
        parser = build_parser()
        args = parser.parse_args([".", "--include", ".py", ".js"])
        assert args.include == [".py", ".js"]

    def test_parser_max_depth(self):
        parser = build_parser()
        args = parser.parse_args([".", "--max-depth", "3"])
        assert args.max_depth == 3

    def test_parser_quiet(self):
        parser = build_parser()
        args = parser.parse_args([".", "--quiet"])
        assert args.quiet is True

    def test_parser_version(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--version"])

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_machine_stdout_has_no_banner_or_wrapping(self, tmp_path: Path, capsys, fmt):
        nested = tmp_path / ("long-[brackets]-" * 8)
        nested.mkdir()
        (nested / "example.py").write_text("one\ntwo")
        assert main([str(tmp_path), "--format", fmt]) == 0
        output = capsys.readouterr().out
        assert "FAST LOC SCANNER" not in output
        if fmt == "json":
            data = json.loads(output)
            assert data["summary"]["total_lines"] == 2
            assert str(nested) in data["by_directory"]
        else:
            assert str(nested) in output

    def test_empty_json_is_valid(self, tmp_path: Path, capsys):
        assert main([str(tmp_path), "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["summary"]["total_files"] == 0
