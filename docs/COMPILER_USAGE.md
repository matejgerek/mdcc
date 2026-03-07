# mdcc Compiler Usage and Failure Interpretation

This document provides a guide for invoking the `mdcc` compiler, understanding its inner stages, interpreting common diagnostic failures, and managing its temporary build artifacts.

---

## 1. Running the Compiler

The `mdcc` application converts a solitary plain-text source file (.md) directly into a complete PDF report. 

You execute the compiler using its unified `compile` command:

```bash
mdcc compile <input_file> [output_file] [OPTIONS]
```

### Arguments:
*   `input_file`: Path to the markdown source file (Required).
*   `output_file`: Path to the generated PDF. If omitted, the compiler defaults to creating `<input>.pdf` adjacent to the input file.

### Options:
*   `--timeout <seconds>`, `-t`: Overrides the default execution time allowed per block (default is 30.0 seconds).
*   `--keep-build-dir`: Prevents the compiler from deleting the intermediate `.mdcc_build` directory post-completion. This is extremely useful for manual debugging.
*   `--verbose`, `-v`: Elevates diagnostic output detail if the compilation fails. It will also display a success message when finishing gracefully.

For a dry-run validation pass that stops before payload generation, execution, rendering, and PDF output, use:

```bash
mdcc validate <input_file>
```

This command reads, parses, and validates the document, then prints a human-readable validation report. It exits `0` when the document is valid and `1` when read, parse, or validation errors are detected.

---

## 2. High-Level Compiler Stages

The `mdcc` compilation process isn't a single magical step. Under the hood, the document passes through an explicit sequence of stages:

1.  **Read Stage**: Loads the source file into memory.
2.  **Parse Stage**: Separates frontmatter, standard markdown text, and explicitly fenced executable blocks (`mdcc_chart` and `mdcc_table`).
3.  **Validation Stage (Structural)**: Checks if blocks are properly closed and if their requested types are recognized by the system MVP.
4.  **Execution Stage**: Runs every executable block sequentially from the top to bottom. Each block evaluates in its own **completely isolated Python process** with pre-loaded data tools (`pandas`, `numpy`, Altair).
5.  **Validation Stage (Typed Output)**: Assures that the captured final expression result perfectly matches the block's promised contract (e.g., Altair Chart, Pandas DataFrame).
6.  **Rendering Stage**: Maps the semantic outputs (tables or charts) to their target visual representations (HTML fragments, image artifacts). 
7.  **Assembly Stage**: Interleaves the processed execution artifacts seamlessly with the standard markdown narrative.
8.  **PDF Generation Stage**: Compiles the unified assembly into the final PDF.

---

## 3. Failure Categories

When `mdcc` encounters an error, it interrupts compilation immediately instead of outputting an incomplete or visually broken document. The failure is broadly categorized into one of these buckets:

*   **Read Error (`READ_ERROR`)**: Triggered when the input source file is missing, empty, or unreadable due to filesystem permissions.
*   **Parse Error (`PARSE_ERROR`)**: Triggered when the markdown format is fundamentally broken (e.g., malformed code blocks or heavily distorted frontmatter).
*   **Validation Error (`VALIDATION_ERROR`)**: Arises when the overall structure is poor (e.g. unknown block types) OR an executable block returns a data type that breaks its own contract (e.g., an `mdcc_chart` returned a pandas data frame). 
*   **Execution Error (`EXECUTION_ERROR`)**: Triggered by a runtime exception raised inside the Python block itself (e.g., `KeyError` on a dataframe layer).
*   **Timeout Error (`TIMEOUT_ERROR`)**: Triggered if a specific block runs longer than the allowed `--timeout` constraint (usually an infinite loop or heavy computation). 
*   **Rendering Error (`RENDERING_ERROR`)**: Arises when an explicitly returned object is valid in type but fails to be mapped to an output visual (e.g. invalid arguments passed to a core charting library).
*   **PDF Generation Error (`PDF_ERROR`)**: Raised when the internal HTML rendering mechanism fails while converting the assembled output to the PDF document. 

---

## 4. Interpreting Block Diagnostics

The most frequent errors you will encounter will be `ExecutionError` or `ValidationError` inside your execution blocks. By design, the compiler will provide deterministic and highly readable context when these happen.

### Basic Diagnostic Structure:
A terminal-formatted compiler error looks like this:

```
error: The chart block crashed at execution.
  stage: execution
  file: input.md
  block: #3 (mdcc_chart)
  location: lines 10:1-15:3
```

### Verbose Mode (`--verbose`):
Enabling the verbose flag expands the diagnostic snapshot significantly, adding properties that are indispensable for autonomous coding agents:

*   **category**: The exact exception class category.
*   **expected / actual**: Highly actionable typing mismatches (e.g., expected `Altair Chart`, got `NoneType`).
*   **stderr / stdout**: Any manual `print()` statements evaluating inside that specific block right up until the point of panic.
*   **caused by**: The raw original Python exception that caused the engine crash.

**Interpreting logs vs exports:** Remember that printed output (`stdout`) never renders onto the PDF. However, you should still actively harness `print()` strings for visibility when debugging your logic, checking it via compiler diagnostics.

---

## 5. Temporary Build Artifact Behavior (.mdcc_build)

During the compilation process, `mdcc` produces an assortment of intermediary assets required by the underlying PDF layout engine, such as temporary static figures and staging scripts.

*   **Where**: These are deposited into a `.mdcc_build` directory physically located adjacent to the active working directory.
*   **Default Behavior**: To retain a clean filesystem cache, `mdcc` removes the `.mdcc_build` folder implicitly after compilation ends (both on succeeding and failing builds). 
*   **Exposing the Build Folder**: By passing `--keep-build-dir`, the folder survives the end of the script. In tricky scenarios where layout artifacts mysteriously fail, `--keep-build-dir` allows you to open intermediate representations and visually inspect the HTML before the PDF rendering stage.
