from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String
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


class OperatorAuditEvent(Base):
    __tablename__ = "operator_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PaperCycleJobRecord(Base):
    __tablename__ = "paper_cycle_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    lookback_bars: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class PaperCycleRunRecord(Base):
    __tablename__ = "paper_cycle_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("paper_cycle_jobs.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trade_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    cycle_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PortfolioStateRecord(Base):
    __tablename__ = "portfolio_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True, default="paper-default")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_anchor_equity: Mapped[float] = mapped_column(Float, nullable=False)
    daily_anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    positions_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LiveReadinessRecord(Base):
    __tablename__ = "live_readiness_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class PredictionTerminalSnapshotRecord(Base):
    __tablename__ = "prediction_terminal_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    report_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
