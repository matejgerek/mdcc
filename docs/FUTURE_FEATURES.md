# mdcc — Future Features & Extensions Analysis

> **"mdcc has a really clean core — the isolated-block, deterministic-pipeline, agent-first philosophy is a strong foundation. The best extensions are the ones that double down on those strengths rather than drifting toward 'Quarto lite'."**

A pragmatic, opinionated look at what would actually move the needle for `mdcc` — ordered roughly by **impact × alignment** with the existing philosophy.

---

## Tier 1 — High-Impact, Philosophy-Aligned

These stay true to the narrow, deterministic, agent-first DNA and unlock real new use cases.

### 1. `mdcc_compute` — Silent Execution Blocks

**What:** A new block type that executes code but produces **no visible output** in the PDF. Its only side-effect is writing files to a well-defined scratch directory (e.g. `_build/shared/`).

**Why it matters:**
- The single biggest friction point in the "no shared state" model is data loading. If three blocks all need the same CSV, each one independently re-reads and re-parses it.
- `mdcc_compute` lets an early block do expensive prep (clean data, compute features) and write a parquet/CSV to disk, which later blocks can `pd.read_parquet(...)` from a known path.
- This is **explicit** file-based sharing — not implicit runtime state. It doesn't violate isolation at all.

**Complexity:** Low. You already have the executor infrastructure; this block type just skips the "validate typed output → render artifact" stages.

```markdown
```mdcc_compute
raw = pd.read_csv("data/raw_sales.csv")
clean = raw.dropna(subset=["revenue"]).query("revenue > 0")
clean.to_parquet("_build/shared/clean_sales.parquet")
```
```

---

### 2. Per-Block Caching

**What:** Hash each block's source + runtime version + input file fingerprints. If the hash matches a previously cached result, skip re-execution and reuse the rendered artifact.

**Why it matters:**
- Your spec already explicitly calls this out as a future-friendly design goal (§20).
- The isolated-process model makes this almost trivial — each block is a pure function of its inputs.
- For reports with 10+ blocks, re-execution on every compile is the dominant bottleneck.

**Design sketch:**
- Cache key: `sha256(block_source + runtime_version + compiler_version + referenced_file_mtimes)`
- Cache store: `.mdcc_cache/` directory with pickled results + rendered artifacts
- CLI flag: `--no-cache` to force fresh execution
- Invalidation: automatic when any component of the key changes

**Complexity:** Medium. The hard part is deciding what counts as an "input" — especially if blocks read external files.

---

### 3. Block Metadata (Captions, Labels, Width)

**What:** Allow optional YAML-style metadata on blocks for controlling presentation.

**Why it matters:**
- Your spec explicitly reserves room for this (§8.3).
- Agents generating reports need to label charts and tables — "Figure 1: Revenue by Region" is table-stakes for professional output.
- Width control is essential for charts that need to be side-by-side or narrow-column.

**Possible syntax:**
````markdown
```mdcc_chart caption="Figure 1: Revenue Trend" width="80%"
alt.Chart(data).mark_line()...
```
````

Or YAML-style inside the fence:
````markdown
```mdcc_chart
# --- metadata ---
# caption: "Figure 1: Revenue Trend"
# width: 80%
# ---
alt.Chart(data).mark_line()...
```
````

**Complexity:** Low-Medium. Parsing is straightforward; the harder work is threading metadata through the renderer and Jinja2 template.

---

### 4. Structured JSON Diagnostics (Agent Protocol)

**What:** A `--format json` flag that emits machine-parseable diagnostics instead of human-formatted text.

**Why it matters:**
- Your spec calls this out as "highly desirable" (§18.4).
- This is the single biggest unlock for **automated agent loops** — an agent can parse the JSON, understand exactly which block failed and why, and fix the source programmatically.
- Right now agents have to parse terminal output with regex, which is fragile.

**Output shape:**
```json
{
  "status": "failure",
  "file": "report.md",
  "block_index": 2,
  "block_type": "mdcc_chart",
  "line_range": [10, 15],
  "stage": "execution",
  "category": "EXECUTION_ERROR",
  "exception_type": "KeyError",
  "exception_message": "'revenue'",
  "stdout": "Loading data...\n",
  "stderr": "",
  "duration_ms": 342
}
```

**Complexity:** Low. Your `errors.py` already has structured `Diagnostic` models — this is mostly a serialization layer.

---

### 5. PDF Theming / Style Customization

**What:** Allow users to control the visual theme of the PDF output — fonts, margins, colors, header/footer styles — via frontmatter or a separate config file.

**Why it matters:**
- You've already discussed this in a previous conversation.
- Professional reports need branding. A default theme is fine for drafts, but any serious use requires at least margin/font/color control.
- This also enables "dark mode" or "presentation-ready" themes.

**Implementation path:**
- Built-in default CSS theme (you already have one via Jinja2/WeasyPrint)
- Frontmatter field: `theme: compact` or `theme: ./custom.css`
- A few bundled presets: `default`, `compact`, `academic`, `minimal`
- CSS override file support for full control

**Complexity:** Low-Medium. WeasyPrint already consumes CSS, so it's mostly about exposing the right knobs.

---

## Tier 2 — Solid Extensions, Worth Planning

These add meaningful capability without bloating the core.

### 6. `mdcc_image` — Static Image Embed Blocks

**What:** A block type for embedding static images (local files or generated images) into the document.

**Why it matters:**
- Many analytical reports include screenshots, diagrams, or pre-rendered visuals.
- Right now there's no way to include an image except by generating it inside an `mdcc_chart` block, which is overkill.

**Syntax:**
````markdown
```mdcc_image src="diagrams/architecture.png" caption="System Architecture"
```
````

**Complexity:** Low. No execution needed — just validation + asset copying + HTML insertion.

---

### 7. Watch Mode / Live Recompile

**What:** `mdcc watch report.md` — watches the source file for changes and automatically recompiles.

**Why it matters:**
- During iterative authoring (human or agent), the edit-compile-view loop is the main workflow.
- Watch mode with caching (Tier 1, #2) would make recompiles near-instant for unchanged blocks.

**Complexity:** Low. Use `watchfiles` or similar, debounce, and re-invoke the compile pipeline.

---

### 8. HTML Output Format

**What:** `mdcc compile report.md --format html` — produce a self-contained HTML file instead of PDF.

**Why it matters:**
- HTML is easier to preview, share via browser, and embed in web tools.
- Your rendering pipeline already produces intermediate HTML — this is literally "stop before the WeasyPrint step."
- Interactive Altair charts (Vega-Lite JSON embedded in HTML) become possible for free.

**Complexity:** Low. The assembly stage already produces HTML. Just skip `pdf.py` and inline the CSS.

---

### 9. Explicit Data Dependency Declarations

**What:** Allow blocks to declare which external files they depend on, enabling smarter caching and better diagnostics.

**Syntax:**
````markdown
```mdcc_table depends="data/sales.csv"
df = pd.read_csv("data/sales.csv")
df.describe()
```
````

**Why it matters:**
- Makes caching (#2) reliable: the cache key includes file hashes of declared dependencies.
- Better diagnostics: "Block #3 failed — its dependency `data/sales.csv` does not exist."
- Helps agents reason about data flow.

**Complexity:** Low-Medium.
---

### 10. Shared Prelude / Helper Modules

**What:** A `helpers/` directory or a `prelude:` frontmatter field that injects shared utility functions into all blocks.

**Why it matters:**
- Many reports reuse the same formatting functions, color palettes, or data cleaning helpers.
- This is **explicit** sharing (user opts in), not implicit leakage — it stays within your principles.

**Example:**
```yaml
---
title: "Q3 Report"
prelude: "helpers/formatting.py"
---
```

Every block gets the contents of `formatting.py` injected before its own code.

**Complexity:** Medium. Need to handle import validation, error attribution (is the bug in the prelude or the block?), and caching implications.

---

## Tier 3 — Longer-Term Vision

These are bigger bets that could redefine what `mdcc` is.

### 11. Multi-File Projects / Includes

**What:** Allow splitting a large report across multiple `.md` files with an `include` directive.

**Why it matters:** Reports grow. A 500-line single file becomes unwieldy. Includes let you modularize without abandoning the single-output model.

**Complexity:** High. Source location tracking, error attribution across files, and ordering semantics all get harder.

---

### 12. Parameterized Reports

**What:** Accept parameters at compile time that get injected into blocks as variables.

```bash
mdcc compile report.md --param region=EMEA --param quarter=Q3
```

Inside blocks: `params["region"]` → `"EMEA"`

**Why it matters:**
- This is the #1 feature request in every report tooling system.
- Agents can generate one template and compile it N times with different parameters.
- Enables batch report generation pipelines.

**Complexity:** Medium. Need to define parameter passing, type coercion, and template variable injection.

---

### 13. `mdcc validate` — Dry-Run Without Execution

**What:** A CLI command that parses and structurally validates the document without executing any blocks.

**Why it matters:**
- Fast feedback loop for agents: "Is this document well-formed?" in milliseconds.
- Useful in CI pipelines as a lint step.

**Complexity:** Very Low. You already have the parse + validate stages — just stop before execution.

---

### 14. Table of Contents Generation

**What:** Auto-generate a table of contents from markdown headings, inserted at a `<!-- toc -->` marker.

**Why it matters:** Professional reports need navigation. This is a low-effort, high-polish feature.

**Complexity:** Very Low.

---

## Summary Matrix

| # | Feature | Impact | Complexity | Philosophy Fit |
|---|---------|--------|------------|----------------|
| 1 | `mdcc_compute` blocks | ★★★★★ | Low | ✅ Perfect |
| 2 | Per-block caching | ★★★★★ | Medium | ✅ Designed for it |
| 3 | Block metadata (captions) | ★★★★☆ | Low-Med | ✅ Spec reserves room |
| 4 | JSON diagnostics | ★★★★☆ | Low | ✅ Spec calls for it |
| 5 | PDF theming | ★★★★☆ | Low-Med | ✅ Natural extension |
| 6 | `mdcc_image` blocks | ★★★☆☆ | Low | ✅ Clean addition |
| 7 | Watch mode | ★★★☆☆ | Low | ✅ Workflow quality |
| 8 | HTML output | ★★★☆☆ | Low | ✅ Pipeline already there |
| 9 | Data dependencies | ★★★☆☆ | Low-Med | ✅ Enables caching |
| 10 | Shared prelude | ★★★☆☆ | Medium | ⚠️ Careful design needed |
| 11 | Multi-file projects | ★★☆☆☆ | High | ⚠️ Scope creep risk |
| 12 | Parameterized reports | ★★★★☆ | Medium | ✅ Agent-first win |
| 13 | `mdcc validate` | ★★★☆☆ | Very Low | ✅ Trivial to add |
| 14 | Table of contents | ★★☆☆☆ | Very Low | ✅ Polish feature |

---

## Recommended Sequencing

If I were prioritizing the next sprint after MVP:

> **Phase 1 (Quick wins):** `mdcc validate` (#13) → JSON diagnostics (#4) → Block metadata/captions (#3)
> 
> **Phase 2 (Core power):** `mdcc_compute` (#1) → Per-block caching (#2) → Data dependencies (#9)
> 
> **Phase 3 (Polish):** PDF theming (#5) → HTML output (#8) → `mdcc_image` (#6) → Watch mode (#7)
> 
> **Phase 4 (Growth):** Parameterized reports (#12) → Shared prelude (#10) → ToC (#14)
