from __future__ import annotations

from mdcc.models import Diagnostic


class MdccError(Exception):
    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class ReadError(MdccError):
    pass


class ParseError(MdccError):
    pass


class ValidationError(MdccError):
    pass


class ExecutionError(MdccError):
    pass


class TimeoutError(MdccError):
    pass


class RenderingError(MdccError):
    pass


class PdfGenerationError(MdccError):
    pass


__all__ = [
    "ExecutionError",
    "MdccError",
    "ParseError",
    "PdfGenerationError",
    "ReadError",
    "RenderingError",
    "TimeoutError",
    "ValidationError",
]
