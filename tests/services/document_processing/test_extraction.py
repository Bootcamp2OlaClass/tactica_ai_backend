import pytest

from app.services.document_processing.extraction import (
    PdfCorruptError,
    extract_native_pdf_text,
)


def test_extracts_text_from_a_digital_pdf(digital_text_pdf):
    pages = extract_native_pdf_text(digital_text_pdf)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "CS 101" in pages[0].text
    assert "Ada Lovelace" in pages[0].text


def test_extracts_text_per_page_in_order(multi_page_digital_text_pdf):
    pages = extract_native_pdf_text(multi_page_digital_text_pdf)

    assert len(pages) == 3
    assert [p.page_number for p in pages] == [1, 2, 3]
    for index, page in enumerate(pages, start=1):
        assert f"Page {index} content" in page.text


def test_blank_pdf_extracts_to_empty_text(blank_pdf):
    pages = extract_native_pdf_text(blank_pdf)

    assert len(pages) == 1
    assert pages[0].text.strip() == ""


def test_corrupt_pdf_raises_pdf_corrupt_error(corrupt_pdf):
    with pytest.raises(PdfCorruptError):
        extract_native_pdf_text(corrupt_pdf)


def test_empty_bytes_raises_pdf_corrupt_error():
    with pytest.raises(PdfCorruptError):
        extract_native_pdf_text(b"")
