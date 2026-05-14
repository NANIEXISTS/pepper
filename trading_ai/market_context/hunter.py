from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import (
    ClobMicrostructureItem,
    CrossVenueCandidate,
    PredictionTerminalReport,
    ProfitHunterCandidate,
    ProfitHunterPaperTicket,
    ProfitHunterReport,
    ResolutionRiskItem,
    SourceMonitorItem,
    WhaleTrade,
)


class PolymarketProfitHunter:
    """Paper-only Polymarket opportunity ranker.

    The hunter is deliberately conservative. It turns public terminal data into
    reviewable paper trade tickets only when liquidity, spread, fillability, and
    rule-risk checks all pass.
    """

    def __init__(
        self,
        *,
        min_trade_score: float = 0.72,
        max_spread: float = 0.02,
        min_fill_score: float = 0.80,
        min_volume_24h: float = 250_000.0,
        min_liquidity: float = 50_000.0,
        max_ambiguity_score: float = 0.75,
    ) -> None:
        self.min_trade_score = min_trade_score
        self.max_spread = max_spread
        self.min_fill_score = min_fill_score
        self.min_volume_24h = min_volume_24h
        self.min_liquidity = min_liquidity
        self.max_ambiguity_score = max_ambiguity_score

    def run(
        self,
        terminal: PredictionTerminalReport,
        *,
        snapshot_delta: dict[str, Any] | None = None,
        horizon_minutes: int = 60,
        max_stake_usd: float = 25.0,
        min_trade_score: float | None = None,
        limit: int = 8,
    ) -> ProfitHunterReport:
        threshold = self._clamp(min_trade_score if min_trade_score is not None else self.min_trade_score)
        candidates = self._build_candidates(
            terminal,
            snapshot_delta=snapshot_delta or {},
            horizon_minutes=horizon_minutes,
            max_stake_usd=max_stake_usd,
            min_trade_score=threshold,
        )
        candidates.sort(key=lambda candidate: (not candidate.blockers, candidate.score), reverse=True)
        ranked = [
            candidate.model_copy(update={"rank": index})
            for index, candidate in enumerate(candidates[:limit], start=1)
        ]
        trade_candidate = next(
            (
                candidate
                for candidate in ranked
                if candidate.score >= threshold and not candidate.blockers and candidate.paper_ticket is not None
            ),
            None,
        )
        if trade_candidate is not None:
            verdict = "TRADE"
            action = "paper_trade_ticket_created"
            no_trade_reason = ""
        elif ranked:
            verdict = "NO_TRADE"
            action = "wait_for_better_edge"
            top = ranked[0]
            blocker_text = ", ".join(top.blockers[:4]) if top.blockers else "score_below_threshold"
            no_trade_reason = f"Best candidate did not pass: {blocker_text}."
        else:
            verdict = "INSUFFICIENT_EDGE"
            action = "collect_more_market_context"
            no_trade_reason = "No CLOB-backed candidate could be scored from the public terminal feed."

        return ProfitHunterReport(
            generated_at=datetime.now(UTC),
            available=terminal.available,
            requested_symbol=terminal.requested_symbol,
            horizon_minutes=horizon_minutes,
            verdict=verdict,
            action=action,
            candidate_count=len(candidates),
            top_score=ranked[0].score if ranked else 0.0,
            min_trade_score=threshold,
            max_stake_usd=max_stake_usd,
            no_trade_reason=no_trade_reason,
            trade_candidate=trade_candidate,
            candidates=ranked,
            summary={
                "tradeable_candidates": sum(1 for candidate in ranked if not candidate.blockers),
                "blocked_candidates": sum(1 for candidate in ranked if candidate.blockers),
                "negative_risk_candidates": sum(1 for candidate in ranked if candidate.negative_risk),
                "new_whale_flow_candidates": sum(1 for candidate in ranked if candidate.new_whale_flow),
            },
            warnings=[
                "This is a paper-only opportunity hunter, not a live Polymarket order path.",
                "Source-latency claims require external official-source confirmation before live capital.",
                "Cross-venue candidates are watchlist items until resolution rules are manually matched.",
            ],
        )

    def _build_candidates(
        self,
        terminal: PredictionTerminalReport,
        *,
        snapshot_delta: dict[str, Any],
        horizon_minutes: int,
        max_stake_usd: float,
        min_trade_score: float,
    ) -> list[ProfitHunterCandidate]:
        event_by_slug = {event.slug: event for event in terminal.hype.events}
        risk_by_slug = {item.slug: item for item in terminal.resolution.items}
        source_by_slug = {item.slug: item for item in terminal.source_monitor.items}
        trades_by_slug = self._trades_by_slug(terminal.wallets.whale_trades)
        new_flow_slugs = {
            str(trade.get("slug") or "")
            for trade in snapshot_delta.get("new_whale_trades", [])
            if isinstance(trade, dict)
        }

        candidates: list[ProfitHunterCandidate] = []
        for book in terminal.microstructure.items:
            event = event_by_slug.get(book.slug)
            risk = risk_by_slug.get(book.slug)
            source = source_by_slug.get(book.slug)
            trades = trades_by_slug.get(book.slug, [])
            new_flow = book.slug in new_flow_slugs
            method = self._method_for(book, title=book.title, source=source, trades=trades, new_flow=new_flow)
            score = self._score_book(
                book,
                volume_24h=event.volume_24h if event else 0.0,
                liquidity=event.liquidity if event else 0.0,
                ambiguity_score=risk.ambiguity_score if risk else 0.0,
                whale_notional=sum(trade.notional for trade in trades),
                new_flow=new_flow,
                source=source,
            )
            blockers = self._blockers(
                book,
                volume_24h=event.volume_24h if event else 0.0,
                liquidity=event.liquidity if event else 0.0,
                ambiguity_score=risk.ambiguity_score if risk else 0.0,
                score=score,
                min_trade_score=min_trade_score,
                method=method,
                has_wallet_confirmation=bool(trades or new_flow),
            )
            source_checks = self._source_checks(source)
            paper_ticket = (
                self._paper_ticket(book, horizon_minutes=horizon_minutes, max_stake_usd=max_stake_usd)
                if not blockers and score >= min_trade_score and book.best_ask is not None
                else None
            )
            candidates.append(
                ProfitHunterCandidate(
                    rank=1,
                    method=method,
                    title=book.title,
                    slug=book.slug,
                    source_url=book.source_url,
                    outcome=book.outcome,
                    token_id=book.token_id,
                    score=score,
                    estimated_edge_score=max(0.0, round(score - min_trade_score, 4)),
                    best_bid=book.best_bid,
                    best_ask=book.best_ask,
                    spread=book.spread,
                    fill_probability_score=book.fill_probability_score,
                    volume_24h=event.volume_24h if event else 0.0,
                    liquidity=event.liquidity if event else 0.0,
                    ambiguity_score=risk.ambiguity_score if risk else 0.0,
                    whale_notional_usd=sum(trade.notional for trade in trades),
                    new_whale_flow=new_flow,
                    negative_risk=book.negative_risk,
                    blockers=blockers,
                    evidence=self._evidence(book, risk=risk, source=source, trades=trades, new_flow=new_flow),
                    source_checks=source_checks,
                    paper_ticket=paper_ticket,
                )
            )

        candidates.extend(self._cross_venue_watch_candidates(terminal.cross_venue.candidates))
        return candidates

    def _score_book(
        self,
        book: ClobMicrostructureItem,
        *,
        volume_24h: float,
        liquidity: float,
        ambiguity_score: float,
        whale_notional: float,
        new_flow: bool,
        source: SourceMonitorItem | None,
    ) -> float:
        spread_score = 0.0 if book.spread is None else max(0.0, 1.0 - min(book.spread / 0.05, 1.0))
        volume_score = min(volume_24h / 1_000_000.0, 1.0)
        liquidity_score = min(liquidity / 100_000.0, 1.0)
        whale_score = min(whale_notional / 2_000.0, 1.0)
        source_score = 1.0 if source and source.official_sources else 0.0
        score = (
            (0.22 * spread_score)
            + (0.28 * book.fill_probability_score)
            + (0.16 * volume_score)
            + (0.10 * liquidity_score)
            + (0.10 * whale_score)
            + (0.06 * source_score)
            + (0.14 if book.negative_risk else 0.0)
            + (0.06 if new_flow else 0.0)
            - (0.18 * ambiguity_score)
        )
        return self._clamp(score)

    def _blockers(
        self,
        book: ClobMicrostructureItem,
        *,
        volume_24h: float,
        liquidity: float,
        ambiguity_score: float,
        score: float,
        min_trade_score: float,
        method: str,
        has_wallet_confirmation: bool,
    ) -> list[str]:
        blockers: list[str] = []
        if book.best_ask is None:
            blockers.append("missing_best_ask")
        if book.spread is None:
            blockers.append("missing_spread")
        elif book.spread > self.max_spread:
            blockers.append("spread_above_2c")
        if book.fill_probability_score < self.min_fill_score:
            blockers.append("fill_probability_below_80pct")
        if volume_24h < self.min_volume_24h and liquidity < self.min_liquidity:
            blockers.append("insufficient_volume_or_liquidity")
        if ambiguity_score > self.max_ambiguity_score:
            blockers.append("resolution_ambiguity_too_high")
        if method == "negative_risk_basket" and not has_wallet_confirmation:
            blockers.append("basket_edge_not_computed")
        if method == "source_latency":
            blockers.append("official_source_not_verified")
        if method == "crypto_close":
            blockers.append("spot_momentum_not_verified")
        if method == "clob_microstructure" and not has_wallet_confirmation:
            blockers.append("directional_edge_unconfirmed")
        if score < min_trade_score:
            blockers.append("score_below_trade_threshold")
        return blockers

    def _paper_ticket(
        self,
        book: ClobMicrostructureItem,
        *,
        horizon_minutes: int,
        max_stake_usd: float,
    ) -> ProfitHunterPaperTicket:
        entry_price = book.best_ask or book.midpoint or 0.0
        spread = book.spread or 0.01
        quantity = max_stake_usd / entry_price if entry_price > 0 else 0.0
        take_profit = min(0.98, entry_price + max(0.02, spread * 3.0))
        stop_loss = max(0.01, entry_price - max(0.03, spread * 3.0))
        return ProfitHunterPaperTicket(
            title=book.title,
            slug=book.slug,
            outcome=book.outcome,
            token_id=book.token_id,
            entry_price=round(entry_price, 4),
            quantity=round(quantity, 4),
            notional_usd=round(max_stake_usd, 2),
            max_loss_usd=round(max_stake_usd, 2),
            take_profit_price=round(take_profit, 4),
            stop_loss_price=round(stop_loss, 4),
            time_stop_minutes=horizon_minutes,
            exit_plan=(
                f"Paper exit at {take_profit:.4f}, stop at {stop_loss:.4f}, "
                f"or close after {horizon_minutes} minutes."
            ),
        )

    def _method_for(
        self,
        book: ClobMicrostructureItem,
        *,
        title: str,
        source: SourceMonitorItem | None,
        trades: list[WhaleTrade],
        new_flow: bool,
    ) -> str:
        text = f"{title} {book.slug}".lower()
        if "updown" in text or any(token in text for token in ("bitcoin up or down", "ethereum up or down", "xrp up or down")):
            return "crypto_close"
        if book.negative_risk:
            return "negative_risk_basket"
        if trades or new_flow:
            return "wallet_delta"
        if source and source.official_sources:
            return "source_latency"
        return "clob_microstructure"

    def _evidence(
        self,
        book: ClobMicrostructureItem,
        *,
        risk: ResolutionRiskItem | None,
        source: SourceMonitorItem | None,
        trades: list[WhaleTrade],
        new_flow: bool,
    ) -> list[str]:
        evidence = [
            f"Spread={book.spread if book.spread is not None else 'missing'}; fill score={book.fill_probability_score:.2f}.",
            f"Best bid/ask={book.best_bid}/{book.best_ask}.",
        ]
        if book.negative_risk:
            evidence.append("Negative-risk market structure detected.")
        if risk:
            evidence.append(f"Resolution ambiguity={risk.ambiguity_score:.2f}; flags={', '.join(risk.risk_flags[:4]) or 'none'}.")
        if trades:
            evidence.append(f"Public whale/top-wallet notional on this slug={sum(trade.notional for trade in trades):.2f}.")
        if new_flow:
            evidence.append("New whale flow versus the previous saved terminal snapshot.")
        if source and source.official_sources:
            evidence.append(f"Source checks: {', '.join(source.official_sources[:3])}.")
        return evidence

    def _source_checks(self, source: SourceMonitorItem | None) -> list[str]:
        if source is None:
            return []
        return source.official_sources[:4]

    def _trades_by_slug(self, trades: list[WhaleTrade]) -> dict[str, list[WhaleTrade]]:
        grouped: dict[str, list[WhaleTrade]] = {}
        for trade in trades:
            grouped.setdefault(trade.slug, []).append(trade)
        return grouped

    def _cross_venue_watch_candidates(self, candidates: list[CrossVenueCandidate]) -> list[ProfitHunterCandidate]:
        watch: list[ProfitHunterCandidate] = []
        for candidate in candidates[:3]:
            gap = candidate.probability_gap or 0.0
            watch.append(
                ProfitHunterCandidate(
                    rank=1,
                    method="cross_venue_arb_watch",
                    title=candidate.title,
                    slug=candidate.polymarket_slug,
                    source_url=f"https://polymarket.com/event/{candidate.polymarket_slug}",
                    score=self._clamp(0.35 + min(gap, 0.20)),
                    estimated_edge_score=0.0,
                    blockers=["rule_equivalence_unconfirmed", "execution_route_not_configured"],
                    evidence=[
                        f"Kalshi candidate={candidate.kalshi_ticker or candidate.kalshi_title}.",
                        f"Probability gap={gap:.2%}." if candidate.probability_gap is not None else "Probability gap unavailable.",
                        "Use as a manual rule-matching watch item only.",
                    ],
                    source_checks=[],
                )
            )
        return watch

    def _clamp(self, value: float) -> float:
        return round(max(0.0, min(float(value), 1.0)), 4)
