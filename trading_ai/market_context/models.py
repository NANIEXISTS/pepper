from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


NarrativeRelevance = Literal["direct", "macro", "watch", "unmapped"]


class PolymarketHypeEvent(BaseModel):
    title: str
    slug: str
    source_url: str
    volume_24h: float = Field(ge=0.0)
    volume_total: float = Field(ge=0.0)
    liquidity: float = Field(ge=0.0)
    end_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    mapped_symbols: list[str] = Field(default_factory=list)
    relevance: NarrativeRelevance = "unmapped"
    relevance_score: float = Field(ge=0.0)
    risk_note: str


class PolymarketHypeReport(BaseModel):
    source: str = "polymarket_gamma"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available: bool = True
    requested_symbol: str | None = None
    events_scanned: int = Field(ge=0)
    mapped_event_count: int = Field(ge=0)
    direct_event_count: int = Field(ge=0)
    total_volume_24h: float = Field(ge=0.0)
    top_symbols: list[str] = Field(default_factory=list)
    events: list[PolymarketHypeEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safe_use: str = (
        "Read-only narrative context. Do not trade automatically from prediction-market hype, "
        "and do not mix this signal into an active paper experiment unless the experiment is restarted."
    )


class WalletLeaderboardEntry(BaseModel):
    rank: int = Field(ge=1)
    wallet: str
    user_name: str
    x_username: str = ""
    pnl: float = 0.0
    volume: float = Field(default=0.0, ge=0.0)
    verified_badge: bool = False
    profile_url: str


class WhaleTrade(BaseModel):
    wallet: str
    pseudonym: str = ""
    side: str
    title: str
    slug: str
    outcome: str = ""
    size: float = Field(ge=0.0)
    price: float = Field(ge=0.0)
    notional: float = Field(ge=0.0)
    timestamp: datetime | None = None
    signal: Literal["copy_watch", "contra_watch", "flow_watch"] = "flow_watch"
    rationale: str
    source_url: str


class WalletIntelligenceReport(BaseModel):
    source: str = "polymarket_data_api"
    available: bool = True
    leaderboard: list[WalletLeaderboardEntry] = Field(default_factory=list)
    whale_trades: list[WhaleTrade] = Field(default_factory=list)
    total_leaderboard_pnl: float = 0.0
    total_leaderboard_volume: float = Field(default=0.0, ge=0.0)
    notes: list[str] = Field(default_factory=list)


class ResolutionRiskItem(BaseModel):
    title: str
    slug: str
    source_url: str
    end_date: datetime | None = None
    resolution_source: str = ""
    description_excerpt: str = ""
    uma_statuses: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    ambiguity_score: float = Field(ge=0.0, le=1.0)


class ResolutionRiskReport(BaseModel):
    source: str = "polymarket_gamma"
    items: list[ResolutionRiskItem] = Field(default_factory=list)
    highest_ambiguity_score: float = Field(default=0.0, ge=0.0, le=1.0)


class BookDepthLevel(BaseModel):
    price: float = Field(ge=0.0)
    size: float = Field(ge=0.0)


class ClobMicrostructureItem(BaseModel):
    title: str
    slug: str
    outcome: str
    token_id: str
    source_url: str
    best_bid: float | None = None
    best_ask: float | None = None
    midpoint: float | None = None
    spread: float | None = None
    bid_depth_near_mid: float = Field(default=0.0, ge=0.0)
    ask_depth_near_mid: float = Field(default=0.0, ge=0.0)
    largest_wall_side: Literal["bid", "ask", "none"] = "none"
    largest_wall_size: float = Field(default=0.0, ge=0.0)
    fill_probability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    negative_risk: bool = False
    flags: list[str] = Field(default_factory=list)


class ClobMicrostructureReport(BaseModel):
    source: str = "polymarket_clob"
    items: list[ClobMicrostructureItem] = Field(default_factory=list)
    thin_book_count: int = Field(default=0, ge=0)
    negative_risk_count: int = Field(default=0, ge=0)


class CrossVenueCandidate(BaseModel):
    title: str
    polymarket_slug: str
    polymarket_probability: float | None = None
    kalshi_title: str = ""
    kalshi_ticker: str = ""
    kalshi_probability: float | None = None
    probability_gap: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    comparable_underlying: list[str] = Field(default_factory=list)
    note: str


class CrossVenueArbReport(BaseModel):
    source: str = "polymarket_gamma+kalshi_public"
    available: bool = True
    candidates: list[CrossVenueCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SourceMonitorItem(BaseModel):
    title: str
    slug: str
    source_url: str
    mapped_symbols: list[str] = Field(default_factory=list)
    official_sources: list[str] = Field(default_factory=list)
    news_queries: list[str] = Field(default_factory=list)
    x_queries: list[str] = Field(default_factory=list)
    telegram_queries: list[str] = Field(default_factory=list)
    trigger_terms: list[str] = Field(default_factory=list)


class SourceMonitorReport(BaseModel):
    source: str = "derived_resolution_watchlist"
    items: list[SourceMonitorItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PredictionTerminalReport(BaseModel):
    source: str = "polymarket_prediction_terminal"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available: bool = True
    requested_symbol: str | None = None
    hype: PolymarketHypeReport
    wallets: WalletIntelligenceReport
    resolution: ResolutionRiskReport
    microstructure: ClobMicrostructureReport
    cross_venue: CrossVenueArbReport
    source_monitor: SourceMonitorReport
    warnings: list[str] = Field(default_factory=list)
    safe_use: str = (
        "Public prediction-market intelligence only. It can support research, source monitoring, "
        "and operator review, but it is not an order path."
    )


ProfitHunterVerdict = Literal["TRADE", "NO_TRADE", "INSUFFICIENT_EDGE"]
ProfitHunterMethod = Literal[
    "source_latency",
    "crypto_close",
    "negative_risk_basket",
    "wallet_delta",
    "clob_microstructure",
    "cross_venue_arb_watch",
]


class ProfitHunterPaperTicket(BaseModel):
    venue: str = "polymarket"
    mode: Literal["paper"] = "paper"
    side: Literal["BUY_YES", "BUY_NO", "WATCH"] = "BUY_YES"
    title: str
    slug: str
    outcome: str = ""
    token_id: str = ""
    entry_price: float = Field(ge=0.0, le=1.0)
    quantity: float = Field(ge=0.0)
    notional_usd: float = Field(ge=0.0)
    max_loss_usd: float = Field(ge=0.0)
    take_profit_price: float = Field(ge=0.0, le=1.0)
    stop_loss_price: float = Field(ge=0.0, le=1.0)
    time_stop_minutes: int = Field(ge=1)
    exit_plan: str


class ProfitHunterCandidate(BaseModel):
    rank: int = Field(ge=1)
    method: ProfitHunterMethod
    title: str
    slug: str
    source_url: str
    outcome: str = ""
    token_id: str = ""
    score: float = Field(ge=0.0, le=1.0)
    estimated_edge_score: float = Field(ge=0.0, le=1.0)
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    fill_probability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    volume_24h: float = Field(default=0.0, ge=0.0)
    liquidity: float = Field(default=0.0, ge=0.0)
    ambiguity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    whale_notional_usd: float = Field(default=0.0, ge=0.0)
    new_whale_flow: bool = False
    negative_risk: bool = False
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source_checks: list[str] = Field(default_factory=list)
    paper_ticket: ProfitHunterPaperTicket | None = None


class ProfitHunterReport(BaseModel):
    source: str = "pepper_polymarket_profit_hunter"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available: bool = True
    requested_symbol: str | None = None
    horizon_minutes: int = Field(default=60, ge=5, le=240)
    mode: Literal["paper"] = "paper"
    verdict: ProfitHunterVerdict
    action: str
    candidate_count: int = Field(default=0, ge=0)
    top_score: float = Field(default=0.0, ge=0.0, le=1.0)
    min_trade_score: float = Field(default=0.72, ge=0.0, le=1.0)
    max_stake_usd: float = Field(default=25.0, gt=0.0)
    no_trade_reason: str = ""
    trade_candidate: ProfitHunterCandidate | None = None
    candidates: list[ProfitHunterCandidate] = Field(default_factory=list)
    summary: dict[str, int | float | str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    safe_use: str = (
        "Paper-only opportunity ranking. This report can create a paper ticket for review, "
        "but it does not place Polymarket orders or guarantee profit."
    )
