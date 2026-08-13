"""Fixed-size chunking over Phase 05's page-labeled normalized text — see
PHASE_07_RAG.md and ADR-003.

Deliberately reuses the exact same `{page_number, text}` artifact Phase 05
already produces and Phase 06 already reads (app/services/document_extraction.py's
`_build_page_labeled_content`) -- this is the one document representation
this codebase uses; chunking does not invent a second one.

Character-based (not token-based): no tokenizer dependency exists in this
codebase yet, and character count is a fine, deterministic proxy at this
scale -- revisit if a real tokenizer becomes available and precision starts
to matter for a specific embedding model's token limit.
"""

from dataclasses import dataclass

CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 150


@dataclass(frozen=True)
class ChunkDraft:
    content: str
    start_page: int
    end_page: int


def chunk_document_pages(pages: list[dict]) -> list[ChunkDraft]:
    """Concatenates page texts (tracking character-offset boundaries per
    page), then slides a fixed-size, overlapping window over the result.
    Every chunk's start_page/end_page is derived from which page
    boundaries its character range actually overlaps -- never guessed."""

    boundaries: list[tuple[int, int, int]] = []
    parts: list[str] = []
    offset = 0

    for page in pages:
        text = page.get("text") or ""
        if not text:
            continue
        if parts:
            parts.append("\n\n")
            offset += 2
        start = offset
        parts.append(text)
        offset += len(text)
        boundaries.append((page["page_number"], start, offset))

    full_text = "".join(parts)
    if not full_text.strip() or not boundaries:
        return []

    def _page_range_for(start: int, end: int) -> tuple[int, int]:
        covering = [
            page_number
            for page_number, b_start, b_end in boundaries
            if b_end > start and b_start < end
        ]
        if not covering:
            covering = [boundaries[0][0]]
        return min(covering), max(covering)

    text_length = len(full_text)
    step = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS

    chunks: list[ChunkDraft] = []
    start = 0
    while start < text_length:
        end = min(start + CHUNK_SIZE_CHARS, text_length)
        chunk_text = full_text[start:end].strip()

        if chunk_text:
            start_page, end_page = _page_range_for(start, end)
            chunks.append(
                ChunkDraft(
                    content=chunk_text,
                    start_page=start_page,
                    end_page=end_page,
                )
            )

        if end >= text_length:
            break
        start += step

    return chunks
