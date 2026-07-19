# Convenience wrapper for the immich-cli project.
# Common tasks: install, test, lint, run.
#
# Usage:
#   make install      # uv sync (create .venv, install deps)
#   make test         # run the offline unit tests
#   make lint         # ruff check src/
#   make format       # ruff format src/  (if enabled)
#   make run-help     # show the CLI help
#   make clean        # remove caches / build artifacts

UV ?= uv

.PHONY: install test lint format run-help clean

install:
	$(UV) sync

test:
	$(UV) run pytest -q

lint:
	$(UV) run ruff check src/ tests/

format:
	$(UV) run ruff format src/ tests/

run-help:
	$(UV) run immich-cli --help

clean:
	rm -rf .ruff_cache .pytest_cache build dist
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
