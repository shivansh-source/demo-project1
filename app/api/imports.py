from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.schemas.batches import BatchDetail
from app.services.importer import import_rows, parse_csv

router = APIRouter(prefix="/imports", tags=["imports"])

_API_EXAMPLE = [
    {
        "email": "Jane.Doe@Acme.com",
        "company_domain": "www.acme.com",
        "first_name": "Jane",
        "last_name": "Doe",
        "job_title": "VP Sales",
    }
]


@router.post("/csv", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
def import_csv(
    session: Annotated[Session, Depends(get_session)],
    file: Annotated[UploadFile, File(description="CSV with columns email, company_domain")],
) -> BatchDetail:
    rows = parse_csv(file.file.read())
    batch = import_rows(session, source="csv", filename=file.filename, rows=rows)
    session.commit()
    return BatchDetail.model_validate(batch)


@router.post("/api", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
def import_api(
    session: Annotated[Session, Depends(get_session)],
    rows: Annotated[list[dict[str, Any]], Body(examples=[_API_EXAMPLE])],
) -> BatchDetail:
    batch = import_rows(session, source="api", filename=None, rows=rows)
    session.commit()
    return BatchDetail.model_validate(batch)
