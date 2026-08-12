"""Text normalization for extracted document pages.

Deliberately conservative — this normalizes encoding/whitespace artifacts,
not document structure. Page boundaries are preserved by the caller (each
page is normalized independently, never concatenated into one string here)
since later phases need page-level provenance (citations, chunking).
"""

import unicodedata


def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # Strip control/format/surrogate/private-use characters (Unicode
    # category "C*") — NUL bytes and similar extraction artifacts — but
    # keep \n and \t, which are technically control characters too.
    normalized = "".join(
        char
        for char in normalized
        if char in ("\n", "\t") or not unicodedata.category(char).startswith("C")
    )

    lines = [line.rstrip() for line in normalized.split("\n")]

    # Collapse 3+ consecutive blank lines down to at most 2 — tidies
    # extraction artifacts without destroying real paragraph breaks.
    collapsed: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 2:
                collapsed.append(line)
        else:
            blank_run = 0
            collapsed.append(line)

    return "\n".join(collapsed).strip()
