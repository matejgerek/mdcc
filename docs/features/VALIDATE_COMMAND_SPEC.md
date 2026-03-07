
# VALIDATE_COMMAND_SPEC.md

## Status
**PLANNED**

## Overview

This document defines the **`validate` command** for the mdcc compiler.

The command checks whether a document is structurally valid **without executing blocks or rendering output**.

The goal is to provide fast feedback for:

- authors
- CI pipelines
- agents generating mdcc documents
- editor integrations

Validation ensures the document satisfies the syntactic and structural rules defined by the mdcc format.

---

# Command

```
mdcc validate <input-file>
```

Example:

```
mdcc validate report.md
```

The command exits with:

- **exit code 0** → document is valid
- **exit code 1** → validation errors detected

---

# Phase Rollout

The feature is implemented in **two phases**.

## Phase 1 (Core Validation)

The command performs structural validation and prints **human-readable output**.

Capabilities:

- Parse document
- Validate block syntax
- Validate metadata
- Validate label rules
- Detect duplicate labels
- Detect invalid metadata keys
- Detect invalid label format
- Report diagnostics with source locations

Output is intended for humans.

Example:

```
Validation successful

Blocks discovered:
1. mdcc_chart (line 18)
2. mdcc_table (line 29)

Labels:
- fig:revenue-growth
- tbl:regional-summary
```

If errors occur:

```
Validation failed

Error: Duplicate label 'fig:revenue-growth'
Line: 42
```

---

## Phase 2 (Optional JSON Output)

Phase 2 adds an optional **machine-readable output mode**.

```
mdcc validate <file> --json
```

This does not change validation behavior.  
It only changes **output formatting**.

Example output:

```json
{
  "status": "ok",
  "blocks": [
    {
      "type": "mdcc_chart",
      "line": 18,
      "metadata": {
        "caption": "Revenue growth by region",
        "label": "fig:revenue-growth"
      }
    },
    {
      "type": "mdcc_table",
      "line": 29,
      "metadata": {
        "caption": "Regional summary",
        "label": "tbl:regional-summary"
      }
    }
  ],
  "labels": [
    "fig:revenue-growth",
    "tbl:regional-summary"
  ],
  "diagnostics": []
}
```

This format is intended for:

- automation scripts
- AI agents
- editor plugins
- CI systems

Implementation of the JSON mode is **optional** and may be added later without affecting Phase 1 behavior.

---

# Validation Rules

## Block Syntax

Each executable block must:

- start with a valid mdcc block fence
- use a supported block type
- contain valid code content

Invalid block syntax must produce a validation error.

---

## Metadata Validation

Block metadata must:

- use supported metadata keys
- match expected value types

Example invalid metadata:

```
```mdcc_chart caption=123
```
```

Error:

```
Invalid metadata value for key 'caption'
Expected string
```

---

## Label Validation

Labels must satisfy:

- unique across the document
- match label grammar
- be attached to a referenceable block

### Label Grammar

```
^[A-Za-z][A-Za-z0-9:_-]*$
```

Examples:

Valid:

```
fig:revenue-growth
tbl:regional-summary
fig:q4_profit
```

Invalid:

```
1figure
fig revenue
fig@trend
```

---

## Duplicate Labels

Duplicate labels must produce an error.

Example:

```
Duplicate label detected: fig:revenue-growth
```

Compilation must fail.

---

# Diagnostics

Diagnostics should include:

- error category
- message
- source location (line number)

Example:

```
Error: Duplicate label 'fig:revenue-growth'
Line: 42
Category: validation_error
```

Diagnostics must be deterministic and stable for automation.

---

# Execution Model

The validate command **must not execute blocks**.

Validation only includes:

- parsing
- structural checks
- metadata checks
- label checks

It must be significantly faster than a full compile.

---

# Relationship to Compile

```
mdcc validate report.md
mdcc compile report.md
```

Typical workflow:

```
1. author edits document
2. run validate
3. fix errors
4. run compile
```

Agents may also use this workflow when generating documents.

---

# Future Extensions

Possible future improvements:

- cross-reference validation
- metadata schema introspection
- dependency detection
- JSON schema for diagnostics
- editor integration support

These are intentionally **out of scope for the initial implementation**.
