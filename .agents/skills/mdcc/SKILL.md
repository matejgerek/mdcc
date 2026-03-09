---
name: mdcc
description: >
  Use this skill whenever working with mdcc — a deterministic Markdown compiler that turns
  plain-text .md files into reproducible PDF reports. Trigger this skill when the user wants to:
  create, write, or edit an mdcc document; compile or validate an mdcc file; debug a failed
  mdcc compilation; understand mdcc block types (mdcc_chart, mdcc_table); add charts or tables
  to a report; or understand caching, diagnostics, or compiler options. Use this skill any time
  the word "mdcc" appears or the user mentions writing a "report" or "analytical document" that
  should compile to PDF using this tool.
---

# mdcc Skill

`mdcc` compiles a single plain-text Markdown file — combining narrative, data tables, and charts — into a deterministic PDF report. It is designed for agents: easy to generate, modify, debug, and rerun automatically.

---

## Quick Reference

| Task | Command |
|---|---|
| Compile to PDF | `mdcc compile report.md` |
| Compile with explicit output | `mdcc compile report.md output/report.pdf` |
| Validate without compiling | `mdcc validate report.md` |
| Force fresh run (no cache) | `mdcc compile report.md --no-cache` |
| Debug a failed block | `mdcc compile report.md --verbose --keep-build-dir` |
| Increase block timeout | `mdcc compile report.md --timeout 60` |

---

## Document Structure

Every mdcc file has three parts in this order:

```
1. Frontmatter (optional YAML)
2. Markdown narrative (prose, headings, lists)
3. Executable blocks (mdcc_chart / mdcc_table) — interleaved anywhere in the narrative
```

### Frontmatter

```yaml
---
title: "Q3 Analysis Memo"
author: "AI Analyst"
date: "2024-01-15"
---
```

Supported fields: `title`, `author`, `date`. Unknown keys are silently ignored — stick to these three for predictable results.

---

## Executable Block Types

Each block runs in a **completely isolated Python process**. Blocks **cannot share state** — variables defined in block A are not visible in block B.

**Available automatically (no import needed):** `pd` (pandas), `np` (numpy), `alt` (altair)

**`import` statements are forbidden** inside blocks.

The **last expression** in the block is its output — no explicit render call needed.

### `mdcc_table` — renders a DataFrame as a table

The last expression must be a `pandas.DataFrame`.

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

### `mdcc_chart` — renders an Altair chart as a static image

The last expression must be an Altair chart object.

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

---

## Block Metadata Attributes

Add optional `caption` and `label` attributes to the fence header:

````markdown
```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
...
```
````

````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary"
...
```
````

**Rules:**
- Use `key="value"` form, separated by whitespace
- `caption` must not be empty
- `label` must match `^[A-Za-z][A-Za-z0-9:_-]*$`
- No duplicate or unknown keys — these will fail validation

---

## Cross-References

Reference labeled blocks in prose using `@label` syntax:

```markdown
The trend is visible in @fig:revenue-region.
Metrics are summarized in @tbl:regional-summary.
```

- `@fig:...` renders as `Figure N`
- `@tbl:...` renders as `Table N`
- Numbers are assigned per type in document order
- Unresolved or duplicate labels **fail validation**

---

## Caching

mdcc caches successful block results in `.mdcc_cache/` next to the source file. The cache is automatically invalidated when:
- The block's code changes
- A tracked local file changes (`open(...)`, `pd.read_csv(...)`, `pd.read_json(...)`, `pd.read_excel(...)`, `pd.read_parquet(...)`)

**What always re-runs regardless of cache:** document assembly, cross-reference resolution, PDF generation.

**Cache does NOT auto-invalidate for:** HTTP/network reads, environment variables, time/randomness.

Use `--no-cache` to force a full fresh run.

---

## Diagnosing Failures

When compilation fails, mdcc reports: file, block number, location, stage, and error message.

**Failure categories:**

| Category | Cause |
|---|---|
| `READ_ERROR` | Input file missing, empty, or unreadable |
| `PARSE_ERROR` | Malformed fences or broken frontmatter |
| `VALIDATION_ERROR` | Unknown block type, wrong output type (e.g. chart block returned a DataFrame), bad label/attribute syntax, unresolved `@references` |
| `EXECUTION_ERROR` | Runtime exception inside the block (e.g. `KeyError`, `NameError`) |
| `TIMEOUT_ERROR` | Block exceeded `--timeout` limit |
| `RENDERING_ERROR` | Valid output type but failed to render (e.g. invalid Altair encoding) |
| `PDF_ERROR` | HTML-to-PDF conversion failed |

**Add `--verbose` to get:**
- Exact exception class and message
- `stdout`/`stderr` from the failing block
- `expected` / `actual` type on validation mismatches
- Cache hit/miss status per block on successful compiles

**Debugging tip:** Use `print()` inside blocks freely — it never appears in the PDF, but shows up in `--verbose` diagnostics. Also use `--keep-build-dir` to inspect intermediate artifacts in `.mdcc_build/`.

**macOS WeasyPrint tip:** If PDF generation fails with missing external libraries, try `export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH` before `mdcc compile`.

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---|---|
| Using `import` inside a block | Remove it — `pd`, `np`, `alt` are pre-loaded |
| `mdcc_chart` block returns a DataFrame | Make sure the last expression is an Altair chart |
| `mdcc_table` block returns a chart or None | Make sure the last expression is a `pd.DataFrame` |
| Referencing a label that doesn't exist | Add a matching `label="..."` attribute to the block, or fix the `@ref` |
| Duplicate `label` values | Each label must be unique across the document |
| Empty `caption=""` | Either remove the attribute or provide a non-empty string |
| Expecting variables from one block in another | Blocks are isolated — recompute or re-load data in each block |
| Expecting `print()` output in the PDF | `print()` is diagnostics only; the last expression is the output |

---

## Complete Example Document

```markdown
---
title: "Sales Summary"
author: "AI Analyst"
date: "2024-06-01"
---

# Sales Summary

This report summarizes Q2 performance across regions.

Regional figures are shown in @tbl:regional-summary and trends in @fig:revenue-trend.

```mdcc_table caption="Regional summary" label="tbl:regional-summary"
df = pd.DataFrame({
    "Region": ["North", "South", "East", "West"],
    "Revenue": [120000, 95000, 110000, 87000],
    "Growth": ["12%", "8%", "15%", "5%"],
})
df
```

```mdcc_chart caption="Revenue by region" label="fig:revenue-trend"
data = pd.DataFrame({
    "Region": ["North", "South", "East", "West"],
    "Revenue": [120000, 95000, 110000, 87000],
})
alt.Chart(data).mark_bar().encode(
    x="Region:N",
    y="Revenue:Q",
    color="Region:N",
).properties(width=500, height=300)
```
```

---

## Out of Scope (MVP)

These are intentionally **not supported**:
- Shared state between blocks
- User `import` statements
- Interactive/dynamic charts
- Non-PDF outputs (HTML, Word, web)
- Compute-only blocks with no rendered output
