from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
import re
from typing import Any, Iterable, Literal

import httpx

from .models import (
    BookDepthLevel,
    ClobMicrostructureItem,
    ClobMicrostructureReport,
    CrossVenueArbReport,
    CrossVenueCandidate,
    NarrativeRelevance,
    PolymarketHypeEvent,
    PolymarketHypeReport,
    PredictionTerminalReport,
    ResolutionRiskItem,
    ResolutionRiskReport,
    SourceMonitorItem,
    SourceMonitorReport,
    WalletIntelligenceReport,
    WalletLeaderboardEntry,
    WhaleTrade,
)


class PolymarketHypeService:
    """Read-only public Polymarket narrative scanner.

    This service deliberately uses only public discovery endpoints. It does not
    authenticate, place orders, or inspect private user data.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://gamma-api.polymarket.com",
        data_api_url: str = "https://data-api.polymarket.com",
        clob_url: str = "https://clob.polymarket.com",
        kalshi_url: str = "https://api.elections.kalshi.com/trade-api/v2",
        timeout_seconds: float = 6.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.data_api_url = data_api_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")
        self.kalshi_url = kalshi_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def fetch_hype(self, *, symbol: str | None = None, limit: int = 12, scan_limit: int = 100) -> PolymarketHypeReport:
        events = await self._fetch_events(limit=scan_limit)
        return self.build_report(events, symbol=symbol, limit=limit)

    async def fetch_terminal(
        self,
        *,
        symbol: str | None = None,
        limit: int = 8,
        scan_limit: int = 100,
    ) -> PredictionTerminalReport:
        events = await self._fetch_events(limit=scan_limit)
        warnings: list[str] = []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            leaderboard_task = self._fetch_optional_json(
                client,
                f"{self.data_api_url}/v1/leaderboard",
                params={"limit": "25"},
                warning_label="Polymarket leaderboard",
                warnings=warnings,
            )
            trades_task = self._fetch_optional_json(
                client,
                f"{self.data_api_url}/trades",
                params={"limit": "100"},
                warning_label="Polymarket trades",
                warnings=warnings,
            )
            kalshi_task = self._fetch_optional_json(
                client,
                f"{self.kalshi_url}/events",
                params={"limit": "100", "status": "open", "with_nested_markets": "true"},
                warning_label="Kalshi public markets",
                warnings=warnings,
            )

            leaderboard, trades, kalshi_payload = await asyncio.gather(
                leaderboard_task,
                trades_task,
                kalshi_task,
            )
            books = await self._fetch_books_for_terminal(client, events=events, symbol=symbol, max_books=min(max(limit, 1), 8))

        report = self.build_terminal(
            events,
            leaderboard=leaderboard,
            trades=trades,
            kalshi_events=kalshi_payload,
            books_by_token=books,
            symbol=symbol,
            limit=limit,
        )
        report.warnings.extend(warnings)
        return report

    async def _fetch_events(self, *, limit: int) -> list[dict[str, Any]]:
        params = {
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": str(limit),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/events", params=params)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Polymarket Gamma events endpoint returned an unexpected payload.")
        return [event for event in payload if isinstance(event, dict)]

    async def _fetch_optional_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, str],
        warning_label: str,
        warnings: list[str],
    ) -> Any:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            warnings.append(f"{warning_label} unavailable: {exc}")
            return None

    def build_report(
        self,
        events: Iterable[dict[str, Any]],
        *,
        symbol: str | None = None,
        limit: int = 12,
    ) -> PolymarketHypeReport:
        requested_symbol = symbol.upper() if symbol else None
        raw_events = list(events)
        enriched = [self._to_event(event, requested_symbol=requested_symbol) for event in raw_events]
        enriched.sort(key=lambda event: (event.relevance_score, event.volume_24h, event.liquidity), reverse=True)
        visible = enriched[:limit]

        symbol_counts: Counter[str] = Counter()
        for event in enriched:
            symbol_counts.update(event.mapped_symbols)

        return PolymarketHypeReport(
            requested_symbol=requested_symbol,
            events_scanned=len(raw_events),
            mapped_event_count=sum(1 for event in enriched if event.relevance != "unmapped"),
            direct_event_count=sum(1 for event in enriched if event.relevance == "direct"),
            total_volume_24h=sum(event.volume_24h for event in enriched),
            top_symbols=[symbol for symbol, _ in symbol_counts.most_common(8)],
            events=visible,
            warnings=[
                "Prediction-market attention is context, not an executable signal.",
                "Do not attach this feed to the active 14-day paper test without starting a new experiment window.",
            ],
        )

    def build_terminal(
        self,
        events: Iterable[dict[str, Any]],
        *,
        leaderboard: Any = None,
        trades: Any = None,
        kalshi_events: Any = None,
        books_by_token: dict[str, dict[str, Any]] | None = None,
        symbol: str | None = None,
        limit: int = 8,
    ) -> PredictionTerminalReport:
        raw_events = list(events)
        requested_symbol = symbol.upper() if symbol else None
        hype = self.build_report(raw_events, symbol=symbol, limit=limit)
        terminal_events = [
            self._to_event(event, requested_symbol=requested_symbol)
            for event in raw_events
        ]
        terminal_events.sort(key=lambda event: (event.relevance_score, event.volume_24h, event.liquidity), reverse=True)

        wallets = self._build_wallet_report(leaderboard=leaderboard, trades=trades, limit=limit)
        resolution = self._build_resolution_report(raw_events, terminal_events=terminal_events, limit=limit)
        microstructure = self._build_microstructure_report(
            raw_events,
            terminal_events=terminal_events,
            books_by_token=books_by_token or {},
            limit=limit,
        )
        cross_venue = self._build_cross_venue_report(
            raw_events,
            terminal_events=terminal_events,
            kalshi_events=kalshi_events,
            limit=limit,
        )
        source_monitor = self._build_source_monitor_report(raw_events, terminal_events=terminal_events, limit=limit)

        return PredictionTerminalReport(
            requested_symbol=requested_symbol,
            hype=hype,
            wallets=wallets,
            resolution=resolution,
            microstructure=microstructure,
            cross_venue=cross_venue,
            source_monitor=source_monitor,
            warnings=[
                "Terminal intelligence is public-data context. Confirm resolution rules and liquidity before acting.",
                "Copy/contra labels are heuristics, not recommendations.",
            ],
        )

    def unavailable_report(self, *, symbol: str | None, error: str) -> PolymarketHypeReport:
        return PolymarketHypeReport(
            available=False,
            requested_symbol=symbol.upper() if symbol else None,
            events_scanned=0,
            mapped_event_count=0,
            direct_event_count=0,
            total_volume_24h=0.0,
            events=[],
            warnings=[f"Polymarket hype feed unavailable: {error}"],
        )

    def unavailable_terminal_report(self, *, symbol: str | None, error: str) -> PredictionTerminalReport:
        hype = self.unavailable_report(symbol=symbol, error=error)
        return PredictionTerminalReport(
            available=False,
            requested_symbol=symbol.upper() if symbol else None,
            hype=hype,
            wallets=WalletIntelligenceReport(available=False, notes=[f"Wallet intelligence unavailable: {error}"]),
            resolution=ResolutionRiskReport(),
            microstructure=ClobMicrostructureReport(),
            cross_venue=CrossVenueArbReport(available=False, notes=[f"Cross-venue scan unavailable: {error}"]),
            source_monitor=SourceMonitorReport(notes=[f"Source monitor unavailable: {error}"]),
            warnings=[f"Prediction terminal unavailable: {error}"],
        )

    async def _fetch_books_for_terminal(
        self,
        client: httpx.AsyncClient,
        *,
        events: list[dict[str, Any]],
        symbol: str | None,
        max_books: int,
    ) -> dict[str, dict[str, Any]]:
        requested_symbol = symbol.upper() if symbol else None
        ranked = sorted(
            events,
            key=lambda event: self._to_event(event, requested_symbol=requested_symbol).relevance_score,
            reverse=True,
        )
        token_ids: list[str] = []
        for event in ranked:
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                if market.get("closed") is True or market.get("acceptingOrders") is False:
                    continue
                if not market.get("enableOrderBook", event.get("enableOrderBook", False)):
                    continue
                ids = self._json_list(market.get("clobTokenIds"))
                if ids:
                    token_ids.append(str(ids[0]))
                if len(token_ids) >= max_books:
                    break
            if len(token_ids) >= max_books:
                break

        async def fetch_one(token_id: str) -> tuple[str, dict[str, Any]]:
            try:
                response = await client.get(f"{self.clob_url}/book", params={"token_id": token_id})
                response.raise_for_status()
                payload = response.json()
                return token_id, payload if isinstance(payload, dict) else {}
            except Exception:
                return token_id, {}

        pairs = await asyncio.gather(*(fetch_one(token_id) for token_id in token_ids))
        return {token_id: book for token_id, book in pairs}

    def _build_wallet_report(self, *, leaderboard: Any, trades: Any, limit: int) -> WalletIntelligenceReport:
        leaderboard_rows = leaderboard if isinstance(leaderboard, list) else []
        trade_rows = trades if isinstance(trades, list) else []

        entries: list[WalletLeaderboardEntry] = []
        for row in leaderboard_rows[: max(limit, 1)]:
            if not isinstance(row, dict):
                continue
            wallet = str(row.get("proxyWallet") or "")
            entries.append(
                WalletLeaderboardEntry(
                    rank=int(self._number(row.get("rank")) or len(entries) + 1),
                    wallet=wallet,
                    user_name=str(row.get("userName") or wallet or "unknown"),
                    x_username=str(row.get("xUsername") or ""),
                    pnl=float(row.get("pnl") or 0.0),
                    volume=self._number(row.get("vol") or row.get("volume")),
                    verified_badge=bool(row.get("verifiedBadge")),
                    profile_url=f"https://polymarket.com/profile/{wallet}" if wallet else "https://polymarket.com",
                )
            )

        rank_by_wallet = {entry.wallet.lower(): entry.rank for entry in entries}
        whale_trades: list[WhaleTrade] = []
        for row in sorted(
            (trade for trade in trade_rows if isinstance(trade, dict)),
            key=lambda trade: self._number(trade.get("size")) * self._number(trade.get("price")),
            reverse=True,
        )[: max(limit, 1)]:
            wallet = str(row.get("proxyWallet") or "")
            notional = self._number(row.get("size")) * self._number(row.get("price"))
            rank = rank_by_wallet.get(wallet.lower())
            title = str(row.get("title") or "Untitled market")
            slug = str(row.get("slug") or row.get("eventSlug") or "")
            signal = "copy_watch" if rank and rank <= 25 else "flow_watch"
            rationale = (
                f"Top leaderboard wallet rank {rank} traded this market."
                if rank
                else "Large public trade; track follow-through before using as a signal."
            )
            whale_trades.append(
                WhaleTrade(
                    wallet=wallet,
                    pseudonym=str(row.get("pseudonym") or row.get("name") or ""),
                    side=str(row.get("side") or "").upper(),
                    title=title,
                    slug=slug,
                    outcome=str(row.get("outcome") or ""),
                    size=self._number(row.get("size")),
                    price=self._number(row.get("price")),
                    notional=notional,
                    timestamp=self._parse_unix_timestamp(row.get("timestamp")),
                    signal=signal,
                    rationale=rationale,
                    source_url=f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
                )
            )

        return WalletIntelligenceReport(
            available=bool(entries or whale_trades),
            leaderboard=entries,
            whale_trades=whale_trades,
            total_leaderboard_pnl=sum(entry.pnl for entry in entries),
            total_leaderboard_volume=sum(entry.volume for entry in entries),
            notes=[
                "Leaderboard and trade flow are public snapshots.",
                "PnL deltas require repeated snapshots; this endpoint exposes the live baseline.",
            ],
        )

    def _build_resolution_report(
        self,
        events: list[dict[str, Any]],
        *,
        terminal_events: list[PolymarketHypeEvent],
        limit: int,
    ) -> ResolutionRiskReport:
        event_by_slug = {str(event.get("slug") or ""): event for event in events}
        items: list[ResolutionRiskItem] = []
        for hype_event in terminal_events[: max(limit * 2, limit)]:
            event = event_by_slug.get(hype_event.slug, {})
            description = str(event.get("description") or "")
            source = str(event.get("resolutionSource") or "")
            statuses = self._collect_uma_statuses(event)
            flags = self._resolution_flags(event, description=description, source=source, statuses=statuses)
            score = min(1.0, 0.12 * len(flags) + (0.18 if not source else 0.0) + (0.12 if "credible reporting" in description.lower() else 0.0))
            items.append(
                ResolutionRiskItem(
                    title=hype_event.title,
                    slug=hype_event.slug,
                    source_url=hype_event.source_url,
                    end_date=hype_event.end_date,
                    resolution_source=source,
                    description_excerpt=self._excerpt(description, 260),
                    uma_statuses=statuses,
                    risk_flags=flags,
                    ambiguity_score=score,
                )
            )
            if len(items) >= limit:
                break

        items.sort(key=lambda item: (item.ambiguity_score, len(item.risk_flags)), reverse=True)
        return ResolutionRiskReport(
            items=items,
            highest_ambiguity_score=max((item.ambiguity_score for item in items), default=0.0),
        )

    def _build_microstructure_report(
        self,
        events: list[dict[str, Any]],
        *,
        terminal_events: list[PolymarketHypeEvent],
        books_by_token: dict[str, dict[str, Any]],
        limit: int,
    ) -> ClobMicrostructureReport:
        event_by_slug = {str(event.get("slug") or ""): event for event in events}
        items: list[ClobMicrostructureItem] = []
        for hype_event in terminal_events:
            event = event_by_slug.get(hype_event.slug, {})
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                if market.get("closed") is True or market.get("acceptingOrders") is False:
                    continue
                token_ids = [str(token_id) for token_id in self._json_list(market.get("clobTokenIds"))]
                outcomes = [str(outcome) for outcome in self._json_list(market.get("outcomes"))]
                token_id = token_ids[0] if token_ids else ""
                if not token_id:
                    continue
                book = books_by_token.get(token_id, {})
                item = self._microstructure_item(
                    hype_event=hype_event,
                    market=market,
                    token_id=token_id,
                    outcome=outcomes[0] if outcomes else str(market.get("yes_sub_title") or "Yes"),
                    book=book,
                )
                items.append(item)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        return ClobMicrostructureReport(
            items=items,
            thin_book_count=sum(1 for item in items if "thin_near_mid_depth" in item.flags),
            negative_risk_count=sum(1 for item in items if item.negative_risk),
        )

    def _build_cross_venue_report(
        self,
        events: list[dict[str, Any]],
        *,
        terminal_events: list[PolymarketHypeEvent],
        kalshi_events: Any,
        limit: int,
    ) -> CrossVenueArbReport:
        kalshi_rows = kalshi_events.get("events", []) if isinstance(kalshi_events, dict) else []
        candidates: list[CrossVenueCandidate] = []
        for hype_event in terminal_events:
            pm_terms = self._terms(hype_event.title)
            if len(pm_terms) < 2:
                continue
            polymarket_probability = self._event_primary_probability(events, hype_event.slug)
            for kalshi_event in kalshi_rows:
                if not isinstance(kalshi_event, dict):
                    continue
                kalshi_title = str(kalshi_event.get("title") or "")
                matched_terms = sorted(pm_terms.intersection(self._terms(kalshi_title)))
                if len(matched_terms) < 2:
                    continue
                kalshi_market = self._first_active_kalshi_market(kalshi_event)
                kalshi_probability = self._kalshi_probability(kalshi_market)
                gap = (
                    abs(polymarket_probability - kalshi_probability)
                    if polymarket_probability is not None and kalshi_probability is not None
                    else None
                )
                mapped_symbols, _, _ = self._map_narrative(title=hype_event.title, tags=hype_event.tags, requested_symbol=None)
                candidates.append(
                    CrossVenueCandidate(
                        title=hype_event.title,
                        polymarket_slug=hype_event.slug,
                        polymarket_probability=polymarket_probability,
                        kalshi_title=kalshi_title,
                        kalshi_ticker=str((kalshi_market or {}).get("ticker") or kalshi_event.get("event_ticker") or ""),
                        kalshi_probability=kalshi_probability,
                        probability_gap=gap,
                        matched_terms=matched_terms[:8],
                        comparable_underlying=mapped_symbols,
                        note="Potential comparison only; confirm rule equivalence before treating as arbitrage.",
                    )
                )
                break
            if len(candidates) >= limit:
                break

        candidates.sort(key=lambda candidate: candidate.probability_gap or 0.0, reverse=True)
        return CrossVenueArbReport(
            available=isinstance(kalshi_events, dict),
            candidates=candidates,
            notes=[
                "Cross-venue gaps are only useful when both markets resolve on materially identical rules.",
                "Underlying/liquid-market comparison is provided through mapped Pepper symbols.",
            ],
        )

    def _build_source_monitor_report(
        self,
        events: list[dict[str, Any]],
        *,
        terminal_events: list[PolymarketHypeEvent],
        limit: int,
    ) -> SourceMonitorReport:
        event_by_slug = {str(event.get("slug") or ""): event for event in events}
        items: list[SourceMonitorItem] = []
        for hype_event in terminal_events[:limit]:
            event = event_by_slug.get(hype_event.slug, {})
            description = str(event.get("description") or "")
            official_sources = self._official_sources_for_event(title=hype_event.title, description=description)
            trigger_terms = self._trigger_terms(hype_event.title, description)
            items.append(
                SourceMonitorItem(
                    title=hype_event.title,
                    slug=hype_event.slug,
                    source_url=hype_event.source_url,
                    mapped_symbols=hype_event.mapped_symbols,
                    official_sources=official_sources,
                    news_queries=[f'"{term}"' for term in trigger_terms[:4]],
                    x_queries=[f'{term} lang:en' for term in trigger_terms[:4]],
                    telegram_queries=trigger_terms[:4],
                    trigger_terms=trigger_terms,
                )
            )
        return SourceMonitorReport(
            items=items,
            notes=[
                "Source monitoring derives watch queries from resolution text and mapped symbols.",
                "Wire these queries to external news/X/Telegram connectors before using them for alerts.",
            ],
        )

    def _to_event(self, event: dict[str, Any], *, requested_symbol: str | None) -> PolymarketHypeEvent:
        title = str(event.get("title") or event.get("question") or "Untitled market")
        slug = str(event.get("slug") or "")
        tags = self._extract_tags(event)
        mapped_symbols, relevance, risk_note = self._map_narrative(title=title, tags=tags, requested_symbol=requested_symbol)
        volume_24h = self._number(event.get("volume24hr") or event.get("volume_24h"))
        volume_total = self._number(event.get("volume"))
        liquidity = self._number(event.get("liquidity"))
        relevance_score = self._score_event(
            relevance=relevance,
            mapped_symbols=mapped_symbols,
            requested_symbol=requested_symbol,
            volume_24h=volume_24h,
            liquidity=liquidity,
        )
        return PolymarketHypeEvent(
            title=title,
            slug=slug,
            source_url=f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
            volume_24h=volume_24h,
            volume_total=volume_total,
            liquidity=liquidity,
            end_date=self._parse_datetime(event.get("endDate") or event.get("end_date")),
            tags=tags,
            mapped_symbols=mapped_symbols,
            relevance=relevance,
            relevance_score=relevance_score,
            risk_note=risk_note,
        )

    def _microstructure_item(
        self,
        *,
        hype_event: PolymarketHypeEvent,
        market: dict[str, Any],
        token_id: str,
        outcome: str,
        book: dict[str, Any],
    ) -> ClobMicrostructureItem:
        bids = self._depth_levels(book.get("bids") or [])
        asks = self._depth_levels(book.get("asks") or [])
        best_bid = max((level.price for level in bids), default=self._optional_number(market.get("bestBid")))
        best_ask = min((level.price for level in asks), default=self._optional_number(market.get("bestAsk")))
        midpoint = self._midpoint(best_bid, best_ask)
        spread = self._optional_number(market.get("spread"))
        if best_bid is not None and best_ask is not None:
            spread = max(best_ask - best_bid, 0.0)

        bid_depth_near_mid = self._near_mid_depth(bids, midpoint=midpoint, side="bid")
        ask_depth_near_mid = self._near_mid_depth(asks, midpoint=midpoint, side="ask")
        bid_wall = max((level.size for level in bids), default=0.0)
        ask_wall = max((level.size for level in asks), default=0.0)
        largest_wall_side = "bid" if bid_wall > ask_wall else "ask" if ask_wall > 0 else "none"
        largest_wall_size = max(bid_wall, ask_wall)
        fill_score = self._fill_probability_score(spread=spread, bid_depth=bid_depth_near_mid, ask_depth=ask_depth_near_mid)
        negative_risk = bool(market.get("negRisk") or book.get("neg_risk"))
        flags: list[str] = []
        if spread is None:
            flags.append("missing_spread")
        elif spread >= 0.05:
            flags.append("wide_spread")
        if bid_depth_near_mid + ask_depth_near_mid < 500:
            flags.append("thin_near_mid_depth")
        if negative_risk:
            flags.append("negative_risk_bundle")

        return ClobMicrostructureItem(
            title=hype_event.title,
            slug=hype_event.slug,
            outcome=outcome,
            token_id=token_id,
            source_url=hype_event.source_url,
            best_bid=best_bid,
            best_ask=best_ask,
            midpoint=midpoint,
            spread=spread,
            bid_depth_near_mid=bid_depth_near_mid,
            ask_depth_near_mid=ask_depth_near_mid,
            largest_wall_side=largest_wall_side,
            largest_wall_size=largest_wall_size,
            fill_probability_score=fill_score,
            negative_risk=negative_risk,
            flags=flags,
        )

    def _depth_levels(self, rows: Any) -> list[BookDepthLevel]:
        levels: list[BookDepthLevel] = []
        if not isinstance(rows, list):
            return levels
        for row in rows:
            if not isinstance(row, dict):
                continue
            levels.append(
                BookDepthLevel(
                    price=self._number(row.get("price")),
                    size=self._number(row.get("size")),
                )
            )
        return levels

    def _near_mid_depth(self, levels: list[BookDepthLevel], *, midpoint: float | None, side: Literal["bid", "ask"]) -> float:
        if midpoint is None:
            return sum(level.size for level in levels[:5])
        if side == "bid":
            return sum(level.size for level in levels if midpoint - 0.02 <= level.price <= midpoint)
        return sum(level.size for level in levels if midpoint <= level.price <= midpoint + 0.02)

    def _fill_probability_score(self, *, spread: float | None, bid_depth: float, ask_depth: float) -> float:
        if spread is None:
            return 0.0
        spread_score = max(0.0, 1.0 - min(spread / 0.1, 1.0))
        depth_score = min((bid_depth + ask_depth) / 5_000, 1.0)
        return round((spread_score * 0.65) + (depth_score * 0.35), 4)

    def _midpoint(self, best_bid: float | None, best_ask: float | None) -> float | None:
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / 2

    def _collect_uma_statuses(self, event: dict[str, Any]) -> list[str]:
        statuses: list[str] = []
        for market in event.get("markets") or []:
            if not isinstance(market, dict):
                continue
            statuses.extend(str(status) for status in self._json_list(market.get("umaResolutionStatuses")))
            if status := market.get("umaResolutionStatus"):
                statuses.append(str(status))
        return sorted(set(statuses), key=str.lower)

    def _resolution_flags(
        self,
        event: dict[str, Any],
        *,
        description: str,
        source: str,
        statuses: list[str],
    ) -> list[str]:
        text = f"{event.get('title', '')} {description}".lower()
        flags: list[str] = []
        if not source and "primary resolution source" not in text:
            flags.append("source_not_structured")
        if "credible reporting" in text or "consensus" in text:
            flags.append("credible_reporting_discretion")
        if "disputed" in {status.lower() for status in statuses}:
            flags.append("uma_dispute_history")
        if "before" in text and ("by" in text or "deadline" in text):
            flags.append("deadline_sensitive")
        if any(term in text for term in ("official", "reported by", "announced by")):
            flags.append("external_source_dependency")
        if bool(event.get("restricted")):
            flags.append("restricted_market")
        return sorted(set(flags))

    def _event_primary_probability(self, events: list[dict[str, Any]], slug: str) -> float | None:
        for event in events:
            if str(event.get("slug") or "") != slug:
                continue
            for market in event.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                bid = self._optional_number(market.get("bestBid"))
                ask = self._optional_number(market.get("bestAsk"))
                if bid is not None and ask is not None:
                    return (bid + ask) / 2
                prices = self._json_list(market.get("outcomePrices"))
                if prices:
                    return self._optional_number(prices[0])
        return None

    def _first_active_kalshi_market(self, event: dict[str, Any]) -> dict[str, Any] | None:
        for market in event.get("markets") or []:
            if isinstance(market, dict) and str(market.get("status") or "").lower() in {"active", "open"}:
                return market
        markets = event.get("markets") or []
        return markets[0] if markets and isinstance(markets[0], dict) else None

    def _kalshi_probability(self, market: dict[str, Any] | None) -> float | None:
        if not market:
            return None
        bid = self._optional_number(market.get("yes_bid_dollars"))
        ask = self._optional_number(market.get("yes_ask_dollars"))
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return self._optional_number(market.get("last_price_dollars"))

    def _terms(self, text: str) -> set[str]:
        stop = {
            "will",
            "the",
            "any",
            "before",
            "after",
            "when",
            "what",
            "with",
            "this",
            "that",
            "market",
            "winner",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]{3,}", text.lower())
            if token not in stop
        }

    def _official_sources_for_event(self, *, title: str, description: str) -> list[str]:
        text = f"{title} {description}".lower()
        sources: list[str] = []
        if "microstrategy" in text or "mstr" in text:
            sources.extend(["MicroStrategy investor relations", "SEC EDGAR company filings", "Bitcoin on-chain treasury wallets"])
        if "bitcoin" in text or "btc" in text:
            sources.extend(["Major exchange BTC/USD reference prices", "Bitcoin on-chain data"])
        if any(term in text for term in ("fed", "rate cut", "interest rate", "cpi", "inflation", "jobs report")):
            sources.extend(["Federal Reserve releases", "BLS economic releases", "Treasury yield data"])
        if any(term in text for term in ("election", "presidential", "senate", "house")):
            sources.extend(["Official election authority releases", "Candidate campaign announcements", "Major wire reporting"])
        if any(term in text for term in ("china", "taiwan", "russia", "ukraine", "iran", "nato")):
            sources.extend(["Official government statements", "Major wire reporting", "Defense ministry releases"])
        return sorted(set(sources)) or ["Polymarket market page", "Primary resolution source listed in market rules"]

    def _trigger_terms(self, title: str, description: str) -> list[str]:
        terms = list(self._terms(title))[:8]
        if "primary resolution source" in description.lower():
            terms.append("primary resolution source")
        if "credible reporting" in description.lower():
            terms.append("credible reporting")
        return sorted(set(terms), key=str.lower)

    def _extract_tags(self, event: dict[str, Any]) -> list[str]:
        tags: list[str] = []
        for tag in event.get("tags") or []:
            if isinstance(tag, dict):
                label = tag.get("label") or tag.get("slug") or tag.get("name")
                if label:
                    tags.append(str(label))
            elif tag:
                tags.append(str(tag))
        if category := event.get("category"):
            tags.append(str(category))
        return sorted(set(tags), key=str.lower)

    def _map_narrative(
        self,
        *,
        title: str,
        tags: list[str],
        requested_symbol: str | None,
    ) -> tuple[list[str], NarrativeRelevance, str]:
        text = f"{title} {' '.join(tags)}".lower()
        mapped: set[str] = set()
        direct_symbols: set[str] = set()
        risk_notes: list[str] = []

        if any(token in text for token in ("bitcoin", "btc", "microstrategy", "mstr", "$150k")):
            mapped.update({"BTC-USD", "MSTR"})
            direct_symbols.update({"BTC-USD", "MSTR"})
            risk_notes.append("Bitcoin narrative can affect BTC risk appetite and crypto beta.")
        if any(token in text for token in ("ethereum", "eth")):
            mapped.add("ETH-USD")
            direct_symbols.add("ETH-USD")
            risk_notes.append("Ethereum narrative can affect ETH and broader crypto liquidity.")
        if any(token in text for token in ("fed", "rate cut", "interest rate", "inflation", "cpi", "jobs report")):
            mapped.update({"SPY", "QQQ", "DXY"})
            risk_notes.append("Macro-rate narrative can affect broad risk assets and USD liquidity.")
        if any(token in text for token in ("election", "presidential", "house", "senate", "tariff")):
            mapped.update({"SPY", "QQQ"})
            risk_notes.append("Political narrative can raise headline risk and market volatility.")
        if any(token in text for token in ("china", "taiwan", "russia", "ukraine", "nato", "iran", "war", "military")):
            mapped.update({"SPY", "QQQ", "BTC-USD"})
            risk_notes.append("Geopolitical narrative can create gap risk and liquidity shocks.")
        if any(token in text for token in ("nba", "fifa", "world cup", "nhl", "champions league", "sports")) and not mapped:
            risk_notes.append("Sports attention is high but not directly useful for Pepper trading decisions.")

        mapped_symbols = sorted(mapped)
        if requested_symbol and requested_symbol in direct_symbols:
            return mapped_symbols, "direct", " ".join(risk_notes)
        if not requested_symbol and direct_symbols:
            return mapped_symbols, "direct", " ".join(risk_notes)
        if mapped_symbols:
            return mapped_symbols, "macro", " ".join(risk_notes)
        if risk_notes:
            return [], "watch", " ".join(risk_notes)
        return [], "unmapped", "No direct Pepper asset mapping; useful only as platform hype context."

    def _score_event(
        self,
        *,
        relevance: str,
        mapped_symbols: list[str],
        requested_symbol: str | None,
        volume_24h: float,
        liquidity: float,
    ) -> float:
        relevance_weight = {
            "direct": 4.0,
            "macro": 2.5,
            "watch": 1.0,
            "unmapped": 0.25,
        }.get(relevance, 0.25)
        symbol_bonus = 2.0 if requested_symbol and requested_symbol in mapped_symbols else 0.0
        volume_score = min(volume_24h / 1_000_000, 5.0)
        liquidity_score = min(liquidity / 1_000_000, 2.0)
        return relevance_weight + symbol_bonus + volume_score + liquidity_score

    def _json_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []

    def _number(self, value: Any) -> float:
        try:
            return max(float(value or 0.0), 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _optional_number(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return None

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_unix_timestamp(self, value: Any) -> datetime | None:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=UTC)

    def _excerpt(self, value: str, max_length: int) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) <= max_length:
            return cleaned
        return f"{cleaned[: max_length - 3]}..."
