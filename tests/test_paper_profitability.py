from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trading_ai.orchestration import PaperCycleRunView
from trading_ai.readiness import evaluate_paper_profitability


def _run(run_id: int, started_at: datetime, equity: float | None, *, trade_executed: bool = False) -> PaperCycleRunView:
    return PaperCycleRunView(
        id=run_id,
        job_id=None,
        source="test",
        symbol="BTC-USD",
        timeframe="1h",
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=5),
        status="completed",
        execution_status="filled" if trade_executed else "none",
        trade_executed=trade_executed,
        cycle_payload={"portfolio": {"equity": equity}} if equity is not None else {},
    )


def test_paper_profitability_passes_only_after_positive_14_day_equity_series() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [
        _run(day + 1, base + timedelta(days=day), 100_000 + (day * 100), trade_executed=day % 2 == 0)
        for day in range(14)
    ]

    report = evaluate_paper_profitability(runs)

    assert report.complete is True
    assert report.passed is True
    assert report.status == "profitable"
    assert report.evaluated_days == 14
    assert report.start_equity == 100_000
    assert report.end_equity == 101_300
    assert report.total_return_fraction > 0
    assert report.trade_count == 7
    assert report.blocking_reasons == []


def test_paper_profitability_blocks_incomplete_or_missing_equity_evidence() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [_run(1, base, None), _run(2, base + timedelta(days=1), 100_000)]

    report = evaluate_paper_profitability(runs)

    assert report.complete is False
    assert report.passed is False
    assert report.status == "insufficient_evidence"
    assert report.missing_equity_run_ids == [1]
    assert "paper_profitability_missing_equity_payloads" in report.blocking_reasons
    assert any(reason.startswith("paper_profitability_incomplete") for reason in report.blocking_reasons)


def test_paper_profitability_fails_completed_negative_14_day_series() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [_run(day + 1, base + timedelta(days=day), 100_000 - (day * 100)) for day in range(14)]

    report = evaluate_paper_profitability(runs)

    assert report.complete is True
    assert report.passed is False
    assert report.status == "not_profitable"
    assert report.total_return_fraction < 0
    assert "paper_profitability_not_positive" in report.blocking_reasons
    assert report.max_drawdown_fraction < 0
