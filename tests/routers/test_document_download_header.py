from app.routers.documents import _content_disposition_header


def test_plain_filename_uses_the_raw_quoted_string_form():
    assert (
        _content_disposition_header("normal-file.pdf")
        == 'attachment; filename="normal-file.pdf"'
    )


def test_filename_with_a_quote_character_is_percent_encoded():
    # A raw double-quote could otherwise break out of `filename="..."` —
    # must fall back to the RFC 5987 encoded form instead.
    header = _content_disposition_header('weird name (final) v2".pdf')
    assert header.startswith("attachment; filename*=utf-8''")
    assert '"' not in header.split("filename*=utf-8''", 1)[1]


def test_non_ascii_filename_is_percent_encoded():
    header = _content_disposition_header("résumé.pdf")
    assert header == "attachment; filename*=utf-8''r%C3%A9sum%C3%A9.pdf"
