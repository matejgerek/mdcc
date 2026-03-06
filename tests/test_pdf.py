from __future__ import annotations

from pathlib import Path

import pytest

from mdcc.errors import PdfGenerationError
from mdcc.models import Frontmatter, IntermediateDocument
from mdcc import pdf as pdf_module
from mdcc.pdf import generate_pdf


def _intermediate_document(tmp_path: Path) -> IntermediateDocument:
    source = tmp_path / "report.md"
    source.write_text("# source\n", encoding="utf-8")
    return IntermediateDocument(
        source_path=source,
        frontmatter=Frontmatter(title="Report"),
        html=(
            "<!DOCTYPE html>"
            "<html><head><title>Report</title></head>"
            "<body><h1>Report</h1><p>Hello PDF</p></body></html>"
        ),
        base_path=tmp_path,
    )


def test_generate_pdf_writes_non_empty_pdf_and_creates_parent_directory(
    tmp_path: Path,
) -> None:
    try:
        pdf_module._load_weasyprint_html()
    except Exception as exc:
        pytest.skip(f"WeasyPrint runtime unavailable: {exc}")

    document = _intermediate_document(tmp_path)
    output_path = tmp_path / "nested" / "report.pdf"

    result = generate_pdf(document, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"%PDF")


def test_generate_pdf_passes_base_url_to_weasyprint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _intermediate_document(tmp_path)
    output_path = tmp_path / "captured.pdf"
    captured: dict[str, str] = {}

    class FakeHTML:
        def __init__(self, *, string: str, base_url: str) -> None:
            captured["string"] = string
            captured["base_url"] = base_url

        def write_pdf(self, target: Path) -> None:
            target.write_bytes(b"%PDF-FAKE")

    monkeypatch.setattr("mdcc.pdf._load_weasyprint_html", lambda: FakeHTML)

    generate_pdf(document, output_path)

    assert captured["string"] == document.html
    assert captured["base_url"] == str(document.base_path)


def test_generate_pdf_wraps_weasyprint_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _intermediate_document(tmp_path)
    output_path = tmp_path / "failed.pdf"

    class FakeHTML:
        def __init__(self, *, string: str, base_url: str) -> None:
            self.string = string
            self.base_url = base_url

        def write_pdf(self, target: Path) -> None:
            raise RuntimeError("renderer exploded")

    monkeypatch.setattr("mdcc.pdf._load_weasyprint_html", lambda: FakeHTML)

    with pytest.raises(PdfGenerationError) as exc_info:
        generate_pdf(document, output_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "failed to generate PDF output"
    assert diagnostic.source_path == document.source_path
    assert diagnostic.exception_type == "RuntimeError"
    assert diagnostic.exception_message == "renderer exploded"


def test_generate_pdf_cleans_up_partial_output_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _intermediate_document(tmp_path)
    output_path = tmp_path / "partial.pdf"

    class FakeHTML:
        def __init__(self, *, string: str, base_url: str) -> None:
            self.string = string
            self.base_url = base_url

        def write_pdf(self, target: Path) -> None:
            target.write_bytes(b"%PDF-partial")
            raise RuntimeError("write interrupted")

    monkeypatch.setattr("mdcc.pdf._load_weasyprint_html", lambda: FakeHTML)

    with pytest.raises(PdfGenerationError):
        generate_pdf(document, output_path)

    assert not output_path.exists()


def test_generate_pdf_raises_when_output_is_missing_after_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _intermediate_document(tmp_path)
    output_path = tmp_path / "missing.pdf"

    class FakeHTML:
        def __init__(self, *, string: str, base_url: str) -> None:
            self.string = string
            self.base_url = base_url

        def write_pdf(self, target: Path) -> None:
            return None

    monkeypatch.setattr("mdcc.pdf._load_weasyprint_html", lambda: FakeHTML)

    with pytest.raises(PdfGenerationError) as exc_info:
        generate_pdf(document, output_path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.message == "PDF output was not created"
    assert diagnostic.source_path == document.source_path
