# mdcc

**mdcc** is a deterministic, agent-friendly compiler for executable Markdown reports.

It turns a single plain-text document — combining narrative text, data loading, tables, and charts — into a **reproducible PDF report**.

---

## Why mdcc?

Most analytical report tools carry hidden state, noisy formats, or complex publishing machinery. `mdcc` strips all of that out.

- **Agent-first design** — the format and runtime model are optimized for coding agents. Documents are easy to generate, modify, debug, and rerun automatically.
- **Single-file reproducible reports** — narrative, code, charts, and tables live in one Markdown file.
- **Deterministic execution** — each block runs in an isolated process, preventing hidden state and making results predictable.
- **Git-friendly** — plain Markdown keeps diffs clean, unlike the noisy JSON used by notebook systems.
- **Practical repeated compiles** — successful blocks are cached locally and invalidated when tracked inputs change.
- **Focused and minimal** — `mdcc` is purpose-built for analytical reports, not a general publishing system.

### Compared to Alternatives

| Tool | Limitation |
|---|---|
| Jupyter notebooks | Hidden state, JSON format, poor diffs |
| Quarto / RMarkdown | More complex publishing system |
| LaTeX + scripts | Harder data integration |
| BI tools / Excel | Not reproducible or automation-friendly |

`mdcc` sits in the middle: simple like Markdown, reproducible like notebooks, and designed for AI-driven workflows. See the [Design Principles](docs/DESIGN_PRINCIPLES.md) for more on our core philosophy.

---

## Installation

### System dependency

`mdcc` uses [WeasyPrint](https://weasyprint.org/) for PDF generation, which requires system-level libraries:

```bash
brew install weasyprint
```

> On Linux, install the equivalent packages for your distro (Pango, Cairo, etc.) — see the [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

### Install the package

Requires **Python 3.12+** and [uv](https://docs.astral.sh/uv/).

```bash
uv pip install -e .
```

Or install from source with pip:

```bash
pip install -e .
```

This installs the `mdcc` CLI command.

---

## Usage

```bash
mdcc compile <input_file> [output_file] [OPTIONS]
```

If `output_file` is omitted, the PDF is written next to the input file (e.g. `report.md` → `report.pdf`).

For a fast pre-execution document check, use:

```bash
mdcc validate <input_file>
```

### Options

| Option | Description |
|---|---|
| `--timeout`, `-t` | Per-block execution timeout in seconds (default: 30) |
| `--keep-build-dir` | Preserve the `.mdcc_build` intermediate directory after compilation |
| `--no-cache` | Disable the persistent per-block cache and force fresh execution |
| `--verbose`, `-v` | Show expanded diagnostic output on failure or success |

`mdcc` keeps a persistent `.mdcc_cache/` directory next to the source document. Cache entries are scoped to the source directory and invalidated when the block definition, runtime fingerprint, or tracked local file reads change. Use `--no-cache` when you want to bypass cached block results entirely.

### Example

```bash
mdcc compile example/example.md
```

---

## Source Format

An `mdcc` document is a plain Markdown file with three parts:

1. **Frontmatter** (optional) — YAML metadata at the top of the file.
2. **Markdown narrative** — standard prose, headings, lists, etc.
3. **Executable blocks** — fenced blocks tagged `mdcc_chart` or `mdcc_table`, interleaved anywhere in the narrative.

### Frontmatter

```yaml
---
title: "Q3 Analysis Memo"
author: "AI Analyst"
date: "2024-01-15"
---
```

### Executable Blocks

Each block runs in its own isolated Python process. The packages `pandas` (as `pd`), `numpy` (as `np`), and `altair` (as `alt`) are available automatically. User `import` statements are not allowed.

Phase 1 caching tracks common local file reads during execution, including `open(...)` and common pandas readers such as `pd.read_csv(...)`. This keeps repeated compiles fast for reports that read local data files. The cache does not guarantee correct invalidation for HTTP/network reads, environment variables, time/randomness, or other hidden ambient state.

The **last expression** in the block is the output — no explicit render calls needed.

Executable fences also support optional inline metadata attributes for rendering:

- `caption="..."` renders a caption with the block output
- `label="..."` assigns a stable block label for future references and HTML anchors

Example:

````markdown
```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
data = pd.read_csv("data/results.csv")
alt.Chart(data).mark_line().encode(
    x="month:N",
    y="revenue:Q",
    color="region:N",
)
```
````

Markdown prose can reference labeled blocks using `@label` syntax:

```markdown
The trend can be seen in @fig:revenue-region.
Metrics are summarized in @tbl:regional-summary.
```

#### `mdcc_table` — produces a DataFrame rendered as a table

````markdown
```mdcc_table
df = pd.DataFrame({
    "Category": ["A", "B", "C"],
    "Values": [10, 20, 30],
})
df["Doubled"] = df["Values"] * 2
df
```
````

#### `mdcc_chart` — produces an Altair chart rendered as a static image

````markdown
```mdcc_chart
data = pd.read_csv("data/results.csv")
alt.Chart(data).mark_line().encode(
    x="month:N",
    y="revenue:Q",
    color="region:N",
).properties(width=640, height=320)
```
````

> `print()` is allowed for debugging, but printed output never appears in the PDF — it goes to diagnostics only.

For the full format reference, see [`docs/SOURCE_FORMAT.md`](docs/SOURCE_FORMAT.md).

---

## Diagnostics

When compilation fails, `mdcc` reports the file, block number, location, failure stage, and error message. Use `--verbose` for expanded output including `stdout`/`stderr` from the failing block, type mismatch details, and cache hit/miss information during successful compiles.

Failure categories: `READ_ERROR`, `PARSE_ERROR`, `VALIDATION_ERROR`, `EXECUTION_ERROR`, `TIMEOUT_ERROR`, `RENDERING_ERROR`, `PDF_ERROR`.

---

## Docs

- [`docs/DESIGN_PRINCIPLES.md`](docs/DESIGN_PRINCIPLES.md) — core philosophy and design goals
- [`docs/SOURCE_FORMAT.md`](docs/SOURCE_FORMAT.md) — full source format reference
- [`docs/COMPILER_USAGE.md`](docs/COMPILER_USAGE.md) — compiler stages, options, and failure interpretation
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — internal architecture and module structure
- [`docs/features/MVP_SPEC.md`](docs/features/MVP_SPEC.md) — technical specification
- [`docs/DIAGNOSTICS.md`](docs/DIAGNOSTICS.md) — detailed error category reference
