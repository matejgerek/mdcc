from __future__ import annotations

from datetime import date as date_type
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar

import altair as alt
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlockType(StrEnum):
    CHART = "mdcc_chart"
    TABLE = "mdcc_table"


class NodeKind(StrEnum):
    MARKDOWN = "markdown"
    EXECUTABLE_BLOCK = "executable_block"
    RENDERED_ARTIFACT = "rendered_artifact"


class ExecutionStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class DiagnosticStage(StrEnum):
    READ = "read"
    PARSE = "parse"
    VALIDATION = "validation"
    EXECUTION = "execution"
    TIMEOUT = "timeout"
    RENDERING = "rendering"
    PDF = "pdf"
    BUNDLE = "bundle"
    INSPECTION = "inspection"
    SQL = "sql"


class DiagnosticCategory(StrEnum):
    PARSE_ERROR = "parse_error"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT_ERROR = "timeout_error"
    VALIDATION_ERROR = "validation_error"
    RENDERING_ERROR = "rendering_error"
    PDF_ERROR = "pdf_error"
    READ_ERROR = "read_error"
    BUNDLE_ERROR = "bundle_error"
    BUNDLE_VALIDATION_ERROR = "bundle_validation_error"
    INSPECTION_ERROR = "inspection_error"
    SQL_ERROR = "sql_error"


class ArtifactKind(StrEnum):
    CHART = "chart"
    TABLE = "table"


class BundleDatasetRole(StrEnum):
    INPUT = "input"
    PRIMARY = "primary"
    SUPPORTING = "supporting"


class DatasetSourceKind(StrEnum):
    READ_CSV = "read_csv"
    READ_JSON = "read_json"
    READ_EXCEL = "read_excel"
    READ_PARQUET = "read_parquet"
    RENDER_PRIMARY = "render_primary"
    MANUAL_PERSIST = "manual_persist"


class BundleOutputKind(StrEnum):
    CHART_SPEC = "chart_spec"
    TABLE_FRAME = "table_frame"


class BundleOutputFormat(StrEnum):
    VEGA_JSON = "vega_json"
    PARQUET = "parquet"


class SourcePosition(BaseModel):
    line: int = Field(ge=1)
    column: int = Field(ge=1, default=1)
    offset: int | None = Field(default=None, ge=0)


class SourceSpan(BaseModel):
    start: SourcePosition
    end: SourcePosition

    @model_validator(mode="after")
    def validate_position_order(self) -> SourceSpan:
        if (self.end.line, self.end.column) < (self.start.line, self.start.column):
            msg = "source span end must not be before start"
            raise ValueError(msg)
        return self


class SourceLocation(BaseModel):
    source_path: Path
    span: SourceSpan | None = None
    snippet: str | None = None


class Frontmatter(BaseModel):
    title: str | None = None
    author: str | None = None
    date: date_type | str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def collect_extra_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        known_fields = {"title", "author", "date", "extra"}
        normalized = {key: value for key, value in data.items() if key in known_fields}
        normalized["extra"] = {
            key: value for key, value in data.items() if key not in known_fields
        }
        return normalized


class BaseNode(BaseModel):
    node_id: str
    location: SourceLocation | None = None


class BlockMetadata(BaseModel):
    caption: str | None = None
    label: str | None = None


class MarkdownNode(BaseNode):
    kind: NodeKind = Field(default=NodeKind.MARKDOWN)
    text: str


class ExecutableBlockNode(BaseNode):
    kind: NodeKind = Field(default=NodeKind.EXECUTABLE_BLOCK)
    block_type: BlockType
    code: str
    block_index: int = Field(ge=0)
    metadata: BlockMetadata = Field(default_factory=BlockMetadata)
    raw_metadata: tuple[tuple[str, str], ...] = Field(default_factory=tuple)


DocumentNode = MarkdownNode | ExecutableBlockNode


class DocumentModel(BaseModel):
    source_path: Path
    frontmatter: Frontmatter | None = None
    nodes: list[DocumentNode] = Field(default_factory=list)


class SourceDocumentInput(BaseModel):
    source_path: Path
    raw_text: str
    body_text: str
    frontmatter_text: str | None = None
    frontmatter: Frontmatter | None = None


class ExecutionTiming(BaseModel):
    duration_ms: float | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)


class ExecutionStreams(BaseModel):
    stdout: str = ""
    stderr: str = ""


class BlockExecutionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    block: ExecutableBlockNode
    status: ExecutionStatus
    streams: ExecutionStreams = Field(default_factory=ExecutionStreams)
    timing: ExecutionTiming = Field(default_factory=ExecutionTiming)
    raw_value: Any = None
    raw_type_name: str | None = None


class ExecutionPayload(BaseModel):
    block: ExecutableBlockNode
    capture_datasets: bool = False
    script_text: str
    script_path: Path
    result_path: Path
    dependency_path: Path
    dataset_manifest_path: Path
    dataset_payloads_dir: Path
    log_path: Path
    execution_cwd: Path


class ChartResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category: ArtifactKind = Field(default=ArtifactKind.CHART)
    block: ExecutableBlockNode
    value: (
        alt.Chart
        | alt.LayerChart
        | alt.ConcatChart
        | alt.HConcatChart
        | alt.VConcatChart
    )
    spec: dict[str, Any]


class TableResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    category: ArtifactKind = Field(default=ArtifactKind.TABLE)
    block: ExecutableBlockNode
    value: pd.DataFrame
    rows: int = Field(default=0, ge=0)
    columns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_shape_metadata(self) -> TableResult:
        self.rows = len(self.value.index)
        self.columns = [str(column) for column in self.value.columns]
        return self


TypedBlockResult = ChartResult | TableResult


class RenderedArtifact(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    block: ExecutableBlockNode
    path: Path | None = None
    html: str | None = None
    mime_type: str | None = None


class AssembledDocumentNode(BaseModel):
    kind: NodeKind
    markdown: MarkdownNode | None = None
    artifact: RenderedArtifact | None = None

    @model_validator(mode="after")
    def validate_single_payload(self) -> AssembledDocumentNode:
        payload_count = int(self.markdown is not None) + int(self.artifact is not None)
        if payload_count != 1:
            msg = "assembled document node must contain exactly one payload"
            raise ValueError(msg)
        return self


class AssembledDocument(BaseModel):
    source_path: Path
    frontmatter: Frontmatter | None = None
    nodes: list[AssembledDocumentNode] = Field(default_factory=list)


class IntermediateDocument(BaseModel):
    source_path: Path
    frontmatter: Frontmatter | None = None
    html: str
    base_path: Path


class ValidationIssue(BaseModel):
    severity: ValidationSeverity
    code: str
    message: str
    location: SourceLocation | None = None


T = TypeVar("T")


class ValidationResult(BaseModel, Generic[T]):
    ok: bool
    value: T | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)


class Diagnostic(BaseModel):
    stage: DiagnosticStage
    category: DiagnosticCategory
    message: str
    source_path: Path | None = None
    block_id: str | None = None
    block_type: BlockType | None = None
    block_index: int | None = Field(default=None, ge=0)
    location: SourceLocation | None = None
    source_snippet: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    stack_trace: str | None = None
    expected_output_type: str | None = None
    actual_output_type: str | None = None
    duration_ms: float | None = Field(default=None, ge=0)


class RuntimeDatasetCapture(BaseModel):
    ordinal: int = Field(ge=0)
    source_kind: DatasetSourceKind
    source_path: str | None = None
    payload_path: Path


class BundleDatasetColumn(BaseModel):
    ordinal: int = Field(ge=0)
    column_name: str
    logical_type: str
    nullable: bool


class BundleDatasetRecord(BaseModel):
    dataset_id: str
    name: str
    format: str
    role_summary: str
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    source_kind: DatasetSourceKind
    payload_id: str
    fingerprint: str
    columns: list[BundleDatasetColumn] = Field(default_factory=list)


class BundleBlockDatasetLink(BaseModel):
    block_id: str
    dataset_id: str
    role: BundleDatasetRole


class BundleBlockRecord(BaseModel):
    block_id: str
    block_type: BlockType
    source_start_line: int = Field(ge=1)
    source_end_line: int = Field(ge=1)
    label: str | None = None
    caption: str | None = None


class BundleDocumentRecord(BaseModel):
    document_id: str
    title: str | None = None
    source_text: str


class BundleMetaRecord(BaseModel):
    format_version: str
    created_at: str
    mdcc_version: str
    source_filename: str | None = None
    source_sha256: str


class BundlePayloadRecord(BaseModel):
    payload_id: str
    blob_data: bytes


class BundleBlockOutputRecord(BaseModel):
    block_id: str
    output_kind: BundleOutputKind
    format: BundleOutputFormat
    payload_id: str


class BundleOutputPayloadRecord(BaseModel):
    payload_id: str
    blob_data: bytes


class BundleModel(BaseModel):
    meta: BundleMetaRecord
    document: BundleDocumentRecord
    blocks: list[BundleBlockRecord] = Field(default_factory=list)
    datasets: list[BundleDatasetRecord] = Field(default_factory=list)
    block_datasets: list[BundleBlockDatasetLink] = Field(default_factory=list)
    dataset_payloads: list[BundlePayloadRecord] = Field(default_factory=list)
    block_outputs: list[BundleBlockOutputRecord] = Field(default_factory=list)
    output_payloads: list[BundleOutputPayloadRecord] = Field(default_factory=list)


class CompiledBlockRecord(BaseModel):
    payload: ExecutionPayload
    execution_result: BlockExecutionResult
    typed_result: TypedBlockResult
    dependencies: list[Any] = Field(default_factory=list)
    dataset_captures: list[RuntimeDatasetCapture] = Field(default_factory=list)
    rendered_artifact: RenderedArtifact | None = None


__all__ = [
    "ArtifactKind",
    "AssembledDocument",
    "AssembledDocumentNode",
    "BaseNode",
    "BlockMetadata",
    "BlockExecutionResult",
    "BundleBlockOutputRecord",
    "BundleBlockDatasetLink",
    "BundleBlockRecord",
    "BundleDatasetColumn",
    "BundleDatasetRecord",
    "BundleDatasetRole",
    "BundleDocumentRecord",
    "BundleMetaRecord",
    "BundleModel",
    "BundleOutputFormat",
    "BundleOutputKind",
    "BundleOutputPayloadRecord",
    "BundlePayloadRecord",
    "BlockType",
    "ChartResult",
    "CompiledBlockRecord",
    "Diagnostic",
    "DiagnosticCategory",
    "DiagnosticStage",
    "DatasetSourceKind",
    "DocumentModel",
    "DocumentNode",
    "ExecutionPayload",
    "ExecutableBlockNode",
    "ExecutionStatus",
    "ExecutionStreams",
    "ExecutionTiming",
    "Frontmatter",
    "IntermediateDocument",
    "MarkdownNode",
    "NodeKind",
    "RenderedArtifact",
    "RuntimeDatasetCapture",
    "SourceLocation",
    "SourceDocumentInput",
    "SourcePosition",
    "SourceSpan",
    "TableResult",
    "TypedBlockResult",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
]
