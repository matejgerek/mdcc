# AGENTS.md

## Project Context

- This repository is `mdcc`, a Python project managed with `uv`.
- Prefer `uv run ...` for project commands and `uv add ...` for dependency changes.
- Source code lives in `src/mdcc/`.
- Tests live in `tests/`.
- Project documentation lives in `docs/`.

## Key Docs

- Read [`docs/SPEC.md`](/Users/matejgerek/Development/mdcc/docs/SPEC.md) for product behavior and expected features.
- Read [`docs/ARCHITECTURE.md`](/Users/matejgerek/Development/mdcc/docs/ARCHITECTURE.md) for system structure and design decisions.
- Read [`docs/DIAGNOSTICS.md`](/Users/matejgerek/Development/mdcc/docs/DIAGNOSTICS.md) for error and diagnostic expectations.
- Read [`docs/TASKS.md`](/Users/matejgerek/Development/mdcc/docs/TASKS.md) for current implementation scope and priorities.

## Working Rules

- Use Python 3.12+ features only when they fit the existing codebase.
- Keep changes consistent with the patterns already used in `src/mdcc/` and `tests/`.
- Avoid introducing new tooling when the existing `uv` + `ruff` + `mypy` + `pytest` workflow already covers the task.
- If dependencies must change, update `pyproject.toml` and the lockfile via `uv`.

## Verification

- Run the full verification sequence when changes affect Python code, packaging, runtime behavior, or tests.
- For documentation-only changes (for example `README.md`, `docs/`, `AGENTS.md`) or other clearly non-functional edits, full verification is not required unless the change could affect generated output or developer workflow in a way that should be validated.
- When full verification is required, run formatting before finishing:
  - `uv run ruff format .`
- After formatting, run typechecking and linting:
  - `uv run ruff check .`
  - `uv run mypy src tests`
- Run tests before considering the task complete:
  - `uv run pytest`
- If a required command fails, fix the issue or clearly report the blocker and the failing command.
