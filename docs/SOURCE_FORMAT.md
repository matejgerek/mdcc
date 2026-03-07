# mdcc Supported Source Format

This document describes the supported source file format for the **mdcc** (Markdown Compiler) MVP. The compiler is designed to turn a single markdown-like file with embedded, typed Python execution blocks into a deterministic PDF report.

---

## 1. Document Structure

An `mdcc` document is a plain-text file combining standard markdown with executable blocks. The structure strictly follows this order:

1.  **(Optional) Frontmatter**: YAML-formatted document metadata at the very top.
2.  **Markdown Narrative**: Standard markdown text for your report body.
3.  **Executable Blocks**: Fenced, isolated execution blocks (`mdcc_chart` and `mdcc_table`) interleaved anywhere in the markdown narrative.

The compiler processes executable blocks **top-to-bottom in document order**, interleaves the rendered outputs with the narrative, and generates a single PDF.

---

## 2. Frontmatter Usage

Frontmatter is placed at the top of the file, fenced by `---`. It defines document-level metadata used during final rendering.

The MVP officially supports a minimal set of recommended fields:
- `title`: The report title.
- `author`: The author's name.
- `date`: The publication or generation date.

```yaml
---
title: "Q3 Analysis Memo"
author: "AI Analyst"
date: "2023-11-15"
---
```

> **Note**: Any unknown or unsupported keys included in the frontmatter may be silently ignored or preserved for future diagnostics, depending on implementation specifics. It is recommended to stick to the minimal supported fields for predictable results.

---

## 3. Supported Executable Block Types

The `mdcc` MVP specifically distances itself from generic notebook compute cells. It enforces **semantic executable blocks**. Each block type has a single, typed purpose, executes in complete isolation (its own separate Python process), and does **not** share state or imports with other blocks.

The MVP provides a fixed built-in Python runtime. The packages `pandas` (as `pd`), `numpy` (as `np`), and Altair are automatically available. **User-written `import` statements are strictly forbidden inside blocks.**

### 3.1 `mdcc_chart`
Used for generating data visualizations.
- **Environment**: Isolated Python process.
- **Built-in tools**: `pd`, `np`, Altair.
- **Expected Output**: An Altair chart object.

### 3.2 `mdcc_table`
Used for generating data tables.
- **Environment**: Isolated Python process.
- **Built-in tools**: `pd`, `np`.
- **Expected Output**: A `pandas.DataFrame`.

### 3.3 Block Metadata Attributes
Executable fence headers may include inline metadata attributes after the block type:

````text
```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
```
````

Phase 1 supports:
- `caption`: rendered with the block output
- `label`: preserved as block metadata and emitted as an HTML anchor/attribute

Rules:
- attributes must use `key="value"` form
- attributes must be separated by whitespace
- duplicate keys are invalid
- unknown keys are invalid
- `caption` must not be empty after trimming
- `label` must match `^[A-Za-z][A-Za-z0-9:_-]*$`

Examples:

````markdown
```mdcc_chart caption="Revenue by region"
alt.Chart(frame).mark_line().encode(x="month", y="revenue")
```
````

````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary"
summary_df
```
````

### 3.4 Cross References
Markdown prose can reference labeled blocks with `@label` syntax.

Examples:

```markdown
See @fig:revenue-region for details.
Metrics are summarized in @tbl:regional-summary.
```

Resolution rules:
- `@fig:...` references render as `Figure N`
- `@tbl:...` references render as `Table N`
- numbering is assigned per artifact type in document order
- only labeled chart/table blocks are referenceable
- unresolved references fail validation
- duplicate labels fail validation

---

## 4. Last-Expression Output Rules

You do **not** need to call explicit rendering functions like `render_chart(my_chart)`. Instead, `mdcc` uses a strict **last-expression output model**.

The captured output of your block is simply the value of the final expression evaluated in the code block.

### Contract Expectations
*   **For `mdcc_chart`**: The last expression **must** evaluate to an Altair chart object. If it evaluates to a string, a Pandas DataFrame, or `None`, the compiler will throw a typed validation error and stop.
*   **For `mdcc_table`**: The last expression **must** evaluate to a `pandas.DataFrame`.

### Example

````markdown
```mdcc_table
# 1. We use the pre-loaded pandas as `pd`
df = pd.DataFrame({
    "Category": ["A", "B", "C"],
    "Values": [10, 20, 30]
})

# 2. Add some logic
df["Doubled"] = df["Values"] * 2

# 3. Last expression is the dataframe itself
df
```
````

---

## 5. stdout / stderr vs. Rendered Output

It is critical to understand the separation between logs and document output:

*   **Rendered Document Output**: Driven completely by the last expression of the block (e.g., the Altair chart or DataFrame). This is what gets embedded into the final PDF.
*   **Execution Logs (stdout/stderr)**: You are free to use `print()` statements for debugging. However, **printed output does never appear in the PDF**. It is captured strictly for diagnostics, traces, and compiler error reporting.

---

## 6. What is Out of Scope in MVP?

The `mdcc` compiler makes opinionated tradeoffs to guarantee determinism and simple agentic interactions. The following are intentionally out of scope:

*   **Shared Notebook State**: Code executed in block A cannot access variables, dataframes, or functions defined in block B. Every block is an isolated universe.
*   **User Imports**: You cannot `import` new libraries; you must work within the provided runtime preview.
*   **Interactive Widgets / Charts**: The output targets static PDFs.
*   **HTML/Word/Web Outputs**: Only PDF output is supported in MVP.
*   **Arbitrary Code Execution / Layout formatting**: There are no "compute-only" hidden blocks, image-import blocks, or direct PDF layout manipulation blocks.
*   **Caching**: Re-compiling re-evaluates all blocks.

By stripping out advanced publishing layouts and shared-state side effects, `mdcc` retains high reliability for its primary audience: autonomous coding agents generating precise analytical documents.
