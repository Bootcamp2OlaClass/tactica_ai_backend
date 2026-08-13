from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.extraction_candidate import CandidateStatus, CandidateType


class ExtractionCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    candidate_type: CandidateType
    payload: dict
    source_page: int | None
    status: CandidateStatus
    created_task_id: int | None
    reviewed_at: datetime | None
    reviewed_by: int | None
    created_at: datetime


class ExtractionCandidateListResponse(BaseModel):
    items: list[ExtractionCandidateResponse]
