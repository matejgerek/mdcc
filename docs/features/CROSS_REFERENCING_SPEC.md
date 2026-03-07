# CROSS_REFERENCING_SPEC.md

## Status
**DONE**

## Overview

This document defines the **cross-referencing system** for mdcc documents.

Cross-referencing allows authors to reference figures and tables in prose using
stable labels defined on executable blocks.

The design goals are:

- Deterministic and simple
- Human-readable in raw source
- Easy for agents to generate and modify
- Independent from renderer implementation
- Compatible with future extensions

Cross-references are resolved during compilation and replaced with the correct
artifact numbering (e.g., "Figure 2", "Table 1").

---

# Core Concept

Cross-referencing connects:

1. **Block label declarations**
2. **Inline references in markdown text**

Example:

```markdown
The trend can be seen in @fig:revenue-growth.

```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
chart
```
```

Rendered output:

The trend can be seen in **Figure 1**.

---

# Labels

## Definition

A label is a unique identifier assigned to a block via metadata.

Example:

```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
```

Labels allow the block to be referenced elsewhere in the document.

## Requirements

Labels must:

- Be unique across the entire document
- Match the label grammar
- Refer to a referenceable block

## Label Grammar

```
^[A-Za-z][A-Za-z0-9:_-]*$
```

Examples:

Valid:

- fig:revenue-growth
- tbl:market-summary
- fig:q4_profit

Invalid:

- 1figure
- fig revenue
- fig@trend

## Recommended Prefixes

Although not strictly required, the following prefixes are strongly recommended:

| Block Type | Prefix |
|-------------|--------|
| mdcc_chart | fig: |
| mdcc_table | tbl: |

These prefixes improve readability and make debugging easier.

---

# Reference Syntax

## Inline Reference

References are written in markdown text using the following syntax:

```
@<label>
```

Examples:

```
See @fig:revenue-growth for details.
Metrics are summarized in @tbl:market-summary.
```

## Parsing Rules

A valid reference:

- Starts with `@`
- Followed by a valid label
- Appears inside normal markdown text

The compiler should detect references using a deterministic parser or regex.

---

# Resolution

During compilation, references are replaced with a human-readable artifact reference.

## Resolution Output

| Block Type | Rendered Reference |
|-------------|-------------------|
| mdcc_chart | Figure N |
| mdcc_table | Table N |

Example:

Source:

```
See @fig:revenue-growth.
```

Rendered:

```
See Figure 1.
```

---

# Numbering

Numbering is assigned per artifact type.

## Independent Counters

Figures and tables maintain separate numbering.

Example:

```
Figure 1
Figure 2
Table 1
Table 2
```

This ensures consistent technical writing conventions.

## Order

Numbers are assigned in **document order**.

---

# Blocks Eligible for Referencing

In the initial implementation, only these block types are referenceable:

| Block Type | Artifact Type |
|-------------|--------------|
| mdcc_chart | Figure |
| mdcc_table | Table |

Blocks without labels cannot be referenced.

---

# Caption Rendering

If a block has a caption and label:

Example:

```
```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
```
```

Rendered caption:

```
Figure 1. Revenue growth by region
```

If no caption exists:

```
Figure 1
```

---

# Compiler Pipeline

Cross-reference resolution occurs after parsing and before rendering.

Recommended pipeline:

1. Parse document
2. Extract blocks and metadata
3. Collect labels
4. Validate label uniqueness
5. Assign artifact numbers
6. Scan markdown text for references
7. Replace references with resolved text
8. Render final document

---

# Diagnostics

## Duplicate Labels

If multiple blocks declare the same label:

Error:

```
Duplicate label: fig:revenue-growth
```

Compilation must fail.

## Unknown Reference

If a reference points to a non-existent label:

Example:

```
See @fig:not-found.
```

Error:

```
Unresolved reference: fig:not-found
```

Diagnostics should include:

- error category
- message
- source location

## Invalid Label Syntax

If a label does not match the grammar:

```
Invalid label format: fig revenue
```

---

# Phase Rollout

## Phase 1 (Foundation)

- Label metadata implemented
- Label uniqueness validation
- Internal label registry

Cross-referencing syntax may be parsed but not yet resolved.

## Phase 2 (Full Feature)

- Inline reference detection
- Artifact numbering
- Reference resolution
- Caption numbering integration
- Full diagnostics

---

# Example End-to-End

Source:

```
# Market Snapshot

Growth trends are visible in @fig:revenue-growth.

```mdcc_chart caption="Revenue growth by region" label="fig:revenue-growth"
chart
```

```mdcc_table caption="Regional summary" label="tbl:regional-summary"
summary_df
```
```

Rendered:

```
# Market Snapshot

Growth trends are visible in Figure 1.

Figure 1. Revenue growth by region
[chart]

Table 1. Regional summary
[table]
```

---

# Future Extensions

Possible future enhancements include:

- Section referencing
- Appendix references
- Custom reference text
- Reference links in HTML output
- Automatic list of figures/tables

These are explicitly out of scope for the initial implementation.
