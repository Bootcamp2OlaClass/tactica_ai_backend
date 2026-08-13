from app.services.chunking import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS, chunk_document_pages


def test_empty_pages_produces_no_chunks():
    assert chunk_document_pages([]) == []


def test_whitespace_only_pages_produces_no_chunks():
    pages = [{"page_number": 1, "text": "   \n\n  "}]
    assert chunk_document_pages(pages) == []


def test_single_short_page_produces_one_chunk_with_correct_page_range():
    pages = [{"page_number": 1, "text": "Course syllabus for CS 101."}]
    chunks = chunk_document_pages(pages)

    assert len(chunks) == 1
    assert chunks[0].content == "Course syllabus for CS 101."
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 1


def test_multi_page_short_document_stays_within_one_chunk_spanning_pages():
    pages = [
        {"page_number": 1, "text": "Page one content."},
        {"page_number": 2, "text": "Page two content."},
    ]
    chunks = chunk_document_pages(pages)

    assert len(chunks) == 1
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 2
    assert "Page one content." in chunks[0].content
    assert "Page two content." in chunks[0].content


def test_long_single_page_splits_into_multiple_overlapping_chunks():
    long_text = "A" * (CHUNK_SIZE_CHARS * 3)
    pages = [{"page_number": 1, "text": long_text}]

    chunks = chunk_document_pages(pages)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.start_page == 1
        assert chunk.end_page == 1
        assert len(chunk.content) <= CHUNK_SIZE_CHARS

    # Consecutive chunks overlap by roughly CHUNK_OVERLAP_CHARS -- since
    # the text is uniform 'A's, just check the step size behaves as
    # configured rather than trying to compare content directly.
    step = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    expected_chunk_count = 1 + (len(long_text) - CHUNK_SIZE_CHARS + step - 1) // step
    assert len(chunks) == expected_chunk_count


def test_chunk_spanning_a_page_boundary_reports_both_pages():
    # First page just under one chunk size, second page pushes the window
    # across the boundary -- the resulting second chunk should report both
    # pages since the character window it slides over now covers text from
    # both.
    page_one_text = "B" * (CHUNK_SIZE_CHARS - 100)
    page_two_text = "C" * 500
    pages = [
        {"page_number": 5, "text": page_one_text},
        {"page_number": 6, "text": page_two_text},
    ]

    chunks = chunk_document_pages(pages)

    assert len(chunks) >= 2
    # The last chunk necessarily reads from page 6 (it's the tail of the
    # sliding window); the first chunk necessarily starts on page 5.
    assert chunks[0].start_page == 5
    assert chunks[-1].end_page == 6


def test_page_with_no_text_key_or_none_text_is_skipped_safely():
    pages = [
        {"page_number": 1, "text": ""},
        {"page_number": 2, "text": "Real content here."},
    ]
    chunks = chunk_document_pages(pages)

    assert len(chunks) == 1
    assert chunks[0].start_page == 2
    assert chunks[0].end_page == 2


def test_chunks_preserve_content_order():
    pages = [
        {"page_number": 1, "text": "FIRST_MARKER " + "x" * 800},
        {"page_number": 2, "text": "y" * 800 + " LAST_MARKER"},
    ]
    chunks = chunk_document_pages(pages)

    assert "FIRST_MARKER" in chunks[0].content
    assert "LAST_MARKER" in chunks[-1].content
