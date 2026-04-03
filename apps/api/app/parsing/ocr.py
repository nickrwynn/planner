from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


class OcrEnvironmentError(Exception):
    """Tesseract or OCR runtime missing or misconfigured (not a bad image file)."""

    code = "ocr_environment_error"


class OcrParseError(Exception):
    """Image unreadable for OCR processing."""

    code = "ocr_parse_error"


@dataclass(frozen=True)
class OcrResult:
    text: str


def ocr_image(path: str) -> OcrResult:
    """
    OCR an image file using pytesseract.
    Requires `tesseract-ocr` binary in the container/host.
    """
    try:
        import pytesseract
    except ImportError as e:
        raise OcrEnvironmentError(
            "pytesseract is not installed (add to requirements for OCR)"
        ) from e

    try:
        img = Image.open(path)
        text = pytesseract.image_to_string(img) or ""
    except pytesseract.TesseractNotFoundError as e:
        raise OcrEnvironmentError(
            "tesseract binary not found — install tesseract-ocr (e.g. apt install tesseract-ocr)"
        ) from e
    except OSError as e:
        # Corrupt image / unreadable file — not an environment issue
        raise OcrParseError(f"cannot read image for OCR: {e}") from e
    return OcrResult(text=text)


def classify_ocr_error(exc: Exception) -> str:
    if isinstance(exc, OcrEnvironmentError):
        return OcrEnvironmentError.code
    if isinstance(exc, OcrParseError):
        return OcrParseError.code
    return "ocr_parse_error"
