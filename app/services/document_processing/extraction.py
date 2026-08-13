"""Native (non-OCR) PDF text extraction.

Library choice (see PHASE_05_DOCUMENT_PROCESSING.md "PDF Extraction Library
Decision" for the full comparison): pdfplumber, built on pdfminer.six.
MIT-licensed and pure Python (no system binary dependency, unlike
Tesseract/poppler), unlike PyMuPDF (AGPL/commercial dual license — a real
concern for a product not otherwise committed to AGPL obligations), with
better text-extraction quality on real-world layouts than the lighter
alternative (pypdf) at an acceptable speed cost — extraction runs in the
background worker, not on the request path, so raw speed matters less than
reliability here.
"""

import io
from dataclasses import dataclass

import pdfplumber


class PdfCorruptError(Exception):
    """Raised when a PDF cannot be parsed at all — a permanent failure,
    never worth retrying."""


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


def extract_native_pdf_text(file_content: bytes) -> list[ExtractedPage]:
    """Extract per-page text from a PDF's native text layer (no OCR).

    Raises PdfCorruptError for anything pdfminer can't parse at all —
    pdfminer/pdfplumber raise a variety of exception types for malformed
    PDFs (syntax errors, unsupported encodings, truncated files), so they're
    deliberately caught broadly and normalized to one exception type the
    caller can treat uniformly as "permanent, don't retry."
    """
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            return [
                ExtractedPage(page_number=index, text=page.extract_text() or "")
                for index, page in enumerate(pdf.pages, start=1)
            ]
    except Exception as exc:
        raise PdfCorruptError(f"Unable to parse PDF: {exc}") from exc
