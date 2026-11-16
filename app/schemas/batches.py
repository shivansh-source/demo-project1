from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RowErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    reason: str
    raw_payload: dict[str, Any]


class BatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    filename: str | None
    created_at: datetime
    total_rows: int
    accepted_rows: int
    rejected_rows: int


class BatchDetail(BatchSummary):
    errors: list[RowErrorOut]
