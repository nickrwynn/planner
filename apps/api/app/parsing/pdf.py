from __future__ import annotations

from dataclasses import dataclass

from pypdf import PdfReader


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str


class PdfParseError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def extract_pdf_pages(path: str) -> list[ParsedPage]:
    try:
        reader = PdfReader(path)
        pages: list[ParsedPage] = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append(ParsedPage(page_number=idx + 1, text=text))
        return pages
    except FileNotFoundError as e:
        raise PdfParseError("storage_read_error", str(e)) from e
    except PermissionError as e:
        raise PdfParseError("storage_read_error", str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise PdfParseError("pdf_parse_error", str(e)) from e

