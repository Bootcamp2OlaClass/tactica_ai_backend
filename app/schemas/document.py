from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import (
    DocumentType,
    ExtractionMethod,
    LLMExtractionStatus,
    ProcessingStatus,
)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    uploaded_by: int
    original_file_name: str
    mime_type: str
    file_size: int
    checksum: str | None
    document_type: DocumentType
    processing_status: ProcessingStatus
    processing_error: str | None
    processed_at: datetime | None
    extraction_method: ExtractionMethod | None
    page_count: int | None
    text_length: int | None
    llm_extraction_status: LLMExtractionStatus
    llm_extraction_error: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)