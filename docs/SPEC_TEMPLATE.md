# [FEATURE NAME] — Specification

<!-- Replace [FEATURE NAME] with the short name of the feature, e.g. "Cross-Referencing" or "Block Metadata". -->
<!-- Filename convention: docs/features/[SCREAMING_SNAKE_CASE]_SPEC.md -->

## Status

<!-- Pick one: PLANNED | IN PROGRESS | PHASE N DONE | DONE -->
**PLANNED**

## Overview

<!--
1–3 paragraphs. Answer:
  - What is this feature?
  - What problem does it solve?
  - Who benefits (authors, agents, CI, ...)?
Keep it short. Details go in the numbered sections below.
-->

---

# 1. Purpose

<!--
One tight paragraph:
  - What capability does this spec add?
  - What must the feature satisfy at a high level?
  - What principles must it respect?
-->

---

# 2. Design Goals

<!--
List the key design priorities that constrain every decision in this spec.
Name each goal and give a one-line rationale.
Examples from existing specs:
  - Locality — metadata lives next to the block it describes
  - Low syntax overhead — format stays compact and markdown-adjacent
  - Typed validation — unknown keys produce diagnostics, not silence
  - Forward-compatible — phase 1 scaffolding doesn't prevent phase 2 additions
-->

## 2.1 [Goal name]

[One-line rationale.]

## 2.2 [Goal name]

[One-line rationale.]

---

# 3. Scope

## 3.1 Applies to

<!--
What document elements, block types, pipeline stages, or user scenarios
does this spec cover?
-->

## 3.2 Out of scope

<!--
Be explicit. List capabilities that are NOT introduced by this spec.
This prevents scope creep during implementation and makes phase splits clear.
-->

---

# 4. Problem Statement

<!--
Optional — include when the design decision is non-obvious.
Describe the competing constraints or tensions this spec resolves.
A comparison table works well here:

| Goal | Problem |
|------|---------|
| ... | ... |
-->

---

# 5. [Core Mechanism / Syntax Contract / Command / Solution]

<!--
The main technical proposal: syntax, command, protocol, data structure, etc.
Name this section after the primary artifact of the spec.

Examples:
  - "5. Syntax Contract"        (for language/format additions)
  - "5. Command"                (for CLI additions)
  - "5. Proposed Solution"      (for architectural additions)
  - "5. Container Structure"    (for data format additions)

Sub-sections as needed.
-->

## 5.1 [Sub-topic]

<!--
Use concrete examples (code blocks, tables, bullet lists).
Prefer showing a minimal complete example first, then explaining it.
-->

## 5.2 [Rejected alternatives] *(optional)*

<!--
If a meaningful alternative was considered and rejected, document it here
with the reason. This prevents relitigating the same decisions later.
-->

---

# 6. Phase Rollout

<!--
Include when the feature is too large to ship atomically, or when
a phased approach de-risks the implementation.
If the feature is small and ships in one go, remove this section
and replace with a single "Implementation" section.
-->

## Phase 1 — [Short name]

<!--
What is completed? What is explicitly deferred?
Be specific: name the capabilities, not just "basic support".
-->

Delivers:

- ...

Does **not** include:

- ...

## Phase 2 — [Short name]

<!--
What does this phase add?
Should be additive — no breaking changes to phase 1 contracts.
-->

Adds:

- ...

---

# 7. Schema / Contract

<!--
Formal definition of proposed  the data shape, metadata keys, CLI flags,
API surface, or file structure introduced by this spec. You are free to change this to whatever you see is optimal during analysis/implementation.

For metadata/data schemas:
  - list every field, its type, whether it is required/optional
  - show at least one complete valid example

For CLI commands:
  - show the command signature
  - document flags and exit codes

For data structures:
  - show the model shape (pseudocode or Python class)
-->

## 7.1 Phase 1

| Field / Option | Type | Required | Description |
|----------------|------|----------|-------------|
| ...            | ...  | ...      | ...         |

Example:

```
<!-- minimal valid example here -->
```

## 7.2 Phase 2 *(if applicable)*

| Field / Option | Type | Required | Description |
|----------------|------|----------|-------------|
| ...            | ...  | ...      | ...         |

---

# 8. Validation Rules

<!--
Enumerate the constraints the compiler must enforce.
Group by entity (per field, per block, per document).
For each rule, state:
  - what is valid / invalid
  - what diagnostic is produced on violation
-->

## 8.1 [Entity]

- Rule description.
- Rule description.

Invalid example:

```
<!-- show invalid input -->
```

Expected diagnostic:

```
[error message]
```

---

# 9. Diagnostics

<!--
Describe the expected diagnostic behavior for all error conditions
introduced by this spec.

Each diagnostic should carry:
  - error category
  - human-readable message
  - source location (file, line) if available

Example diagnostic messages (from existing specs):
  - "Duplicate label: fig:revenue-growth"
  - "unsupported metadata key 'width' for mdcc_chart in this compiler version"
  - "Invalid label format: fig revenue; expected pattern ^[A-Za-z][A-Za-z0-9:_-]*$"
-->

Diagnostics must include:

- Error category
- Message
- Source location (line number)

| Condition | Category | Example message |
|-----------|----------|-----------------|
| ...       | ...      | ...             |

---

# 10. Pipeline Integration

<!--
Where does this feature fit in the compiler pipeline?
Describe which stage(s) are affected (parser, validator, executor, renderer, assembler, etc.)
and in what order operations must occur.

Example from cross-referencing spec:
  1. Parse document
  2. Collect labels
  3. Validate label uniqueness
  4. Assign artifact numbers
  5. Scan markdown text for references
  6. Replace references with resolved text
  7. Render final document
-->

---

# 11. Examples

<!--
Show at least one complete end-to-end example: input → output.
Use sub-sections for different cases: happy path, edge cases, error cases.
-->

## 11.1 [Happy path]

Input:

```
<!-- source here -->
```

Output / result:

```
<!-- expected output here -->
```

## 11.2 [Error case]

Input:

```
<!-- invalid source here -->
```

Expected diagnostic:

```
[error message]
```

---

# 12. Implementation Guidance

<!--
Optional but encouraged for complex features.
Give concrete direction to the implementer:
  - what to keep thin in phase 1
  - what to keep separate from existing sub-systems
  - what must not regress (backward compatibility)
  - where to fail loudly vs. silently
-->

---

# 13. Why This Design

<!--
Optional — include when the core design decision is non-obvious
or when you want to pre-empt likely questions.
Summarize the key constraint that makes this the right call.

Example format (table or bullet list):
| Requirement     | Result    |
|-----------------|-----------|
| Single file     | preserved |
| Deterministic   | preserved |
| Agent-friendly  | enabled   |
-->

---

# 14. Future Extensions

<!--
List plausible follow-on capabilities that are explicitly out of scope
for this spec but should be considered when making design decisions.
Keeping these visible prevents designs that accidentally foreclose them.
-->

- [Extension idea]
- [Extension idea]

These are **out of scope** for the current spec.

---

# 15. Summary

<!--
Close with a tight paragraph (or bullet list) restating:
  - what this spec introduces
  - what phase 1 delivers
  - what phase 2 adds (if applicable)
  - the core design principle it upholds
-->
