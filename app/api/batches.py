from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import NotFoundError
from app.models import ImportBatch
from app.schemas.batches import BatchDetail

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: int, session: Annotated[Session, Depends(get_session)]) -> BatchDetail:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise NotFoundError(f"batch {batch_id} not found")
    return BatchDetail.model_validate(batch)
