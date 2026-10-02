# Changelog

## 0.2.0 — 2026-10-03

- Write valid, complete JSON and CSV directly to stdout, without terminal markup or status lines.
- Apply `--sort-by` and make `--top` affect only table output.
- Use one directory walk with consistent `--max-depth` behavior and simpler progress display.
- Respect nested `.gitignore` and `.ignore` files, anchored rules, and negation. Add built-in ignores and `--no-default-ignores`.
- Count Dockerfile and Makefile, and count the final line even without a trailing newline.
- Document physical line counting accurately and add CLI regression tests and CI.

## 0.1.1

- Updated package metadata after the rename to codelines.
