# Contributing

Thanks for your interest in `immich-cli`!

> **Note:** This repository is currently **private** and contribution is by
> invitation only. The guidance below applies once the repo is opened up or
> you have been granted access.

## Getting started

```bash
uv sync
uv run pytest            # offline unit tests (XMP generation)
uv run ruff check src/   # lint
```

## Workflow

1. Create a branch off `main` (e.g. `feat/...`, `fix/...`).
2. Make your change with tests. Keep changes focused.
3. Run `make test` and `make lint` (or the `uv run` equivalents) before pushing.
4. Open a pull request against `main`. CI (lint + tests) must pass.

## Guidelines

- Python 3.12 only (`requires-python = ">=3.12,<3.13"`).
- Format/lint with `ruff` (config in `pyproject.toml`); match the existing style.
- Add or update unit tests for any behavior change. Keep the suite offline
  (no network calls in `tests/` — use `httpx.MockTransport` if needed).
- The XMP sidecar generator (`src/immich_cli/xmp.py`) is stdlib-only by design;
  do not introduce PyQt or other GUI dependencies.

## Reporting issues

Open an issue with a minimal reproduction. For upload problems, include the
command, the Immich server version, and (sanitized) metadata — never API keys.
