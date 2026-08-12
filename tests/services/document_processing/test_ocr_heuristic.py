from app.services.document_processing.extraction import ExtractedPage
from app.services.document_processing.ocr_heuristic import (
    MIN_CHARS_PER_PAGE,
    requires_ocr,
)


def test_no_pages_requires_ocr():
    assert requires_ocr([]) is True


def test_pages_with_ample_text_do_not_require_ocr():
    pages = [
        ExtractedPage(page_number=1, text="A" * (MIN_CHARS_PER_PAGE * 3)),
        ExtractedPage(page_number=2, text="B" * (MIN_CHARS_PER_PAGE * 3)),
    ]
    assert requires_ocr(pages) is False


def test_all_blank_pages_require_ocr():
    pages = [
        ExtractedPage(page_number=1, text=""),
        ExtractedPage(page_number=2, text="   \n  "),
    ]
    assert requires_ocr(pages) is True


def test_majority_blank_pages_require_ocr():
    # 1 of 3 pages has real text -- below the MIN_TEXT_PAGE_RATIO threshold.
    pages = [
        ExtractedPage(page_number=1, text="A" * (MIN_CHARS_PER_PAGE * 2)),
        ExtractedPage(page_number=2, text=""),
        ExtractedPage(page_number=3, text=""),
    ]
    assert requires_ocr(pages) is True


def test_single_sparse_page_among_many_does_not_trigger_ocr():
    # A mostly-blank title page shouldn't force the whole document to OCR.
    pages = [
        ExtractedPage(page_number=1, text="Title"),
        ExtractedPage(page_number=2, text="A" * (MIN_CHARS_PER_PAGE * 3)),
        ExtractedPage(page_number=3, text="B" * (MIN_CHARS_PER_PAGE * 3)),
    ]
    assert requires_ocr(pages) is False


def test_text_exactly_at_threshold_counts_as_having_text():
    pages = [ExtractedPage(page_number=1, text="A" * MIN_CHARS_PER_PAGE)]
    assert requires_ocr(pages) is False


def test_text_one_below_threshold_does_not_count():
    pages = [ExtractedPage(page_number=1, text="A" * (MIN_CHARS_PER_PAGE - 1))]
    assert requires_ocr(pages) is True
