from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..orchestration.models import PaperCycleRunView


ProfitabilityStatus = Literal["insufficient_evidence", "profitable", "not_profitable"]


class PaperProfitabilityDay(BaseModel):
    day: date
    run_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    first_run_id: int
    last_run_id: int
    first_equity: float = Field(gt=0.0)
    last_equity: float = Field(gt=0.0)
    pnl: float
    return_fraction: float


class PaperProfitabilityReport(BaseModel):
    required_days: int = Field(ge=1)
    completed_days_observed: int = Field(ge=0)
    equity_days_observed: int = Field(ge=0)
    evaluated_days: int = Field(ge=0)
    complete: bool
    passed: bool
    status: ProfitabilityStatus
    start_equity: float | None = None
    end_equity: float | None = None
    total_pnl: float
    total_return_fraction: float
    max_drawdown_fraction: float
    profitable_days: int = Field(ge=0)
    losing_days: int = Field(ge=0)
    flat_days: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    missing_equity_run_ids: list[int] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    days: list[PaperProfitabilityDay] = Field(default_factory=list)


def evaluate_paper_profitability(
    runs: list["PaperCycleRunView"],
    *,
    required_days: int = 14,
    min_total_return_fraction: float = 0.0,
) -> PaperProfitabilityReport:
    if required_days <= 0:
        raise ValueError("required_days must be positive.")

    completed_runs = [run for run in runs if run.status == "completed"]
    completed_days = {_to_utc(run.started_at).date() for run in completed_runs}
    missing_equity_run_ids: list[int] = []
    by_day: dict[date, list[tuple["PaperCycleRunView", float]]] = defaultdict(list)

    for run in completed_runs:
        equity = _extract_equity(run)
        if equity is None or equity <= 0:
            missing_equity_run_ids.append(run.id)
            continue
        by_day[_to_utc(run.started_at).date()].append((run, equity))

    daily_inputs: list[tuple[date, list[tuple["PaperCycleRunView", float]]]] = []
    for run_day, day_runs in by_day.items():
        ordered = sorted(day_runs, key=lambda item: (_to_utc(item[0].started_at), item[0].id))
        daily_inputs.append((run_day, ordered))
    daily_inputs.sort(key=lambda item: item[0])

    selected_inputs = daily_inputs[-required_days:]
    complete = len(selected_inputs) >= required_days
    blocking_reasons: list[str] = []
    if not complete:
        blocking_reasons.append(f"paper_profitability_incomplete:{len(selected_inputs)}_of_{required_days}_equity_days")

    if missing_equity_run_ids and not complete:
        blocking_reasons.append("paper_profitability_missing_equity_payloads")

    selected_days: list[PaperProfitabilityDay] = []
    previous_equity: float | None = None
    peak_equity: float | None = None
    max_drawdown = 0.0
    profitable_days = 0
    losing_days = 0
    flat_days = 0
    trade_count = 0

    for run_day, day_runs in selected_inputs:
        first_run, first_equity = day_runs[0]
        last_run, last_equity = day_runs[-1]
        baseline_equity = previous_equity if previous_equity is not None else first_equity
        pnl = last_equity - baseline_equity
        return_fraction = (pnl / baseline_equity) if baseline_equity else 0.0
        day_trade_count = sum(1 for run, _ in day_runs if run.trade_executed)
        trade_count += day_trade_count
        if return_fraction > 0:
            profitable_days += 1
        elif return_fraction < 0:
            losing_days += 1
        else:
            flat_days += 1

        peak_equity = last_equity if peak_equity is None else max(peak_equity, last_equity)
        if peak_equity:
            max_drawdown = min(max_drawdown, (last_equity / peak_equity) - 1.0)
        previous_equity = last_equity

        selected_days.append(
            PaperProfitabilityDay(
                day=run_day,
                run_count=len(day_runs),
                trade_count=day_trade_count,
                first_run_id=first_run.id,
                last_run_id=last_run.id,
                first_equity=first_equity,
                last_equity=last_equity,
                pnl=pnl,
                return_fraction=return_fraction,
            )
        )

    start_equity = selected_days[0].first_equity if selected_days else None
    end_equity = selected_days[-1].last_equity if selected_days else None
    total_pnl = (end_equity - start_equity) if start_equity is not None and end_equity is not None else 0.0
    total_return = (total_pnl / start_equity) if start_equity else 0.0
    profitable = complete and total_return > min_total_return_fraction
    if complete and not profitable:
        blocking_reasons.append("paper_profitability_not_positive")

    return PaperProfitabilityReport(
        required_days=required_days,
        completed_days_observed=len(completed_days),
        equity_days_observed=len(daily_inputs),
        evaluated_days=len(selected_days),
        complete=complete,
        passed=profitable,
        status="profitable" if profitable else "not_profitable" if complete else "insufficient_evidence",
        start_equity=start_equity,
        end_equity=end_equity,
        total_pnl=total_pnl,
        total_return_fraction=total_return,
        max_drawdown_fraction=max_drawdown,
        profitable_days=profitable_days,
        losing_days=losing_days,
        flat_days=flat_days,
        trade_count=trade_count,
        missing_equity_run_ids=missing_equity_run_ids,
        blocking_reasons=blocking_reasons,
        days=selected_days,
    )


def _extract_equity(run: "PaperCycleRunView") -> float | None:
    payload = run.cycle_payload or {}
    portfolio = payload.get("portfolio")
    if not isinstance(portfolio, dict):
        return None
    equity = portfolio.get("equity")
    if equity is None:
        return None
    try:
        return float(equity)
    except (TypeError, ValueError):
        return None


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
