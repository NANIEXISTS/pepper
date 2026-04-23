from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TradeAuditEvent(Base):
    __tablename__ = "trade_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_check_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    action_taken: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(String(2048), nullable=False)
    order_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    risk_reason: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    router: Mapped[str] = mapped_column(String(64), nullable=False)
    order_status: Mapped[str] = mapped_column(String(32), nullable=False)
    report_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
