"""Small, deterministic PDF fixtures generated on the fly with fpdf2
(test-only dependency) — no binary fixture files checked into the repo."""

import pytest
from fpdf import FPDF


def _pdf_bytes(build) -> bytes:
    pdf = FPDF()
    build(pdf)
    return bytes(pdf.output())


@pytest.fixture
def digital_text_pdf() -> bytes:
    def build(pdf: FPDF) -> None:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(
            0,
            10,
            "CS 101 -- Introduction to Computer Science\n\n"
            "Instructor: Dr. Ada Lovelace\n"
            "Exam 1: October 15\n"
            "Final Project due December 1",
        )

    return _pdf_bytes(build)


@pytest.fixture
def multi_page_digital_text_pdf() -> bytes:
    def build(pdf: FPDF) -> None:
        pdf.set_font("Helvetica", size=12)
        for page_number in range(1, 4):
            pdf.add_page()
            pdf.multi_cell(0, 10, f"Page {page_number} content: syllabus section {page_number}.")

    return _pdf_bytes(build)


@pytest.fixture
def blank_pdf() -> bytes:
    def build(pdf: FPDF) -> None:
        pdf.add_page()

    return _pdf_bytes(build)


@pytest.fixture
def corrupt_pdf() -> bytes:
    return b"this is not a real pdf file at all"
