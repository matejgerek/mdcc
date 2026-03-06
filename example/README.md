# Example Bundle

This folder contains a complete file-backed `mdcc` example:

- `example.md`: the source document
- `data/market-data.json`: monthly market metrics
- `data/region-targets.csv`: region-level target data

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
