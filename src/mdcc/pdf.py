from __future__ import annotations

from pathlib import Path

from mdcc.errors import ErrorContext, PdfGenerationError
from mdcc.models import IntermediateDocument


def generate_pdf(document: IntermediateDocument, output_path: Path) -> Path:
    """Generate a PDF file from an intermediate HTML document."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        html_class = _load_weasyprint_html()
        html_class(
            string=document.html,
            base_url=str(document.base_path),
        ).write_pdf(output_path)
    except Exception as exc:
        _remove_partial_output(output_path)
        raise PdfGenerationError.from_exception(
            "failed to generate PDF output",
            exc,
            context=ErrorContext(source_path=document.source_path),
        ) from exc

    if not output_path.exists():
        raise PdfGenerationError.from_message(
            "PDF output was not created",
            context=ErrorContext(source_path=document.source_path),
        )

    if output_path.stat().st_size == 0:
        _remove_partial_output(output_path)
        raise PdfGenerationError.from_message(
            "PDF output is empty",
            context=ErrorContext(source_path=document.source_path),
        )

    return output_path


def _remove_partial_output(output_path: Path) -> None:
    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        pass


def _load_weasyprint_html():
    from weasyprint import HTML  # type: ignore[import-untyped]

    return HTML


__all__ = ["generate_pdf"]
