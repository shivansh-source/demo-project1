"""All ORM tables. Typed SQLAlchemy 2.0 style."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# --- Allowed values (also enforced by CHECK constraints) ---
IMPORT_SOURCES = ("csv", "api")
ENRICHMENT_STATUSES = ("pending", "enriched", "not_found")
REASONING_STATUSES = ("ok", "pending", "failed", "skipped")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> Any:
    return func.now()


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (CheckConstraint(_in("source", IMPORT_SOURCES), name="ck_batch_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(10))
    filename: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)

    errors: Mapped[list[ImportRowError]] = relationship(
        back_populates="batch", order_by="ImportRowError.row_number"
    )


class ImportRowError(Base):
    __tablename__ = "import_row_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    batch: Mapped[ImportBatch] = relationship(back_populates="errors")


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(_in("enrichment_status", ENRICHMENT_STATUSES), name="ck_company_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    industry: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    enrichment_status: Mapped[str] = mapped_column(String(20), default="pending")
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrichment_source: Mapped[str | None] = mapped_column(String(50))


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (CheckConstraint("email = lower(email)", name="ck_lead_email_lower"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str | None] = mapped_column(String(255))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    segment: Mapped[str | None] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=_now(), onupdate=_now()
    )

    company: Mapped[Company] = relationship()


class LeadScore(Base):
    """Append-only: every scoring run inserts a new row. Rows are never updated
    except to fill in `reasoning` / `reasoning_status` after the LLM step."""

    __tablename__ = "lead_scores"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_score_range"),
        CheckConstraint(_in("reasoning_status", REASONING_STATUSES), name="ck_reasoning_status"),
        Index("ix_lead_scores_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"))
    score: Mapped[int] = mapped_column(Integer)
    rule_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rules_version: Mapped[str] = mapped_column(String(64))
    reasoning: Mapped[str | None] = mapped_column(Text)
    reasoning_status: Mapped[str] = mapped_column(String(10), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class CrmPush(Base):
    __tablename__ = "crm_pushes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("lead_scores.id"))
    status: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
