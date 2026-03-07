# mdcc Core Design Principles

## 1. Agent-first

`mdcc` is designed primarily for **coding agents**, not interactive human editing environments.

The format, execution model, and diagnostics should be optimized for tools that automatically generate, edit, and debug documents.

Implications:
- simple and predictable syntax
- minimal ambiguity in the format
- clear, structured diagnostics
- easy for agents to insert, modify, or replace blocks
- compatibility with existing agent workflows that operate on files and CLI commands

Human usability is important, but **agent reliability and clarity take priority**.

---

## 2. Plain text / Git-friendly source

The source document must remain **plain text** and easy to work with using normal developer tooling.

Benefits:
- clean git diffs
- easy merges and reviews
- compatibility with existing editors and automation tools
- easy modification by coding agents

The format intentionally avoids structures that introduce noisy diffs or hidden state (such as notebook JSON formats).

Markdown is used because it is widely understood by both developers and AI systems.

---

## 3. Single source → compiled artifact

`mdcc` follows a **compiler-style workflow**.

A single source document defines the content and logic of the report, and the tool compiles that source into a generated artifact.

This principle keeps the workflow simple and reproducible:
- the source file acts as the canonical definition of the document
- the compiled artifact is generated from that source

The exact output format and supported block types may evolve over time, but the core idea remains the same:  
**documents are defined as source and produced through compilation.**