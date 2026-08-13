from app.services.document_processing.normalization import normalize_text


def test_empty_text_stays_empty():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_normalizes_windows_and_mac_line_endings():
    assert normalize_text("a\r\nb\rc") == "a\nb\nc"


def test_strips_null_and_control_characters_but_keeps_newline_and_tab():
    text = "hello\x00world\n\tindented"
    normalized = normalize_text(text)

    assert "\x00" not in normalized
    assert "hello" in normalized
    assert "world" in normalized
    assert "\n\tindented" in normalized


def test_collapses_long_runs_of_blank_lines_but_keeps_paragraph_breaks():
    text = "paragraph one\n\n\n\n\n\nparagraph two"
    normalized = normalize_text(text)

    # 5 blank lines collapse down to at most 2 (three "\n" between the
    # words) -- a real paragraph break is preserved, not destroyed
    # entirely down to a single line break.
    assert normalized == "paragraph one\n\n\nparagraph two"


def test_a_single_blank_line_is_left_untouched():
    text = "paragraph one\n\nparagraph two"
    assert normalize_text(text) == "paragraph one\n\nparagraph two"


def test_strips_trailing_whitespace_per_line():
    text = "line one   \nline two\t\t\n"
    normalized = normalize_text(text)

    assert normalized == "line one\nline two"


def test_unicode_is_normalized_to_nfkc():
    # "ﬁ" (U+FB01, a ligature) should normalize to the two-character "fi".
    normalized = normalize_text("scientiﬁc")
    assert normalized == "scientific"
