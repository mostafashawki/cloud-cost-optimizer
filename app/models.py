"""ORM models for Scan, Resource, and Finding (SPEC §4).

SQLAlchemy 2.0 typed `Mapped[...]` models. JSON columns store dicts as TEXT
under SQLite, decoded transparently by SQLAlchemy's `JSON` type.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)  # "aws" | "azure"
    resource_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_monthly_savings: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    resources: Mapped[list[Resource]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    monthly_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="resources")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="resource",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_pk: Mapped[int] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # low|medium|high
    estimated_monthly_savings: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    remediation_command: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    scan: Mapped[Scan] = relationship(back_populates="findings")
    resource: Mapped[Resource] = relationship(back_populates="findings")
