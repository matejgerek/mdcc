# CACHE_SPEC.md

## Status
**IN PROGRESS PHASE 1**

## Purpose

This document describes a high-level caching design for **mdcc**. The goal is to make repeated compilation significantly faster while preserving correctness.

The core rule is:

> A block must be cached based on the fingerprint of all of its effective inputs, not only its source code.

That means caching must account for:

* block source
* block type and relevant metadata
* runtime/compiler version
* parameter values
* external files read by the block

This is necessary because a block can remain textually identical while the underlying data changes.

---

## Goals

The caching system should:

1. Speed up repeated compilation of unchanged documents.
2. Avoid re-executing blocks when neither code nor effective inputs changed.
3. Invalidate cache entries when source, runtime, parameters, or dependencies change.
4. Work with the current mdcc execution model with minimal user-facing complexity.
5. Preserve the possibility of stricter dependency declarations later.

---

## Non-goals

At this stage, the caching system does **not** need to fully solve:

* arbitrary non-file ambient dependencies
* network-dependent correctness
* perfect sandbox-level system call tracing
* distributed/shared remote caches
* cache portability across fundamentally different runtimes

The initial design should focus on local, practical, trustworthy caching.

---

## Core concept

Each executable block is treated as a small compilation unit.

A cache entry is valid only if all of the following are unchanged:

* normalized block source
* block type
* relevant block metadata
* mdcc/runtime version
* Python version
* parameter values used for the compile
* content of files read by the block

So the cache check is not:

* "did the block text change?"

It is:

* "did anything this block semantically depends on change?"

---

## High-level architecture

For each executable block, mdcc should persist:

1. **Static fingerprint**
2. **Dependency manifest**
3. **Cached semantic result**
4. **Rendered block artifact**
5. **Execution metadata**

Conceptually:

```text
.mdcc_cache/
  <block-cache-key>/
    manifest.json
    result.json
    rendered.html
    rendered.png
```

The exact serialization format is an implementation detail. The important point is that caching is **per block**, not per whole document.

---

## What should be part of the static fingerprint

The static fingerprint should include at least:

* normalized block source
* block type (e.g. `mdcc_table`, `mdcc_chart`)
* relevant block metadata (`caption`, `label`, later other rendering-affecting metadata)
* mdcc version
* execution prelude/runtime version hash
* Python version
* parameter values, when parameterization exists
* document path or document identity if path resolution depends on it

The purpose of the static fingerprint is to detect changes in the block definition itself.

---

## Dependency manifest

Each cache entry should store a manifest of dependencies discovered or declared for the block.

Example shape:

```json
{
  "dependencies": [
    {
      "path": "/abs/path/data/market-data.json",
      "kind": "file",
      "hash": "abc123"
    },
    {
      "path": "/abs/path/data/region-targets.csv",
      "kind": "file",
      "hash": "def456"
    }
  ]
}
```

The dependency manifest is used to determine whether the cached result is still valid on the next compile.

---

## Cache validity rule

A cache entry is valid if:

1. the static fingerprint matches
2. all dependency files still exist
3. all dependency file hashes still match

If any of these conditions fail, the block must be re-executed and the cache refreshed.

---

## Why block source alone is not enough

Consider a block like this:

```python
market = pd.read_json("data/market-data.json")
targets = pd.read_csv("data/region-targets.csv")

summary = pd.DataFrame({
    "metric": ["Market rows", "Regions"],
    "value": [len(market), market["region"].nunique()],
})

summary
```

If either input file changes, the block output changes even when the code itself does not.

Therefore, cache correctness requires tracking the effective input files and invalidating when they change.

---

## Dependency discovery strategy

There are three realistic models.

### 1. Runtime dependency tracking

During execution, mdcc records files read by the block.

This is the best initial approach because it requires no new syntax and works with existing documents.

Practical first version:

* wrap `open(...)`
* wrap common pandas readers such as:

  * `pd.read_csv`
  * `pd.read_json`
  * `pd.read_excel`
  * `pd.read_parquet`
* normalize paths to absolute paths
* record read accesses only

This does not need to be a perfect tracer on day one. It only needs to cover the common data-loading paths that matter most in mdcc.

### 2. Declared external inputs

Later, mdcc may optionally allow blocks to declare their input files explicitly.

Example direction:

````md
```mdcc_table inputs="data/market-data.json,data/region-targets.csv"
...
````

````

This enables:

- pre-validation of inputs
- clearer diagnostics
- stronger reproducibility
- cleaner future packaging
- more predictable cache behavior

This should be optional initially.

### 3. Hybrid model

Recommended long-term direction:

- automatic runtime dependency detection
- optional explicit input declaration

This provides good UX while still allowing stricter compiler behavior later.

---

## Recommended rollout

### Phase 1 — practical caching

Implement:

- persistent local cache directory
- per-block cache entries
- static fingerprinting
- runtime dependency tracking for file reads
- dependency hashing
- cache reuse when fingerprint and hashes match

This phase should require no new author-facing syntax.

### Phase 2 — declared inputs

Add:

- optional declared external input metadata
- pre-validation of missing inputs
- diagnostics that distinguish declared vs detected dependencies
- improved cache planning and explainability

### Phase 3 — maturity features

Potential later additions:

- configurable cache policy per block (`auto`, `off`)
- cache inspection/debug output
- selective cache invalidation
- remote/shared cache support
- stronger runtime restrictions for cacheable blocks

---

## Compile flow with caching

For each executable block:

1. Parse block.
2. Compute static fingerprint.
3. Look up cache entry.
4. If no cache entry exists:
   - execute block
   - track dependencies
   - hash dependencies
   - validate result
   - render block artifact
   - persist cache entry
5. If cache entry exists:
   - recompute dependency hashes
   - if all hashes match, reuse cached result/artifact
   - otherwise re-execute and refresh cache
6. Assemble final document using fresh or cached block artifacts.

---

## What gets cached

mdcc should cache at the **block result level**, not only the final document fragment.

### For table-like blocks

Cache:

- normalized result representation
- rendered fragment
- optionally raw tabular serialization

Possible internal formats:

- JSON
- Arrow
- Parquet
- HTML fragment

### For chart-like blocks

Cache:

- normalized chart representation/spec
- rendered image or vector artifact
- rendering metadata

Possible internal formats:

- JSON spec
- PNG
- SVG

This allows mdcc to skip both execution and rendering on a cache hit.

---

## Invalidation layers

There are three main invalidation layers.

### 1. Source invalidation

Invalidate when block code or rendering-relevant metadata changes.

### 2. Input invalidation

Invalidate when any dependency file changes.

### 3. Runtime invalidation

Invalidate when mdcc version, runtime prelude, or rendering/runtime environment changes in a meaningful way.

These three layers are sufficient for a strong first implementation.

---

## Parameterization interaction

If mdcc later supports parameterized documents, parameters become part of the effective block input.

Example:

```yaml
region: emea
````

and inside a block:

```python
pd.read_csv(f"data/{region}.csv")
```

Then the cache key must reflect:

* block source
* parameter values
* resolved dependency paths
* dependency content hashes

This is why caching should be designed around **effective inputs** from the start, even before parameterization is implemented.

---

## Non-file dependencies and limitations

Caching is harder to trust when blocks depend on things like:

* current time
* random numbers
* environment variables
* network calls
* hidden mutable external state

The initial policy should be simple:

* file-based dependencies: supported
* parameter dependencies: supported
* runtime/compiler version dependencies: supported
* ambient/non-deterministic dependencies: not guaranteed

For such blocks, mdcc may later support either:

* documented best-effort caching
* or a per-block option to disable caching

This does not need to be solved fully in the first version.

---

## Suggested internal data model

A cache entry may conceptually contain:

```json
{
  "block_id": "block-0001",
  "block_type": "mdcc_table",
  "static_fingerprint": "...",
  "dependencies": [
    {
      "path": "/abs/path/data/market-data.json",
      "hash": "..."
    },
    {
      "path": "/abs/path/data/region-targets.csv",
      "hash": "..."
    }
  ],
  "result": {
    "kind": "table"
  },
  "artifacts": {
    "rendered_html": "..."
  },
  "execution": {
    "duration_ms": 123.4,
    "cached": false
  }
}
```

This shape is illustrative only. The exact layout can evolve.

---

## Diagnostics and transparency

Even if mdcc does not implement JSON diagnostics, the caching system should eventually surface plain-text information such as:

* cache hit / miss per block
* why a cache entry was invalidated
* which dependencies were detected
* whether dependencies were declared or auto-detected

Examples:

* `block-0001: cache hit`
* `block-0002: cache miss (dependency changed: data/market-data.json)`
* `block-0003: cache miss (runtime changed)`

This is important for trust and debugging. Show it in the verbose mode.

---

## Recommendations

### Strong recommendation

Implement caching as:

* **persistent**
* **per-block**
* based on **effective input fingerprints**
* with **runtime dependency tracking** in phase 1

### Do not do this

Do not implement caching purely as:

* "same block source = reuse output"

That approach will be incorrect for many realistic mdcc documents.

### Best practical sequence

1. Add `.mdcc_cache/` or similar folder (analyze the current implementation if we can reuse something)
2. Cache per block
3. Track file reads during block execution
4. Hash dependencies
5. Reuse cached outputs when fingerprints and dependency hashes match
6. Later add optional explicit input declarations

---

## Summary

The caching model for mdcc should answer this question:

> Did anything this block semantically depends on change?

Not just:

> Did the code change?

For mdcc, the most important effective inputs are:

* block source
* block metadata
* parameters
* runtime/compiler version
* files read during execution

If caching is built around that model, mdcc will remain correct and extensible as it grows.

---

## Phase 1 Cache Implementation Plan

### Summary
Implement default-on, local, per-block caching for `mdcc` with a `--no-cache` escape hatch. Phase 1 caches successful block outputs and rendered block artifacts, tracks common local file reads at runtime, invalidates cache entries when execution-relevant inputs or tracked file content hashes change, and always rebuilds final document assembly/PDF fresh.

### Key Changes
- Add cache controls to the compile surface.
  - Add `use_cache: bool = True` to `CompileOptions`.
  - Add `--no-cache` to `mdcc compile`; it sets `use_cache=False`.
  - In verbose mode, print one line per executable block with `cache hit`, `cache miss`, or `cache bypassed`, plus the primary miss reason.

- Add a persistent cache subsystem stored adjacent to the source file as `.mdcc_cache/`.
  - Keep `.mdcc_build/` ephemeral and unchanged in purpose.
  - Scope cache entries to the execution root (`source_path.parent`).
  - Do not promise cache portability across moved projects, machines, or materially different runtimes in Phase 1.

- Model two cache concepts explicitly.
  - **Execution fingerprint** decides whether a block must re-execute.
  - **Artifact fingerprint** decides whether a rendered artifact can be reused.
  - Phase 1 may store both in the same manifest/entry, but the logic must keep them conceptually separate.

- Define the Phase 1 execution fingerprint.
  - Include:
    - block type
    - original block code
    - capture mode / epilogue identity
    - runtime prelude fingerprint
    - mdcc version
    - Python version
    - execution root scope
    - future parameter values placeholder, but no parameter behavior yet
  - Exclude:
    - `block_id`
    - `block_index`
    - `caption`
    - `label`
  - Do not hash the full Python environment in Phase 1.

- Define the Phase 1 artifact fingerprint.
  - Include:
    - execution fingerprint
    - renderer implementation fingerprint
    - artifact kind
  - Only include artifact-relevant metadata if it actually changes the block-local rendered artifact.
  - In Phase 1, captions/labels are applied later during document assembly, so they do not invalidate execution or block artifact reuse.

- Define the runtime fingerprint narrowly and deterministically.
  - Include:
    - mdcc version
    - Python version
    - runtime prelude fingerprint
    - renderer implementation fingerprint
  - Do not hash unrelated installed packages or the whole interpreter environment.

- Define the cache entry contents.
  - `manifest.json` with:
    - execution fingerprint
    - artifact fingerprint
    - block type
    - execution root
    - dependency list with absolute normalized path and content hash
    - cached result metadata
    - cached artifact filenames
    - execution metadata such as duration
  - For chart blocks: cache `spec.json` and `rendered.svg`.
  - For table blocks: cache a stable tabular JSON representation and `rendered.html`.
  - Cache only successful executions and successful typed-result validation.

- Add runtime dependency tracking for local filesystem reads.
  - Extend the fixed runtime prelude so each block writes a dependency log file alongside the existing result/log files.
  - Track reads via:
    - built-in `open`
    - `pd.read_csv`
    - `pd.read_json`
    - `pd.read_excel`
    - `pd.read_parquet`
  - Normalize paths to absolute resolved local paths under the execution root context.
  - Record read dependencies only.
  - Deduplicate dependency records before persisting.

- Define dependency validation semantics.
  - Correctness must rely on content hashes.
  - File size or mtime may be used only as internal fast checks; they must not be the source of truth for validity.
  - A cache entry is valid only if every tracked dependency still exists and its content hash matches.

- Define cache corruption and invalid entry handling.
  - Treat all of the following as cache misses, never compiler failures:
    - unreadable or invalid `manifest.json`
    - missing cached result/artifact files
    - malformed dependency records
    - missing dependency files
    - dependency hash mismatch
  - Behavior is always:
    - cache miss
    - recompute block
    - replace cache entry

- Change compile orchestration from “execute all then render all” to “resolve each block to an artifact”.
  - Keep parse and validation exactly as they are today.
  - For each executable block:
    - compute execution fingerprint
    - if `use_cache` is false, bypass lookup
    - if cache entry exists, validate manifest and dependency hashes
    - on valid hit, hydrate the cached chart/table artifact into a `RenderedArtifact` for the current parsed block
    - on miss, build payload, execute block, read dependency log, hash dependencies, validate typed result, render artifact, and persist the cache entry
  - After all blocks are resolved to artifacts, keep document assembly and PDF generation unchanged.

- Preserve current diagnostics and define Phase 1 trust boundaries.
  - Cache events are informational, not errors.
  - Existing execution, validation, rendering, and PDF diagnostics remain unchanged for uncached or invalidated blocks.
  - Phase 1 guarantees correct invalidation only for:
    - block source changes
    - runtime fingerprint changes
    - tracked local filesystem reads
  - Phase 1 does not guarantee correct invalidation for:
    - HTTP/network reads
    - time/randomness
    - environment variables
    - external services
    - hidden side effects

### Test Plan
- CLI and defaults:
  - `--no-cache` forwards `use_cache=False`.
  - cache is enabled by default when the flag is absent.
  - verbose compile output includes cache hit/miss/bypass lines.

- Fingerprint behavior:
  - identical block code and runtime fingerprint produce the same execution fingerprint across repeated runs.
  - changing only block order does not change the execution fingerprint.
  - changing only `caption` or `label` does not force re-execution.
  - changing renderer fingerprint invalidates artifact reuse but not execution identity.
  - changing runtime prelude, mdcc version, Python version, or execution root invalidates execution reuse.

- Dependency tracking:
  - `open("data.csv")` is recorded as an absolute dependency.
  - `pd.read_csv`, `pd.read_json`, `pd.read_excel`, and `pd.read_parquet` are recorded.
  - duplicate reads of the same file yield one dependency entry.

- Cache reuse and invalidation:
  - second compile with unchanged inputs skips subprocess execution for the cached block.
  - changing a tracked file’s contents invalidates the cache and re-executes.
  - deleting a tracked file invalidates the cache and re-executes.
  - `--no-cache` re-executes even when a valid cache entry exists.

- Artifact hydration:
  - chart hits reuse cached `rendered.svg`.
  - table hits reuse cached `rendered.html`.
  - final document assembly still reflects current caption/reference numbering after a cache hit.

- Corruption handling:
  - unreadable `manifest.json` is treated as a miss and refreshed.
  - missing cached artifact files are treated as a miss and refreshed.
  - malformed dependency records are treated as a miss and refreshed.

- Failure behavior:
  - execution errors, timeouts, and typed-result validation failures are not cached.
  - corrupted or incomplete cache entries never fail compilation by themselves.

### Assumptions and Defaults
- Cache is enabled by default; `--no-cache` is the only Phase 1 user control.
- Cache entries are scoped to the source directory / execution root.
- Phase 1 dependency tracking is best-effort for common local filesystem reads only.
- Content hashing is the correctness mechanism for dependency invalidation.
- Final document assembly and PDF generation always run fresh; Phase 1 only skips block execution and block-local rendering.
