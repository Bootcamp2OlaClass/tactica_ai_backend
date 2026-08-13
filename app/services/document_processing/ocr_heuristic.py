"""Deterministic heuristic for deciding whether native extraction produced
usable text or whether a document is effectively a scanned/image-based PDF
that would need OCR.

Thresholds (see PHASE_05_DOCUMENT_PROCESSING.md "OCR Strategy" for the full
reasoning): a page counts as "has text" once it has at least
MIN_CHARS_PER_PAGE non-whitespace characters. OCR is considered required if
fewer than MIN_TEXT_PAGE_RATIO of a document's pages have text — this
catches both fully-scanned documents (0% of pages have text) and mixed
documents (e.g. a scanned cover page followed by native pages) without
being tripped up by a single legitimately sparse page (a title page, a
mostly-blank section divider).
"""

from app.services.document_processing.extraction import ExtractedPage

MIN_CHARS_PER_PAGE = 20
MIN_TEXT_PAGE_RATIO = 0.5


def requires_ocr(pages: list[ExtractedPage]) -> bool:
    if not pages:
        return True

    pages_with_text = sum(
        1 for page in pages if len(page.text.strip()) >= MIN_CHARS_PER_PAGE
    )

    return (pages_with_text / len(pages)) < MIN_TEXT_PAGE_RATIO
