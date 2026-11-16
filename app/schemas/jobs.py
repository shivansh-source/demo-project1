from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    type: str
    payload: dict[str, Any]
    status: str  # queued (incl. scheduled/backing off) | running | done | failed
    attempts: int
    max_attempts: int
    last_error: str | None
    enqueued_at: datetime | None
