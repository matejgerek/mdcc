# Block Metadata — Technical Specification

## Status
**PLANNED**

This document defines the proposed block metadata extension for `mdcc`.
It is intentionally scoped as a follow-up spec to the MVP and is designed to fit the existing architecture, parsing model, and agent-first principles.

---

# 1. Purpose

Add optional **block-level metadata** to executable blocks so documents can express structural information such as captions and stable labels directly at the block site.

The extension must:
- remain plain-text and git-friendly
- remain easy for coding agents to generate and patch
- stay local to the block it affects
- preserve deterministic behavior
- avoid introducing layout-heavy publishing complexity too early

This spec is intentionally split into **two phases**.

---

# 2. Design Goals

## 2.1 Locality
Metadata should live next to the block it describes.
A reader or agent should be able to inspect or modify a block without searching elsewhere in the document.

## 2.2 Low syntax overhead
The syntax should remain compact and markdown-adjacent.
It should not introduce nested formats unless clearly justified.

## 2.3 Typed validation
Metadata must be validated explicitly.
Unknown keys and invalid values must produce diagnostics rather than being silently ignored.

## 2.4 Forward-compatible scaffolding
Phase 1 should introduce the parsing and AST/model contract needed for future metadata additions without over-engineering a full publishing system.

## 2.5 Rendering-only semantics
Metadata must affect rendering and document structure only.
It must not affect runtime execution semantics in this spec.

---

# 3. Scope

## 3.1 Applies to
This spec applies to executable block types:
- `mdcc_chart`
- `mdcc_table`

The metadata model should be implemented in a way that can later be reused by future block types.

## 3.2 Out of scope
This spec does not introduce:
- execution-time metadata
- per-block runtime overrides
- imports or shared execution state
- arbitrary styling knobs
- generic CSS-like formatting
- placement engines
- cross-reference rendering syntax

Cross-reference support may be added later and should build on `label`, but is not required by this spec.

---

# 4. Recommended Syntax Contract

## 4.1 Chosen contract
Block metadata should be expressed as **inline attributes on the opening fence line**.

Example:

````markdown
```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
chart
```
````

and

````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary"
summary_df
```
````

## 4.2 Why inline attributes
This contract is preferred because it:
- keeps metadata local to the block
- avoids nested YAML/frontmatter syntax inside blocks
- is easier for coding agents to edit in place
- stays visually lightweight
- leaves document-level frontmatter reserved for document-level metadata

## 4.3 Explicitly rejected contract for now
The following is intentionally not used in this spec:

````markdown
```mdcc_chart
---
caption: Revenue by region
label: fig:revenue-region
---
chart
```
````

Reasons:
- higher syntax overhead
- nested syntax inside fenced blocks
- worse scanning ergonomics
- more complicated agent patching
- unnecessary expressiveness for the initial metadata set

---

# 5. Parsing Contract

## 5.1 General rule
The opening executable fence may contain zero or more metadata attributes after the block type.

General form:

```
```<block_type> key="value" key2="value2"
```

where `<block_type>` is one of:
- `mdcc_chart`
- `mdcc_table`

## 5.2 Attribute format
Each attribute must be a `key="value"` pair.

Phase 1 intentionally supports only quoted string values.
This keeps the parser simple and the contract unambiguous.

Examples:
- `caption="Revenue by region"`
- `label="fig:revenue-region"`

## 5.3 Whitespace
Attributes are separated by one or more spaces.
Leading and trailing whitespace after the block type may be tolerated by the parser, but normalized internally.

## 5.4 Duplicate keys
Duplicate metadata keys in the same block are invalid and must produce a diagnostic.

Example invalid syntax:

````markdown
```mdcc_chart caption="A" caption="B"
chart
```
````

## 5.5 Unknown keys
Unknown metadata keys are invalid and must produce a diagnostic.
They must not be silently ignored.

This matters especially during the phase split.
For example, a phase-1 compiler encountering `width="wide"` should fail clearly rather than pretending to support it.

---

# 6. Two-Phase Rollout

# 6.1 Phase 1
Phase 1 introduces the metadata pipeline end-to-end with only two supported keys:
- `caption`
- `label`

Phase 1 must implement:
- fence attribute parsing
- AST/model support for block metadata
- metadata validation
- renderer access to metadata
- rendered captions for supported blocks
- clear diagnostics for metadata errors

Phase 1 does **not** need to implement:
- width/alignment behavior
- source notes
- cross-reference resolution
- any styling beyond basic caption rendering

## 6.2 Phase 2
Phase 2 extends the same metadata scaffolding with these additional keys:
- `width`
- `align`
- `source_note`

Phase 2 should be additive.
It should not require changing the basic block metadata contract introduced in phase 1.

---

# 7. Metadata Schema by Phase

## 7.1 Phase 1 schema
Supported keys:
- `caption: string`
- `label: string`

Both are optional.

Examples:

````markdown
```mdcc_chart caption="Revenue by region"
chart
```
````

````markdown
```mdcc_table label="tbl:summary"
summary_df
```
````

````markdown
```mdcc_chart caption="Revenue by region" label="fig:revenue-region"
chart
```
````

## 7.2 Phase 2 schema
Phase 2 adds:
- `width: enum`
- `align: enum`
- `source_note: string`

Recommended value sets:
- `width ∈ {"content", "wide", "full"}`
- `align ∈ {"left", "center", "right"}`

Example:

````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary" width="full" align="center" source_note="Source: internal CRM export"
summary_df
```
````

---

# 8. Field Semantics

## 8.1 `caption`
Human-visible descriptive text rendered with the block output.

Purpose:
- improves readability
- makes charts and tables feel like first-class report elements
- creates a natural base for later figure/table numbering

Phase 1 behavior:
- optional
- if present, rendered with the block output
- no numbering required by this spec

Recommended rendering convention:
- tables: caption above the rendered table
- charts: caption below the rendered chart

This convention is recommended for consistency, but exact presentation details may remain renderer-owned.

## 8.2 `label`
Stable machine-readable identifier attached to a block.

Purpose:
- prepares for future cross-references
- provides a durable anchor for agents and diagnostics
- gives the document structure beyond visible text

Phase 1 behavior:
- optional
- stored in the parsed block metadata
- not required to be rendered visibly
- not required to power references yet

## 8.3 `width` (Phase 2)
Rendering hint for how wide the block should appear relative to the content area.

Recommended values:
- `content`
- `wide`
- `full`

This field must remain a constrained semantic hint, not arbitrary styling.

## 8.4 `align` (Phase 2)
Rendering hint for horizontal alignment of the rendered block.

Recommended values:
- `left`
- `center`
- `right`

## 8.5 `source_note` (Phase 2)
Optional source or provenance text associated with the rendered block.

Purpose:
- useful in analytical reports
- helps communicate data provenance without embedding it in the narrative text

---

# 9. Validation Rules

## 9.1 `caption`
Rules:
- must be a string
- must not be empty after trimming

Invalid examples:
- `caption=""`
- `caption="   "`

## 9.2 `label`
Rules:
- must be a string
- must match the regex:

```text
^[A-Za-z][A-Za-z0-9:_-]*$
```

Rationale:
- easy to read
- safe for future cross-reference syntax
- stable for machine processing

Examples of valid labels:
- `fig:revenue-region`
- `tbl:summary`
- `chart_1`
- `Revenue2025`

Examples of invalid labels:
- `123abc`
- `my label`
- `revenue.region?`

## 9.3 Phase-2 validation
Recommended future rules:
- `width` must be one of `content`, `wide`, `full`
- `align` must be one of `left`, `center`, `right`
- `source_note` must be a non-empty string if present

## 9.4 Unknown key handling
Any unknown metadata key must produce a validation diagnostic.

Example invalid block for phase 1:

````markdown
```mdcc_chart caption="Revenue" width="wide"
chart
```
````

Expected result:
- compilation error or validation failure
- explicit message that `width` is unsupported in the current compiler/spec phase

## 9.5 Duplicate key handling
Duplicate keys are invalid.
A block must not define the same metadata key more than once.

---

# 10. AST / Model Contract

## 10.1 Recommendation
Even in phase 1, metadata should be represented as a dedicated typed object rather than as an unstructured dictionary.

Recommended shape:

```python
class BlockMetadata(BaseModel):
    caption: str | None = None
    label: str | None = None
```

Executable block nodes should then carry:

```python
class ExecutableBlockNode(BaseModel):
    ...
    metadata: BlockMetadata
```

## 10.2 Why a dedicated model
This approach:
- keeps validation explicit
- fits the compiler’s typed architecture
- makes future phase-2 additions additive
- avoids leaking raw parser details deeper into the pipeline

## 10.3 Phase 2 extension
Phase 2 can extend the same model shape with:

```python
class BlockMetadata(BaseModel):
    caption: str | None = None
    label: str | None = None
    width: Literal["content", "wide", "full"] | None = None
    align: Literal["left", "center", "right"] | None = None
    source_note: str | None = None
```

---

# 11. Rendering Contract

## 11.1 Phase 1 rendering requirements
Phase 1 renderer behavior should be minimal and deterministic.

Required behavior:
- if `caption` is present, render it with the block output
- if `label` is present, preserve it in the internal compiled representation if possible
- do not require visible rendering of `label`

## 11.2 Numbering
Automatic numbering of tables and figures is not required by this spec.
However, the presence of `caption` and `label` should make later numbering straightforward.

## 11.3 Reference resolution
Reference syntax such as `@fig:revenue-region` is not part of this spec.
It is an expected future extension that should build on `label`.

---

# 12. Diagnostics Expectations

Metadata errors should integrate with the existing diagnostics model.

Useful diagnostics include:
- invalid metadata syntax
- duplicate metadata key
- unknown metadata key
- invalid label format
- empty caption

Diagnostics should include:
- stage
- category
- source location if available
- clear error message
- expected vs actual shape where useful

Examples of desirable messages:
- `unsupported metadata key 'width' for mdcc_chart in this compiler version`
- `duplicate metadata key 'caption'`
- `invalid label 'my label'; expected pattern ^[A-Za-z][A-Za-z0-9:_-]*$`
- `caption must not be empty`

---

# 13. Examples

## 13.1 Phase 1 — chart with caption only
````markdown
```mdcc_chart caption="Revenue by region"
chart
```
````

## 13.2 Phase 1 — table with caption and label
````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary"
summary_df
```
````

## 13.3 Phase 1 — invalid unknown key
````markdown
```mdcc_chart caption="Revenue by region" width="wide"
chart
```
````

Expected: validation error.

## 13.4 Phase 1 — invalid label
````markdown
```mdcc_table label="regional summary"
summary_df
```
````

Expected: validation error because the label contains spaces.

## 13.5 Phase 2 — full example
````markdown
```mdcc_table caption="Regional summary" label="tbl:regional-summary" width="full" align="center" source_note="Source: CRM export"
summary_df
```
````

---

# 14. Implementation Guidance

## 14.1 Keep phase 1 thin
Phase 1 should introduce only the infrastructure necessary to support metadata cleanly.
It should not attempt to build a broad publishing abstraction.

## 14.2 Keep metadata separate from execution
This spec intentionally limits metadata to rendering and structural concerns.
Execution behavior should remain governed by the existing block type and runtime model.

## 14.3 Fail loudly on unsupported future keys
Because this spec is phased, it is important that unsupported keys produce explicit diagnostics rather than partial behavior.

## 14.4 Preserve backward compatibility
Blocks without metadata must continue to compile exactly as before.

---

# 15. Summary

This spec introduces block metadata in a deliberately narrow, extensible way.

## Phase 1
Adds:
- inline metadata parsing on executable fence lines
- `caption`
- `label`
- typed metadata model support
- validation and diagnostics
- minimal caption rendering

## Phase 2
Adds:
- `width`
- `align`
- `source_note`

The design goal is to improve structure and report quality without compromising the tool’s core identity as a deterministic, agent-first executable report compiler.
