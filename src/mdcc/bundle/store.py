from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from mdcc.errors import BundleError
from mdcc.models import (
    BundleBlockDatasetLink,
    BundleBlockRecord,
    BundleDatasetColumn,
    BundleDatasetRecord,
    BundleDocumentRecord,
    BundleMetaRecord,
    BundleModel,
    BundlePayloadRecord,
)

REQUIRED_TABLES = frozenset(
    {
        "bundle_meta",
        "documents",
        "blocks",
        "datasets",
        "dataset_columns",
        "block_datasets",
        "dataset_payloads",
    }
)


def write_bundle(path: Path, bundle: BundleModel) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    try:
        _create_schema(connection)
        _insert_bundle(connection, bundle)
        connection.commit()
    finally:
        connection.close()
    return path


def read_bundle(path: Path) -> BundleModel:
    connection = _open_bundle(path)
    connection.row_factory = sqlite3.Row
    try:
        meta_row = _fetch_one(connection, "SELECT * FROM bundle_meta")
        document_row = _fetch_one(connection, "SELECT * FROM documents")
        block_rows = connection.execute(
            """
            SELECT block_id, block_type, source_start_line, source_end_line, label, caption
            FROM blocks
            ORDER BY source_start_line, block_id
            """
        ).fetchall()
        dataset_rows = connection.execute(
            """
            SELECT dataset_id, name, format, role_summary, row_count, column_count,
                   source_kind, payload_id, fingerprint
            FROM datasets
            ORDER BY dataset_id
            """
        ).fetchall()
        column_rows = connection.execute(
            """
            SELECT dataset_id, ordinal, column_name, logical_type, nullable
            FROM dataset_columns
            ORDER BY dataset_id, ordinal
            """
        ).fetchall()
        block_dataset_rows = connection.execute(
            """
            SELECT block_id, dataset_id, role
            FROM block_datasets
            ORDER BY block_id, dataset_id, role
            """
        ).fetchall()
        payload_rows = connection.execute(
            "SELECT payload_id, blob_data FROM dataset_payloads ORDER BY payload_id"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise BundleError.from_exception(
            "invalid bundle: file is not a readable SQLite database",
            exc,
        ) from exc
    finally:
        connection.close()

    try:
        columns_by_dataset: dict[str, list[BundleDatasetColumn]] = {}
        for row in column_rows:
            columns_by_dataset.setdefault(row["dataset_id"], []).append(
                BundleDatasetColumn(
                    ordinal=row["ordinal"],
                    column_name=row["column_name"],
                    logical_type=row["logical_type"],
                    nullable=bool(row["nullable"]),
                )
            )
        return BundleModel(
            meta=BundleMetaRecord.model_validate(dict(meta_row)),
            document=BundleDocumentRecord.model_validate(dict(document_row)),
            blocks=[BundleBlockRecord.model_validate(dict(row)) for row in block_rows],
            datasets=[
                BundleDatasetRecord.model_validate(
                    {
                        **dict(row),
                        "columns": columns_by_dataset.get(row["dataset_id"], []),
                    }
                )
                for row in dataset_rows
            ],
            block_datasets=[
                BundleBlockDatasetLink.model_validate(dict(row))
                for row in block_dataset_rows
            ],
            dataset_payloads=[
                BundlePayloadRecord(
                    payload_id=row["payload_id"], blob_data=row["blob_data"]
                )
                for row in payload_rows
            ],
        )
    except PydanticValidationError as exc:
        raise BundleError.from_exception(
            "invalid bundle: stored row contents failed validation",
            exc,
        ) from exc


def list_tables(path: Path) -> set[str]:
    connection = _open_bundle(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {str(row[0]) for row in rows}
    except sqlite3.DatabaseError as exc:
        raise BundleError.from_exception(
            "invalid bundle: file is not a readable SQLite database",
            exc,
        ) from exc
    finally:
        connection.close()


def _open_bundle(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"file:{path}?mode=rw", uri=True)
    except sqlite3.Error as exc:
        raise BundleError.from_exception(
            "invalid bundle: file is not a readable SQLite database",
            exc,
        ) from exc


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE bundle_meta (
            format_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            mdcc_version TEXT NOT NULL,
            source_filename TEXT,
            source_sha256 TEXT NOT NULL
        );
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY,
            title TEXT,
            source_text TEXT NOT NULL
        );
        CREATE TABLE blocks (
            block_id TEXT PRIMARY KEY,
            block_type TEXT NOT NULL,
            source_start_line INTEGER NOT NULL,
            source_end_line INTEGER NOT NULL,
            label TEXT,
            caption TEXT
        );
        CREATE TABLE datasets (
            dataset_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            format TEXT NOT NULL,
            role_summary TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            source_kind TEXT NOT NULL,
            payload_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL
        );
        CREATE TABLE dataset_columns (
            dataset_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            logical_type TEXT NOT NULL,
            nullable INTEGER NOT NULL
        );
        CREATE TABLE block_datasets (
            block_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE dataset_payloads (
            payload_id TEXT PRIMARY KEY,
            blob_data BLOB NOT NULL
        );
        """
    )


def _insert_bundle(connection: sqlite3.Connection, bundle: BundleModel) -> None:
    connection.execute(
        """
        INSERT INTO bundle_meta (
            format_version, created_at, mdcc_version, source_filename, source_sha256
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            bundle.meta.format_version,
            bundle.meta.created_at,
            bundle.meta.mdcc_version,
            bundle.meta.source_filename,
            bundle.meta.source_sha256,
        ),
    )
    connection.execute(
        "INSERT INTO documents (document_id, title, source_text) VALUES (?, ?, ?)",
        (
            bundle.document.document_id,
            bundle.document.title,
            bundle.document.source_text,
        ),
    )
    connection.executemany(
        """
        INSERT INTO blocks (
            block_id, block_type, source_start_line, source_end_line, label, caption
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                block.block_id,
                block.block_type.value,
                block.source_start_line,
                block.source_end_line,
                block.label,
                block.caption,
            )
            for block in bundle.blocks
        ],
    )
    connection.executemany(
        """
        INSERT INTO dataset_payloads (payload_id, blob_data) VALUES (?, ?)
        """,
        [
            (payload.payload_id, payload.blob_data)
            for payload in bundle.dataset_payloads
        ],
    )
    connection.executemany(
        """
        INSERT INTO datasets (
            dataset_id, name, format, role_summary, row_count, column_count,
            source_kind, payload_id, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                dataset.dataset_id,
                dataset.name,
                dataset.format,
                dataset.role_summary,
                dataset.row_count,
                dataset.column_count,
                dataset.source_kind.value,
                dataset.payload_id,
                dataset.fingerprint,
            )
            for dataset in bundle.datasets
        ],
    )
    connection.executemany(
        """
        INSERT INTO dataset_columns (
            dataset_id, ordinal, column_name, logical_type, nullable
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                dataset.dataset_id,
                column.ordinal,
                column.column_name,
                column.logical_type,
                int(column.nullable),
            )
            for dataset in bundle.datasets
            for column in dataset.columns
        ],
    )
    connection.executemany(
        """
        INSERT INTO block_datasets (block_id, dataset_id, role) VALUES (?, ?, ?)
        """,
        [
            (link.block_id, link.dataset_id, link.role.value)
            for link in bundle.block_datasets
        ],
    )


def _fetch_one(connection: sqlite3.Connection, query: str) -> sqlite3.Row:
    row = connection.execute(query).fetchone()
    if row is None:
        raise BundleError.from_message("invalid bundle: missing required bundle row")
    return row
