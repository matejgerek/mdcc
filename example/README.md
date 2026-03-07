# Example Bundle

This folder contains a complete file-backed `mdcc` example:

- `example.md`: the source document for a baseline company report
- `apple_analysis.mdcc`: an advanced report featuring real-time financial data fetching
- `data/market-data.json`: monthly market metrics
- `data/region-targets.csv`: region-level target data

The examples demonstrate phase-1 block metadata support (using `caption="..."` and `label="..."` attributes) and live network-based data loading.

## How to Run

From the repository root:

```bash
cd /Users/matejgerek/Development/mdcc
source ~/.zshrc
uv run mdcc compile example/example.md --verbose
```

That writes the output PDF to:

```text
example/example.pdf
```

If you want to inspect all intermediate build artifacts:

```bash
uv run mdcc compile example/example.md --keep-build-dir --verbose
```

That keeps:

```text
example/.mdcc_build/
```

## What Happens During Compile

When `mdcc compile example/example.md` runs, the compiler executes these stages
in order:

1. Reads `example/example.md` and parses its frontmatter and Markdown content.
2. Detects each `mdcc_chart` and `mdcc_table` fenced block.
3. Validates the document structure before any execution starts.
4. Creates an isolated execution payload for each executable block.
5. Runs each block in its own Python process, top to bottom.
6. In each block, the code reads `data/market-data.json` or
   `data/region-targets.csv` from disk using `pandas`.
7. Validates the final expression result:
   chart blocks must return an Altair chart and table blocks must return a
   `pandas.DataFrame`.
8. Renders charts and tables into intermediate artifacts.
9. Combines the rendered artifacts with the narrative Markdown into HTML.
10. Generates the final PDF.

## Important Behavior

- Blocks do not share Python variables or state.
- Each block must reload the files it needs.
- User-written `import` statements are not allowed inside executable blocks.
- The runtime already provides `pd`, `np`, and `alt`.

## Useful Variations

Write the PDF somewhere else:

```bash
uv run mdcc compile example/example.md /tmp/example-report.pdf --verbose
```

Preserve build artifacts for debugging:

```bash
uv run mdcc compile example/example.md --keep-build-dir --verbose
```

## Advanced Example: Apple Q1 2026 Analysis

The `apple_analysis.mdcc` file provides a more complex real-world scenario. Unlike the basic example which uses local JSON/CSV files, this report:
- Fetches real-time financial data using `pd.read_csv` from external stock market APIs.
- Uses **Multiple Block Types** (including `mdcc_table` for financials and `mdcc_chart` for revenue and pricing trends).
- Demonstrates **Cross-Referencing** with internal figure and table labels (e.g., `@fig:historical-price`).

### High-Level Generation Prompt
This report was generated using a single high-level prompt:
> "Generate a comprehensive `mdcc` document for Apple's fiscal Q1 2026 performance. It should include an executive summary, a financial metrics table, a segmented revenue bar chart, and a historical stock price trend section that fetches live daily closing data from an external API."
