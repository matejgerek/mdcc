from __future__ import annotations

import hashlib
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import altair as alt
import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from mdcc import __version__
from mdcc.executor.payload import capture_mode_for_source
from mdcc.executor.prelude import runtime_prelude_template
from mdcc.models import (
    ArtifactKind,
    BlockType,
    ChartResult,
    CompiledBlockRecord,
    ExecutableBlockNode,
    BlockExecutionResult,
    ExecutionPayload,
    ExecutionStatus,
    ExecutionStreams,
    ExecutionTiming,
    RenderedArtifact,
    RuntimeDatasetCapture,
    TableResult,
    TypedBlockResult,
)
from mdcc.renderers import render_chart_spec_artifact, render_table_frame_artifact
from mdcc.renderers.chart import render_chart_artifact
from mdcc.renderers.table import render_table_artifact
from mdcc.utils.workspace import BuildContext

CACHE_DIR_NAME = ".mdcc_cache"


class CacheDependency(BaseModel):
    path: str
    hash: str


class CacheManifest(BaseModel):
    execution_fingerprint: str
    artifact_fingerprint: str
    block_type: BlockType
    artifact_kind: ArtifactKind
    execution_root: str
    dependencies: list[CacheDependency] = Field(default_factory=list)
    semantic_filename: str
    rendered_filename: str
    mime_type: str
    duration_ms: float | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    columns: list[str] = Field(default_factory=list)
    dataset_manifest_filename: str = "dataset_manifest.json"
    dataset_payloads_dirname: str = "datasets"


@dataclass(frozen=True, slots=True)
class CacheResolution:
    artifact: RenderedArtifact | None
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class CacheCompiledResolution:
    compiled_record: CompiledBlockRecord | None
    status: str
    reason: str


class CacheStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_source(cls, source_path: Path) -> CacheStore:
        return cls(source_path.parent / CACHE_DIR_NAME)

    def resolve_artifact(
        self,
        *,
        payload: ExecutionPayload,
        build_context: BuildContext,
    ) -> CacheResolution:
        compiled = self.resolve_compiled_record(
            payload=payload,
            build_context=build_context,
        )
        artifact = (
            compiled.compiled_record.rendered_artifact
            if compiled.compiled_record is not None
            else None
        )
        return CacheResolution(artifact, compiled.status, compiled.reason)

    def resolve_compiled_record(
        self,
        *,
        payload: ExecutionPayload,
        build_context: BuildContext,
    ) -> CacheCompiledResolution:
        execution_fingerprint = build_execution_fingerprint(payload)
        artifact_fingerprint = build_artifact_fingerprint(
            execution_fingerprint=execution_fingerprint,
            artifact_kind=_artifact_kind(payload.block.block_type),
        )
        manifest = self._read_manifest(execution_fingerprint)
        if manifest is None:
            return CacheCompiledResolution(None, "miss", "cache entry missing")

        if manifest.execution_fingerprint != execution_fingerprint:
            return CacheCompiledResolution(
                None, "miss", "execution fingerprint changed"
            )

        if manifest.block_type is not payload.block.block_type:
            return CacheCompiledResolution(None, "miss", "block type changed")

        dependency_error = self._validate_dependencies(manifest)
        if dependency_error is not None:
            return CacheCompiledResolution(None, "miss", dependency_error)

        semantic = self._load_semantic_result(
            manifest=manifest,
            block=payload.block,
            execution_fingerprint=execution_fingerprint,
        )
        if semantic is None:
            return CacheCompiledResolution(
                None, "miss", "cached semantic result missing"
            )

        rendered_path = self._rendered_path(execution_fingerprint, manifest)
        dataset_captures = self._materialize_dataset_captures(
            payload=payload,
            manifest=manifest,
            execution_fingerprint=execution_fingerprint,
            build_context=build_context,
        )
        if (
            manifest.artifact_fingerprint == artifact_fingerprint
            and rendered_path.exists()
        ):
            artifact = self._materialize_cached_artifact(
                payload=payload,
                manifest=manifest,
                rendered_path=rendered_path,
                build_context=build_context,
            )
            self._write_cache_log(
                payload=payload,
                status="hit",
                reason="artifact reused",
                dependencies=manifest.dependencies,
            )
            return CacheCompiledResolution(
                self._compiled_record_from_cache(
                    payload=payload,
                    semantic=semantic,
                    artifact=artifact,
                    manifest=manifest,
                    dataset_captures=dataset_captures,
                ),
                "hit",
                "artifact reused",
            )

        artifact = self._render_semantic_result(
            semantic=semantic,
            build_context=build_context,
        )
        self._persist_rendered_artifact(execution_fingerprint, manifest, artifact)
        manifest.artifact_fingerprint = artifact_fingerprint
        self._write_manifest(execution_fingerprint, manifest)
        self._write_cache_log(
            payload=payload,
            status="hit",
            reason="artifact refreshed",
            dependencies=manifest.dependencies,
        )
        return CacheCompiledResolution(
            self._compiled_record_from_cache(
                payload=payload,
                semantic=semantic,
                artifact=artifact,
                manifest=manifest,
                dataset_captures=dataset_captures,
            ),
            "hit",
            "artifact refreshed",
        )

    def store_typed_result(
        self,
        *,
        payload: ExecutionPayload,
        execution_result: BlockExecutionResult,
        result: TypedBlockResult,
        artifact: RenderedArtifact,
        dependencies: list[CacheDependency],
        dataset_captures: list[RuntimeDatasetCapture],
    ) -> None:
        execution_fingerprint = build_execution_fingerprint(payload)
        artifact_kind = (
            ArtifactKind.CHART
            if isinstance(result, ChartResult)
            else ArtifactKind.TABLE
        )
        manifest = CacheManifest(
            execution_fingerprint=execution_fingerprint,
            artifact_fingerprint=build_artifact_fingerprint(
                execution_fingerprint=execution_fingerprint,
                artifact_kind=artifact_kind,
            ),
            block_type=payload.block.block_type,
            artifact_kind=artifact_kind,
            execution_root=str(payload.execution_cwd.resolve()),
            dependencies=dependencies,
            semantic_filename=_semantic_filename(artifact_kind),
            rendered_filename=_rendered_filename(artifact_kind),
            mime_type=artifact.mime_type or _default_mime_type(artifact_kind),
            duration_ms=execution_result.timing.duration_ms,
            rows=result.rows if isinstance(result, TableResult) else None,
            columns=result.columns if isinstance(result, TableResult) else [],
        )

        entry_dir = self._entry_dir(execution_fingerprint)
        entry_dir.mkdir(parents=True, exist_ok=True)
        self._persist_semantic_result(execution_fingerprint, result)
        self._persist_rendered_artifact(execution_fingerprint, manifest, artifact)
        self._persist_dataset_captures(
            execution_fingerprint=execution_fingerprint,
            manifest=manifest,
            dataset_captures=dataset_captures,
        )
        self._write_manifest(execution_fingerprint, manifest)

    def _validate_dependencies(self, manifest: CacheManifest) -> str | None:
        for dependency in manifest.dependencies:
            try:
                path = Path(dependency.path)
            except TypeError:
                return "dependency metadata invalid"

            if not path.exists():
                return f"dependency missing: {dependency.path}"
            if _hash_file(path) != dependency.hash:
                return f"dependency changed: {dependency.path}"
        return None

    def _load_semantic_result(
        self,
        *,
        manifest: CacheManifest,
        block: ExecutableBlockNode,
        execution_fingerprint: str,
    ) -> TypedBlockResult | None:
        semantic_path = self._semantic_path(execution_fingerprint, manifest)
        try:
            if manifest.artifact_kind is ArtifactKind.CHART:
                spec = json.loads(semantic_path.read_text(encoding="utf-8"))
                if not isinstance(spec, dict):
                    return None
                chart = alt.Chart.from_dict(spec)
                return ChartResult(block=block, value=chart, spec=spec)

            frame = pd.read_pickle(semantic_path)
            return TableResult(block=block, value=frame)
        except Exception:
            return None

    def _render_semantic_result(
        self,
        *,
        semantic: TypedBlockResult,
        build_context: BuildContext,
    ) -> RenderedArtifact:
        if isinstance(semantic, ChartResult):
            return render_chart_spec_artifact(
                block=semantic.block,
                spec=semantic.spec,
                build_context=build_context,
            )
        return render_table_frame_artifact(
            block=semantic.block,
            frame=semantic.value,
            build_context=build_context,
        )

    def _materialize_cached_artifact(
        self,
        *,
        payload: ExecutionPayload,
        manifest: CacheManifest,
        rendered_path: Path,
        build_context: BuildContext,
    ) -> RenderedArtifact:
        target_path = (
            build_context.chart_path(payload.block.block_index, ".svg")
            if manifest.artifact_kind is ArtifactKind.CHART
            else build_context.table_path(payload.block.block_index, ".html")
        )
        target_path.write_bytes(rendered_path.read_bytes())
        payload.dependency_path.write_text(
            json.dumps([dependency.path for dependency in manifest.dependencies]),
            encoding="utf-8",
        )

        if manifest.artifact_kind is ArtifactKind.CHART:
            return RenderedArtifact(
                artifact_id=f"chart-{payload.block.node_id}",
                kind=ArtifactKind.CHART,
                block=payload.block,
                path=target_path,
                mime_type="image/svg+xml",
            )

        html = target_path.read_text(encoding="utf-8")
        return RenderedArtifact(
            artifact_id=f"table-{payload.block.node_id}",
            kind=ArtifactKind.TABLE,
            block=payload.block,
            path=target_path,
            html=html,
            mime_type="text/html",
        )

    def _persist_semantic_result(
        self,
        execution_fingerprint: str,
        result: TypedBlockResult,
    ) -> None:
        entry_dir = self._entry_dir(execution_fingerprint)
        entry_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(result, ChartResult):
            self._semantic_path(
                execution_fingerprint,
                CacheManifest(
                    execution_fingerprint=execution_fingerprint,
                    artifact_fingerprint="",
                    block_type=result.block.block_type,
                    artifact_kind=ArtifactKind.CHART,
                    execution_root="",
                    semantic_filename=_semantic_filename(ArtifactKind.CHART),
                    rendered_filename="",
                    mime_type="image/svg+xml",
                ),
            ).write_text(json.dumps(result.spec, sort_keys=True), encoding="utf-8")
            return

        result.value.to_pickle(
            self._semantic_path(
                execution_fingerprint,
                CacheManifest(
                    execution_fingerprint=execution_fingerprint,
                    artifact_fingerprint="",
                    block_type=result.block.block_type,
                    artifact_kind=ArtifactKind.TABLE,
                    execution_root="",
                    semantic_filename=_semantic_filename(ArtifactKind.TABLE),
                    rendered_filename="",
                    mime_type="text/html",
                ),
            ),
        )

    def _persist_rendered_artifact(
        self,
        execution_fingerprint: str,
        manifest: CacheManifest,
        artifact: RenderedArtifact,
    ) -> None:
        rendered_path = self._rendered_path(execution_fingerprint, manifest)
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        if artifact.kind is ArtifactKind.CHART:
            if artifact.path is None:
                msg = "chart artifact is missing its path"
                raise ValueError(msg)
            rendered_path.write_bytes(artifact.path.read_bytes())
            return

        if artifact.html is None:
            msg = "table artifact is missing its HTML"
            raise ValueError(msg)
        rendered_path.write_text(artifact.html, encoding="utf-8")

    def _read_manifest(self, execution_fingerprint: str) -> CacheManifest | None:
        manifest_path = self._entry_dir(execution_fingerprint) / "manifest.json"
        try:
            return CacheManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, OSError, ValidationError, json.JSONDecodeError):
            return None

    def _write_manifest(
        self, execution_fingerprint: str, manifest: CacheManifest
    ) -> None:
        manifest_path = self._entry_dir(execution_fingerprint) / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _persist_dataset_captures(
        self,
        *,
        execution_fingerprint: str,
        manifest: CacheManifest,
        dataset_captures: list[RuntimeDatasetCapture],
    ) -> None:
        entry_dir = self._entry_dir(execution_fingerprint)
        payload_dir = entry_dir / manifest.dataset_payloads_dirname
        payload_dir.mkdir(parents=True, exist_ok=True)

        normalized: list[dict[str, str | int | None]] = []
        for capture in dataset_captures:
            target_path = payload_dir / f"dataset_{capture.ordinal:03d}.parquet"
            target_path.write_bytes(capture.payload_path.read_bytes())
            normalized.append(
                {
                    "ordinal": capture.ordinal,
                    "source_kind": capture.source_kind.value,
                    "source_path": capture.source_path,
                    "payload_path": str(target_path),
                }
            )

        (entry_dir / manifest.dataset_manifest_filename).write_text(
            json.dumps(normalized, indent=2),
            encoding="utf-8",
        )

    def _materialize_dataset_captures(
        self,
        *,
        payload: ExecutionPayload,
        manifest: CacheManifest,
        execution_fingerprint: str,
        build_context: BuildContext,
    ) -> list[RuntimeDatasetCapture]:
        manifest_path = (
            self._entry_dir(execution_fingerprint) / manifest.dataset_manifest_filename
        )
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return []

        captures: list[RuntimeDatasetCapture] = []
        if not isinstance(raw, list):
            return captures

        for item in raw:
            if not isinstance(item, dict):
                continue
            payload_path = item.get("payload_path")
            ordinal = item.get("ordinal")
            if not isinstance(payload_path, str) or not isinstance(ordinal, int):
                continue
            source_path = item.get("source_path")
            source_kind = item.get("source_kind")
            if not isinstance(source_kind, str):
                continue
            source_cache_path = Path(payload_path)
            if not source_cache_path.exists():
                continue
            target_path = (
                build_context.dataset_payload_dir(payload.block.block_index)
                / f"dataset_{ordinal:03d}.parquet"
            )
            target_path.write_bytes(source_cache_path.read_bytes())
            captures.append(
                RuntimeDatasetCapture.model_validate(
                    {
                        "ordinal": ordinal,
                        "source_kind": source_kind,
                        "source_path": source_path
                        if isinstance(source_path, str)
                        else None,
                        "payload_path": str(target_path),
                    }
                )
            )
        return captures

    def _compiled_record_from_cache(
        self,
        *,
        payload: ExecutionPayload,
        semantic: TypedBlockResult,
        artifact: RenderedArtifact,
        manifest: CacheManifest,
        dataset_captures: list[RuntimeDatasetCapture],
    ) -> CompiledBlockRecord:
        execution_result = BlockExecutionResult(
            block=payload.block,
            status=ExecutionStatus.SUCCESS,
            streams=ExecutionStreams(),
            timing=ExecutionTiming(duration_ms=manifest.duration_ms),
            raw_value=semantic.value,
            raw_type_name=type(semantic.value).__name__,
        )
        return CompiledBlockRecord(
            payload=payload,
            execution_result=execution_result,
            typed_result=semantic,
            dependencies=manifest.dependencies,
            dataset_captures=dataset_captures,
            rendered_artifact=artifact,
        )

    def _entry_dir(self, execution_fingerprint: str) -> Path:
        return self.root / execution_fingerprint

    def _semantic_path(
        self, execution_fingerprint: str, manifest: CacheManifest
    ) -> Path:
        return self._entry_dir(execution_fingerprint) / manifest.semantic_filename

    def _rendered_path(
        self, execution_fingerprint: str, manifest: CacheManifest
    ) -> Path:
        return self._entry_dir(execution_fingerprint) / manifest.rendered_filename

    def _write_cache_log(
        self,
        *,
        payload: ExecutionPayload,
        status: str,
        reason: str,
        dependencies: list[CacheDependency],
    ) -> None:
        lines = [
            f"block_id: {payload.block.node_id}",
            f"block_index: {payload.block.block_index}",
            f"block_type: {payload.block.block_type.value}",
            f"cache_status: {status}",
            f"cache_reason: {reason}",
            f"cwd: {payload.execution_cwd}",
            "dependencies:",
        ]
        lines.extend(dependency.path for dependency in dependencies)
        payload.log_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_execution_fingerprint(payload: ExecutionPayload) -> str:
    material = {
        "block_type": payload.block.block_type.value,
        "code": payload.block.code,
        "capture_mode": capture_mode_for_source(payload.block.code),
        "capture_datasets": payload.capture_datasets,
        "runtime_prelude_fingerprint": _hash_text(runtime_prelude_template()),
        "mdcc_version": __version__,
        "python_version": _python_version(),
        "execution_root": str(payload.execution_cwd.resolve()),
    }
    return _hash_text(json.dumps(material, sort_keys=True))


def build_artifact_fingerprint(
    *,
    execution_fingerprint: str,
    artifact_kind: ArtifactKind,
) -> str:
    material = {
        "execution_fingerprint": execution_fingerprint,
        "artifact_kind": artifact_kind.value,
        "renderer_fingerprint": _renderer_fingerprint(),
    }
    return _hash_text(json.dumps(material, sort_keys=True))


def load_dependency_hashes(dependency_path: Path) -> list[CacheDependency]:
    try:
        raw = json.loads(dependency_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []

    if not isinstance(raw, list):
        return []

    dependencies: list[CacheDependency] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        resolved = str(Path(item).expanduser().resolve())
        if resolved in seen:
            continue
        path = Path(resolved)
        if not path.exists() or not path.is_file():
            continue
        dependencies.append(CacheDependency(path=resolved, hash=_hash_file(path)))
        seen.add(resolved)
    return dependencies


def _artifact_kind(block_type: BlockType) -> ArtifactKind:
    return ArtifactKind.CHART if block_type is BlockType.CHART else ArtifactKind.TABLE


def _default_mime_type(kind: ArtifactKind) -> str:
    return "image/svg+xml" if kind is ArtifactKind.CHART else "text/html"


def _semantic_filename(kind: ArtifactKind) -> str:
    return "spec.json" if kind is ArtifactKind.CHART else "table.pkl"


def _rendered_filename(kind: ArtifactKind) -> str:
    return "rendered.svg" if kind is ArtifactKind.CHART else "rendered.html"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _renderer_fingerprint() -> str:
    material = "\n".join(
        [
            inspect.getsource(render_chart_artifact),
            inspect.getsource(render_chart_spec_artifact),
            inspect.getsource(render_table_artifact),
            inspect.getsource(render_table_frame_artifact),
        ]
    )
    return _hash_text(material)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_duration_ms(log_path: Path) -> float | None:
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("duration_ms: "):
            try:
                return float(line.removeprefix("duration_ms: "))
            except ValueError:
                return None
    return None


__all__ = [
    "CACHE_DIR_NAME",
    "CacheCompiledResolution",
    "CacheDependency",
    "CacheManifest",
    "CacheResolution",
    "CacheStore",
    "build_artifact_fingerprint",
    "build_execution_fingerprint",
    "load_dependency_hashes",
]
