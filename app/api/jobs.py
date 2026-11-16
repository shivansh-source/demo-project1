from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.queue.inspect import list_jobs as _list_jobs
from app.schemas.jobs import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: Literal["queued", "running", "done", "failed"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobOut]:
    """Jobs from the Redis queue. `queued` includes jobs waiting out a retry backoff."""
    return _list_jobs(status, limit, offset)
