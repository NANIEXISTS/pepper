const state = {
  symbol: "BTC-USD",
  timeframe: "1h",
  overview: null,
  strategyDraft: null,
  strategyBacktest: null,
  profitHunter: null,
};

const elements = {
  symbolInput: document.getElementById("symbol-input"),
  timeframeSelect: document.getElementById("timeframe-select"),
  refreshButton: document.getElementById("refresh-button"),
  paperCycleButton: document.getElementById("paper-cycle-button"),
  refreshStatus: document.getElementById("refresh-status"),
  cycleStatus: document.getElementById("cycle-status"),
  profitPathHeadline: document.getElementById("profit-path-headline"),
  profitPathVerdict: document.getElementById("profit-path-verdict"),
  profitPathCopy: document.getElementById("profit-path-copy"),
  profitPathSteps: document.getElementById("profit-path-steps"),
  hypeRadarSummary: document.getElementById("hype-radar-summary"),
  hypeRadarList: document.getElementById("hype-radar-list"),
  predictionTerminalSummary: document.getElementById("prediction-terminal-summary"),
  terminalSnapshotButton: document.getElementById("terminal-snapshot-button"),
  terminalSnapshotStatus: document.getElementById("terminal-snapshot-status"),
  terminalDeltaSummary: document.getElementById("terminal-delta-summary"),
  terminalWallets: document.getElementById("terminal-wallets"),
  terminalRisks: document.getElementById("terminal-risks"),
  terminalBooks: document.getElementById("terminal-books"),
  terminalSources: document.getElementById("terminal-sources"),
  profitHunterAnswer: document.getElementById("profit-hunter-answer"),
  profitHunterVerdict: document.getElementById("profit-hunter-verdict"),
  profitHunterWhy: document.getElementById("profit-hunter-why"),
  profitHunterButton: document.getElementById("profit-hunter-button"),
  profitHunterStatus: document.getElementById("profit-hunter-status"),
  profitHunterTicket: document.getElementById("profit-hunter-ticket"),
  profitHunterCandidates: document.getElementById("profit-hunter-candidates"),
  edgeScanButton: document.getElementById("edge-scan-button"),
  edgeScanStatus: document.getElementById("edge-scan-status"),
  edgeScanSummary: document.getElementById("edge-scan-summary"),
  jobForm: document.getElementById("job-form"),
  jobSymbolInput: document.getElementById("job-symbol-input"),
  jobTimeframeSelect: document.getElementById("job-timeframe-select"),
  jobLookbackInput: document.getElementById("job-lookback-input"),
  jobIntervalInput: document.getElementById("job-interval-input"),
  jobAutoStartInput: document.getElementById("job-auto-start-input"),
  jobSubmitButton: document.getElementById("job-submit-button"),
  manualOrderForm: document.getElementById("manual-order-form"),
  manualSymbolInput: document.getElementById("manual-symbol-input"),
  manualTimeframeSelect: document.getElementById("manual-timeframe-select"),
  manualSideSelect: document.getElementById("manual-side-select"),
  manualQuantityInput: document.getElementById("manual-quantity-input"),
  manualStopLossInput: document.getElementById("manual-stop-loss-input"),
  manualTakeProfitInput: document.getElementById("manual-take-profit-input"),
  manualOrderButton: document.getElementById("manual-order-button"),
  strategyForm: document.getElementById("strategy-form"),
  strategyPromptInput: document.getElementById("strategy-prompt-input"),
  strategyDraftButton: document.getElementById("strategy-draft-button"),
  strategyValidateButton: document.getElementById("strategy-validate-button"),
  strategyBacktestButton: document.getElementById("strategy-backtest-button"),
  strategyStatus: document.getElementById("strategy-status"),
  liveReadinessStatus: document.getElementById("live-readiness-status"),
  liveReadinessVerdict: document.getElementById("live-readiness-verdict"),
  liveReadinessSubtext: document.getElementById("live-readiness-subtext"),
  clientBriefAnswer: document.getElementById("client-brief-answer"),
  clientBriefWhy: document.getElementById("client-brief-why"),
  clientNextAction: document.getElementById("client-next-action"),
  clientProofList: document.getElementById("client-proof-list"),
  burnInProgressLabel: document.getElementById("burn-in-progress-label"),
  burnInProgress: document.getElementById("burn-in-progress"),
  readinessGatesList: document.getElementById("readiness-gates-list"),
  readinessBlockersList: document.getElementById("readiness-blockers-list"),
  readinessActionStatus: document.getElementById("readiness-action-status"),
  drawdownSelftestButton: document.getElementById("drawdown-selftest-button"),
  credentialAuditForm: document.getElementById("credential-audit-form"),
  credentialVenueInput: document.getElementById("credential-venue-input"),
  credentialScopeSelect: document.getElementById("credential-scope-select"),
  credentialAuditorInput: document.getElementById("credential-auditor-input"),
  credentialNotesInput: document.getElementById("credential-notes-input"),
  credentialAuditButton: document.getElementById("credential-audit-button"),
  rampPlanForm: document.getElementById("ramp-plan-form"),
  rampVenueInput: document.getElementById("ramp-venue-input"),
  rampCapInput: document.getElementById("ramp-cap-input"),
  rampNotesInput: document.getElementById("ramp-notes-input"),
  rampPlanButton: document.getElementById("ramp-plan-button"),
};

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Math.abs(Number(value ?? 0)) >= 100 ? 0 : 2,
  }).format(value ?? 0);
}

function percent(value) {
  return `${(Number(value ?? 0) * 100).toFixed(2)}%`;
}

function number(value, digits = 2) {
  return Number(value ?? 0).toFixed(digits);
}

function setText(id, value, className = "") {
  const node = document.getElementById(id);
  node.textContent = value;
  node.className = className;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function labelFromKey(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll(":", ": ")
    .replace(/\s+/g, " ")
    .trim();
}

function describeBlocker(reason, readiness) {
  if (reason.startsWith("paper_burn_in_incomplete")) {
    const observedDays = Number(readiness.paper_burn_in_days_observed || 0);
    const requiredDays = Number(readiness.required_burn_in_days || 28);
    const remainingDays = Math.max(requiredDays - observedDays, 0);
    return `${remainingDays} more paper burn-in day${remainingDays === 1 ? "" : "s"} needed`;
  }
  if (reason.startsWith("paper_profitability_incomplete")) {
    const observedDays = Number(readiness.fourteen_day_profitability?.equity_days_observed || 0);
    const requiredDays = Number(readiness.fourteen_day_profitability?.required_days || 14);
    const remainingDays = Math.max(requiredDays - observedDays, 0);
    return `${remainingDays} more paper equity day${remainingDays === 1 ? "" : "s"} needed before judging profit`;
  }
  if (reason === "paper_profitability_missing_equity_payloads") {
    return "Some completed paper runs are missing portfolio equity evidence";
  }
  if (reason === "paper_profitability_not_positive") {
    return "The latest 14-day paper run is not net profitable";
  }
  if (reason === "credential_audit_missing_or_stale") {
    return "Credential audit must be recorded or refreshed";
  }
  if (reason === "drawdown_breaker_selftest_missing_or_stale") {
    return "Drawdown self-test must be run again";
  }
  if (reason === "drawdown_breaker_selftest_failed") {
    return "Drawdown self-test failed and must be investigated";
  }
  if (reason === "ramp_plan_not_recorded") {
    return "First-capital ramp plan must be recorded";
  }
  if (reason === "ramp_plan_exceeds_configured_cap") {
    return "Ramp plan exceeds the configured capital cap";
  }
  if (reason === "live_trading_disabled_by_config") {
    return "Live trading is still disabled in config";
  }
  return labelFromKey(reason);
}

function nextActionFor(readiness, blockers) {
  if (readiness.live_capital_allowed) {
    return "Live gate is clear. Keep reviewing evidence before enabling capital.";
  }
  if (blockers.some((reason) => reason.startsWith("paper_burn_in_incomplete"))) {
    const observedDays = Number(readiness.paper_burn_in_days_observed || 0);
    const requiredDays = Number(readiness.required_burn_in_days || 28);
    return `Keep paper jobs running until ${requiredDays} distinct UTC days are observed. Current count: ${observedDays}.`;
  }
  if (blockers.includes("drawdown_breaker_selftest_missing_or_stale")) {
    return "Run the drawdown self-test from the readiness attestations section.";
  }
  if (blockers.includes("credential_audit_missing_or_stale")) {
    return "Record a current credential audit for the intended live venue.";
  }
  if (blockers.includes("ramp_plan_not_recorded")) {
    return "Record a ramp plan within the configured capital cap.";
  }
  if (blockers.includes("live_trading_disabled_by_config")) {
    return "Leave live trading disabled until the evidence gates are complete, then change config deliberately.";
  }
  return "Review the remaining blocker list and clear the oldest failing evidence item.";
}

function verdictLabel(value) {
  if (value === "review_for_live") {
    return "Review for live";
  }
  if (value === "paper_until_gates_clear") {
    return "Paper only";
  }
  if (value === "paper_profit_pending") {
    return "14-day test running";
  }
  if (value === "paper_not_profitable") {
    return "Not profitable";
  }
  return "Research only";
}

function renderProfitPath(profitPath) {
  if (!profitPath) {
    return;
  }

  const edge = profitPath.edge || {};
  const paper = profitPath.paper_profitability || {};
  const size = profitPath.risk_size_preview || {};
  const gate = profitPath.capital_gate || {};
  const liveBlocked = gate.live_capital_allowed !== true;

  elements.profitPathHeadline.textContent = profitPath.headline || "Profit path unavailable";
  elements.profitPathVerdict.textContent = verdictLabel(profitPath.verdict);
  elements.profitPathVerdict.className =
    profitPath.verdict === "review_for_live"
      ? "positive"
      : profitPath.verdict === "paper_not_profitable"
        ? "negative"
        : "warning-text";
  elements.profitPathCopy.textContent = profitPath.plain_english || "";
  elements.profitPathSteps.innerHTML = [
    {
      label: "1. Find edge",
      value: `${percent(edge.backtest_return_fraction)} backtest return`,
      detail:
        Number(edge.walk_forward_window_count || 0) > 0
          ? `${number(edge.walk_forward_sharpe_ratio, 2)} walk-forward Sharpe across ${Number(edge.walk_forward_window_count)} held-out window${Number(edge.walk_forward_window_count) === 1 ? "" : "s"}`
          : "Need more market history before the edge can be scored out-of-sample",
      passed: edge.leakage_check_passed && edge.walk_forward_sharpe_ratio > 0,
    },
    {
      label: "2. Prove paper profit",
      value: paper.complete ? `${percent(paper.total_return_fraction)} over ${Number(paper.evaluated_days || 0)} days` : `${Number(paper.equity_days_observed || 0)} / ${Number(paper.required_days || 14)} days`,
      detail: paper.complete
        ? `${paper.profitable_days || 0} profitable days, ${paper.losing_days || 0} losing days, max drawdown ${percent(paper.max_drawdown_fraction)}`
        : "Needs 14 distinct UTC days with persisted portfolio equity",
      passed: paper.passed === true,
    },
    {
      label: "3. Size risk",
      value: `${number(size.quantity, 6)} units`,
      detail: `${money(size.risk_dollars)} at risk, capped at ${percent(size.risk_fraction)}`,
      passed: Number(size.quantity || 0) > 0,
    },
    {
      label: "4. Gate capital",
      value: liveBlocked ? "Live blocked" : "Live gate clear",
      detail: liveBlocked
        ? `${gate.paper_burn_in_days_observed || 0} of ${gate.required_burn_in_days || 28} burn-in days observed`
        : "All coded live gates are clear",
      passed: !liveBlocked,
    },
  ]
    .map((step) => `
      <article class="profit-step ${step.passed ? "passed" : "blocked"}">
        <span>${escapeHtml(step.label)}</span>
        <strong>${escapeHtml(step.value)}</strong>
        <p>${escapeHtml(step.detail)}</p>
      </article>
    `)
    .join("");
}

function renderHypeRadar(report) {
  if (!report || !elements.hypeRadarList || !elements.hypeRadarSummary) {
    return;
  }
  if (report.available === false) {
    elements.hypeRadarSummary.innerHTML = '<span class="tag warning">Feed unavailable</span>';
    elements.hypeRadarList.innerHTML = `
      <p class="table-empty">${escapeHtml((report.warnings || []).join(" ") || "Polymarket context is unavailable.")}</p>
    `;
    return;
  }

  const events = report.events || [];
  const topSymbols = report.top_symbols?.length ? report.top_symbols.slice(0, 5).join(", ") : "No mapped symbols";
  elements.hypeRadarSummary.innerHTML = `
    <div class="mini-metrics">
      <div>
        <span>24h volume scanned</span>
        <strong>${money(report.total_volume_24h)}</strong>
      </div>
      <div>
        <span>Mapped narratives</span>
        <strong>${Number(report.mapped_event_count || 0)} / ${Number(report.events_scanned || 0)}</strong>
      </div>
      <div>
        <span>Direct to symbol</span>
        <strong>${Number(report.direct_event_count || 0)}</strong>
      </div>
      <div>
        <span>Top mappings</span>
        <strong>${escapeHtml(topSymbols)}</strong>
      </div>
    </div>
  `;

  if (!events.length) {
    elements.hypeRadarList.innerHTML = '<p class="table-empty">No public hype events mapped yet.</p>';
    return;
  }

  elements.hypeRadarList.innerHTML = events
    .map((event) => {
      const mapped = event.mapped_symbols?.length
        ? event.mapped_symbols.map((symbol) => `<span class="audit-chip">${escapeHtml(symbol)}</span>`).join("")
        : '<span class="audit-chip">unmapped</span>';
      const tags = (event.tags || []).slice(0, 5).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const tone = event.relevance === "direct" ? "positive" : event.relevance === "macro" ? "warning-text" : "";
      return `
        <article class="hype-event">
          <header>
            <div>
              <strong>${escapeHtml(event.title)}</strong>
              <p>${escapeHtml(event.risk_note)}</p>
            </div>
            <a href="${escapeHtml(event.source_url)}" target="_blank" rel="noreferrer">open</a>
          </header>
          <div class="split-list">
            <div>
              <span class="metric-label">24h volume</span>
              <strong>${money(event.volume_24h)}</strong>
            </div>
            <div>
              <span class="metric-label">Liquidity</span>
              <strong>${money(event.liquidity)}</strong>
            </div>
            <div>
              <span class="metric-label">Relevance</span>
              <strong class="${tone}">${escapeHtml(event.relevance)}</strong>
            </div>
          </div>
          <div class="audit-meta">${mapped}</div>
          <div class="tag-row">${tags}</div>
        </article>
      `;
    })
    .join("");
}

function renderPredictionTerminal(report) {
  if (
    !report ||
    !elements.predictionTerminalSummary ||
    !elements.terminalWallets ||
    !elements.terminalRisks ||
    !elements.terminalBooks ||
    !elements.terminalSources
  ) {
    return;
  }

  if (report.available === false) {
    elements.predictionTerminalSummary.innerHTML = '<span class="tag warning">Terminal unavailable</span>';
    elements.terminalWallets.innerHTML = '<p class="table-empty">Wallet feed unavailable.</p>';
    elements.terminalRisks.innerHTML = '<p class="table-empty">Resolution risk unavailable.</p>';
    elements.terminalBooks.innerHTML = '<p class="table-empty">Book and arb feed unavailable.</p>';
    elements.terminalSources.innerHTML = '<p class="table-empty">Source watch unavailable.</p>';
    return;
  }

  const wallets = report.wallets || {};
  const resolution = report.resolution || {};
  const micro = report.microstructure || {};
  const crossVenue = report.cross_venue || {};
  const sources = report.source_monitor || {};
  const whaleTrades = wallets.whale_trades || [];
  const leaders = wallets.leaderboard || [];
  const riskItems = resolution.items || [];
  const bookItems = micro.items || [];
  const arbItems = crossVenue.candidates || [];
  const sourceItems = sources.items || [];

  elements.predictionTerminalSummary.innerHTML = `
    <div class="mini-metrics">
      <div>
        <span>Top-wallet PnL</span>
        <strong>${money(wallets.total_leaderboard_pnl || 0)}</strong>
      </div>
      <div>
        <span>Whale trades</span>
        <strong>${whaleTrades.length}</strong>
      </div>
      <div>
        <span>Rule risk</span>
        <strong>${percent(resolution.highest_ambiguity_score || 0)}</strong>
      </div>
      <div>
        <span>Thin books</span>
        <strong>${Number(micro.thin_book_count || 0)}</strong>
      </div>
      <div>
        <span>Arb matches</span>
        <strong>${arbItems.length}</strong>
      </div>
    </div>
  `;

  const leaderCards = leaders.slice(0, 3).map((leader) => `
    <article class="terminal-card">
      <header>
        <strong>#${Number(leader.rank || 0)} ${escapeHtml(leader.user_name || leader.wallet)}</strong>
        <a href="${escapeHtml(leader.profile_url)}" target="_blank" rel="noreferrer">profile</a>
      </header>
      <p>${money(leader.pnl || 0)} PnL · ${money(leader.volume || 0)} volume</p>
      <div class="audit-meta">
        <span class="audit-chip">${escapeHtml((leader.wallet || "").slice(0, 10))}...</span>
        ${leader.x_username ? `<span class="audit-chip">@${escapeHtml(leader.x_username)}</span>` : ""}
      </div>
    </article>
  `);
  const tradeCards = whaleTrades.slice(0, 3).map((trade) => `
    <article class="terminal-card">
      <header>
        <strong>${escapeHtml(trade.side)} ${escapeHtml(trade.outcome || "outcome")}</strong>
        <a href="${escapeHtml(trade.source_url)}" target="_blank" rel="noreferrer">market</a>
      </header>
      <p>${escapeHtml(trade.title)} · ${money(trade.notional || 0)} notional</p>
      <div class="tag-row">
        <span class="tag">${escapeHtml(trade.signal)}</span>
        <span class="tag">${number(trade.price || 0, 3)}</span>
      </div>
    </article>
  `);
  elements.terminalWallets.innerHTML = [...leaderCards, ...tradeCards].join("") || '<p class="table-empty">No wallet intelligence available.</p>';

  elements.terminalRisks.innerHTML = riskItems
    .slice(0, 4)
    .map((item) => `
      <article class="terminal-card">
        <header>
          <strong>${escapeHtml(item.title)}</strong>
          <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">rules</a>
        </header>
        <p>${escapeHtml(item.description_excerpt || "No rule excerpt available.")}</p>
        <div class="tag-row">
          <span class="tag warning">ambiguity ${percent(item.ambiguity_score || 0)}</span>
          ${(item.risk_flags || []).slice(0, 4).map((flag) => `<span class="tag">${escapeHtml(flag)}</span>`).join("")}
        </div>
      </article>
    `)
    .join("") || '<p class="table-empty">No resolution risks ranked yet.</p>';

  const bookCards = bookItems.slice(0, 3).map((item) => `
    <article class="terminal-card">
      <header>
        <strong>${escapeHtml(item.outcome)} book</strong>
        <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">market</a>
      </header>
      <p>${escapeHtml(item.title)}</p>
      <div class="split-list">
        <div><span class="metric-label">Bid/Ask</span><strong>${number(item.best_bid, 3)} / ${number(item.best_ask, 3)}</strong></div>
        <div><span class="metric-label">Spread</span><strong>${number(item.spread, 3)}</strong></div>
        <div><span class="metric-label">Fill score</span><strong>${percent(item.fill_probability_score || 0)}</strong></div>
      </div>
      <div class="tag-row">${(item.flags || []).map((flag) => `<span class="tag">${escapeHtml(flag)}</span>`).join("")}</div>
    </article>
  `);
  const arbCards = arbItems.slice(0, 3).map((item) => `
    <article class="terminal-card">
      <header>
        <strong>${escapeHtml(item.kalshi_ticker || "cross-venue")}</strong>
        <span class="tag">${item.probability_gap == null ? "rule match" : `${percent(item.probability_gap)} gap`}</span>
      </header>
      <p>${escapeHtml(item.title)} ↔ ${escapeHtml(item.kalshi_title)}</p>
      <div class="audit-meta">${(item.matched_terms || []).slice(0, 5).map((term) => `<span class="audit-chip">${escapeHtml(term)}</span>`).join("")}</div>
    </article>
  `);
  elements.terminalBooks.innerHTML = [...bookCards, ...arbCards].join("") || '<p class="table-empty">No book or cross-venue candidates available.</p>';

  elements.terminalSources.innerHTML = sourceItems
    .slice(0, 4)
    .map((item) => `
      <article class="terminal-card">
        <header>
          <strong>${escapeHtml(item.title)}</strong>
          <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">market</a>
        </header>
        <p>${escapeHtml((item.official_sources || []).slice(0, 3).join(" · ") || "No official source mapped.")}</p>
        <div class="tag-row">
          ${(item.trigger_terms || []).slice(0, 5).map((term) => `<span class="tag">${escapeHtml(term)}</span>`).join("")}
        </div>
      </article>
    `)
    .join("") || '<p class="table-empty">No source watch queries generated.</p>';
}

function renderTerminalHistory(history) {
  if (!elements.terminalDeltaSummary) {
    return;
  }
  const snapshots = history?.snapshots || [];
  const delta = history?.delta || {};
  if (!snapshots.length) {
    elements.terminalDeltaSummary.innerHTML =
      '<p class="table-empty">No saved terminal snapshots yet. Save one to start tracking deltas.</p>';
    return;
  }
  if (delta.available === false) {
    elements.terminalDeltaSummary.innerHTML = `
      <div class="terminal-card">
        <header>
          <strong>${snapshots.length} saved snapshot${snapshots.length === 1 ? "" : "s"}</strong>
          <span class="tag warning">baseline</span>
        </header>
        <p>${escapeHtml(delta.reason || "Need another snapshot to compute movement.")}</p>
      </div>
    `;
    return;
  }
  const summary = delta.summary || {};
  const topWallet = (delta.wallet_deltas || [])[0];
  const topTrade = (delta.new_whale_trades || [])[0];
  elements.terminalDeltaSummary.innerHTML = `
    <div class="mini-metrics">
      <div>
        <span>Wallet moves</span>
        <strong>${Number(summary.wallet_delta_count || 0)}</strong>
      </div>
      <div>
        <span>New whale trades</span>
        <strong>${Number(summary.new_whale_trade_count || 0)}</strong>
      </div>
      <div>
        <span>Rule changes</span>
        <strong>${Number(summary.resolution_risk_change_count || 0)}</strong>
      </div>
      <div>
        <span>Book changes</span>
        <strong>${Number(summary.microstructure_change_count || 0)}</strong>
      </div>
    </div>
    <div class="terminal-columns">
      <article class="terminal-card">
        <header>
          <strong>Top wallet delta</strong>
          <span class="tag">${topWallet ? escapeHtml(topWallet.status) : "none"}</span>
        </header>
        <p>${
          topWallet
            ? `${escapeHtml(topWallet.user_name || topWallet.wallet)} moved ${money(topWallet.pnl_change || 0)} PnL and ${money(topWallet.volume_change || 0)} volume.`
            : "No wallet delta yet."
        }</p>
      </article>
      <article class="terminal-card">
        <header>
          <strong>Latest new flow</strong>
          <span class="tag">${topTrade ? escapeHtml(topTrade.signal || "flow") : "none"}</span>
        </header>
        <p>${
          topTrade
            ? `${escapeHtml(topTrade.side)} ${escapeHtml(topTrade.outcome || "outcome")} on ${escapeHtml(topTrade.title)} for ${money(topTrade.notional || 0)}.`
            : "No new whale trade versus the prior snapshot."
        }</p>
      </article>
    </div>
  `;
}

function renderProfitHunter(report) {
  if (
    !report ||
    !elements.profitHunterAnswer ||
    !elements.profitHunterVerdict ||
    !elements.profitHunterWhy ||
    !elements.profitHunterTicket ||
    !elements.profitHunterCandidates
  ) {
    return;
  }
  state.profitHunter = report;

  const verdict = report.verdict || "INSUFFICIENT_EDGE";
  const trade = report.trade_candidate;
  const ticket = trade?.paper_ticket;
  const verdictCopy =
    verdict === "TRADE"
      ? "Paper trade candidate found"
      : verdict === "NO_TRADE"
        ? "No safe one-hour trade right now"
        : "Not enough edge yet";
  elements.profitHunterAnswer.textContent = verdictCopy;
  elements.profitHunterVerdict.textContent = verdict;
  elements.profitHunterVerdict.className =
    verdict === "TRADE" ? "positive" : verdict === "NO_TRADE" ? "warning-text" : "negative";
  elements.profitHunterWhy.textContent =
    verdict === "TRADE" && trade
      ? `${trade.method.replaceAll("_", " ")} passed the paper gates on ${trade.title}. Review the ticket before acting.`
      : report.no_trade_reason || "The hunter needs stronger market context before it can issue a paper ticket.";
  if (elements.profitHunterStatus) {
    const generatedAt = report.generated_at ? new Date(report.generated_at).toLocaleTimeString() : "now";
    elements.profitHunterStatus.textContent =
      `${Number(report.candidate_count || 0)} candidates scanned at ${generatedAt}. Top score ${number(report.top_score || 0, 2)}.`;
  }

  if (ticket) {
    elements.profitHunterTicket.innerHTML = `
      <article class="hunter-ticket-card">
        <div>
          <span class="metric-label">Paper ticket</span>
          <strong>${escapeHtml(ticket.side)} ${escapeHtml(ticket.outcome || "outcome")}</strong>
          <p>${escapeHtml(ticket.title)}</p>
        </div>
        <div class="split-list">
          <div><span class="metric-label">Entry</span><strong>${number(ticket.entry_price, 4)}</strong></div>
          <div><span class="metric-label">Size</span><strong>${money(ticket.notional_usd)}</strong></div>
          <div><span class="metric-label">Stop</span><strong>${number(ticket.stop_loss_price, 4)}</strong></div>
          <div><span class="metric-label">Target</span><strong>${number(ticket.take_profit_price, 4)}</strong></div>
        </div>
        <p class="metric-subtext">${escapeHtml(ticket.exit_plan)}</p>
      </article>
    `;
  } else {
    elements.profitHunterTicket.innerHTML = `
      <article class="hunter-ticket-card muted-ticket">
        <strong>No paper ticket issued</strong>
        <p>${escapeHtml(report.no_trade_reason || "The current market does not clear the hunter gates.")}</p>
      </article>
    `;
  }

  const candidates = report.candidates || [];
  elements.profitHunterCandidates.innerHTML = candidates.length
    ? candidates
        .slice(0, 4)
        .map((candidate) => {
          const blockers = candidate.blockers?.length
            ? candidate.blockers.slice(0, 3).map((blocker) => `<span class="tag warning">${escapeHtml(blocker)}</span>`).join("")
            : '<span class="tag success">gates clear</span>';
          return `
            <article class="hunter-candidate">
              <header>
                <strong>#${Number(candidate.rank)} ${escapeHtml(candidate.method.replaceAll("_", " "))}</strong>
                <span class="tag">${number(candidate.score, 2)} score</span>
              </header>
              <p>${escapeHtml(candidate.title)}</p>
              <div class="split-list">
                <div><span class="metric-label">Spread</span><strong>${candidate.spread == null ? "-" : number(candidate.spread, 4)}</strong></div>
                <div><span class="metric-label">Fill</span><strong>${percent(candidate.fill_probability_score || 0)}</strong></div>
                <div><span class="metric-label">24h Vol</span><strong>${money(candidate.volume_24h || 0)}</strong></div>
                <div><span class="metric-label">Rule risk</span><strong>${percent(candidate.ambiguity_score || 0)}</strong></div>
              </div>
              <div class="tag-row">${blockers}</div>
            </article>
          `;
        })
        .join("")
    : '<p class="table-empty">No hunter candidates available yet.</p>';
}

function optimizationGridFor(graph) {
  if (graph?.family === "bollinger_mean_reversion") {
    return {
      bollinger_window: [14, 20, 30],
      band_multiplier: [1.5, 2.0, 2.5],
    };
  }
  return {
    fast_window: [10, 15, 20, 25],
    slow_window: [40, 50, 60, 80],
  };
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload?.detail
        ? Array.isArray(payload.detail)
          ? payload.detail.join("; ")
          : payload.detail
        : payload;
    throw new Error(String(detail));
  }
  return payload;
}

function chartSvg(points, color) {
  if (!points.length) {
    return '<div class="table-empty">No data.</div>';
  }
  const width = 900;
  const height = 260;
  const padding = 18;
  const values = points.map((point) => point.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = maxValue - minValue || 1;
  const xStep = points.length === 1 ? 0 : (width - padding * 2) / (points.length - 1);
  const polyline = points
    .map((point, index) => {
      const x = padding + (index * xStep);
      const y = height - padding - (((point.value - minValue) / span) * (height - padding * 2));
      return `${x},${y}`;
    })
    .join(" ");
  const area = `${padding},${height - padding} ${polyline} ${width - padding},${height - padding}`;
  return `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Chart">
      <defs>
        <linearGradient id="area-${color.replace("#", "")}" x1="0%" x2="0%" y1="0%" y2="100%">
          <stop offset="0%" stop-color="${color}" stop-opacity="0.36"></stop>
          <stop offset="100%" stop-color="${color}" stop-opacity="0.02"></stop>
        </linearGradient>
      </defs>
      <path d="M ${area}" fill="url(#area-${color.replace("#", "")})"></path>
      <polyline points="${polyline}" fill="none" stroke="${color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function renderTags(targetId, tags) {
  const root = document.getElementById(targetId);
  root.innerHTML = "";
  if (!tags.length) {
    root.innerHTML = '<span class="tag">No flags</span>';
    return;
  }
  tags.forEach((tag) => {
    const span = document.createElement("span");
    span.className = `tag ${tag.kind || ""}`.trim();
    span.textContent = tag.label;
    root.appendChild(span);
  });
}

function renderPositions(positions) {
  const body = document.getElementById("positions-body");
  const entries = Object.values(positions || {});
  if (!entries.length) {
    body.innerHTML = '<tr><td colspan="5" class="table-empty">No positions yet.</td></tr>';
    return;
  }
  body.innerHTML = entries
    .map((position) => {
      const unrealized = (position.last_price - position.average_entry_price) * position.quantity;
      const tone = unrealized >= 0 ? "positive" : "negative";
      return `
        <tr>
          <td>${escapeHtml(position.symbol)}</td>
          <td>${number(position.quantity, 4)}</td>
          <td>${money(position.average_entry_price)}</td>
          <td>${money(position.last_price)}</td>
          <td class="${tone}">${money(unrealized)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderAlerts(alerts) {
  const root = document.getElementById("alerts-list");
  if (!alerts.length) {
    root.innerHTML = '<p class="table-empty">No alerts yet.</p>';
    return;
  }
  root.innerHTML = alerts
    .map((alert) => {
      const symbolSuffix = alert.details?.symbol ? ` for ${escapeHtml(alert.details.symbol)}` : "";
      return `
        <article class="alert-item">
          <header>
            <strong>${escapeHtml(alert.level)}${symbolSuffix}</strong>
            <time>${escapeHtml(new Date(alert.created_at).toLocaleString())}</time>
          </header>
          <p>${escapeHtml(alert.message)}</p>
        </article>
      `;
    })
    .join("");
}

function renderJobs(jobs) {
  const root = document.getElementById("jobs-list");
  if (!jobs.length) {
    root.innerHTML = '<p class="table-empty">No scheduled jobs yet.</p>';
    return;
  }
  root.innerHTML = jobs
    .map((job) => {
      const stateClass = job.is_active ? "positive" : "negative";
      const actionLabel = job.is_active ? "Pause" : "Start";
      const actionPath = job.is_active ? "pause" : "start";
      const lastStatus = job.last_status ? `<span class="audit-chip">${escapeHtml(job.last_status)}</span>` : "";
      const lastError = job.last_error ? `<p class="negative">${escapeHtml(job.last_error)}</p>` : "";
      return `
        <article class="alert-item">
          <header>
            <strong>${escapeHtml(job.symbol)} - ${escapeHtml(job.timeframe)}</strong>
            <time>every ${Number(job.interval_seconds)}s</time>
          </header>
          <p>
            <span class="${stateClass}">${job.is_active ? "active" : "paused"}</span>
            - lookback ${Number(job.lookback_bars)} bars
          </p>
          <div class="audit-meta">
            ${lastStatus}
          </div>
          ${lastError}
          <div class="job-actions">
            <button class="button subtle small" type="button" data-job-action="${escapeHtml(actionPath)}" data-job-id="${escapeHtml(String(job.id))}">
              ${actionLabel}
            </button>
            <button class="button subtle small" type="button" data-job-action="run" data-job-id="${escapeHtml(String(job.id))}">
              Run Now
            </button>
          </div>
        </article>
      `;
    })
    .join("");

  root.querySelectorAll("[data-job-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      const action = button.dataset.jobAction;
      const jobId = button.dataset.jobId;
      try {
        const path = action === "run" ? `/paper/jobs/${jobId}/run` : `/paper/jobs/${jobId}/${action}`;
        await apiRequest(path, { method: "POST" });
        elements.cycleStatus.textContent = action === "run" ? `Job ${jobId} executed.` : `Job ${jobId} updated.`;
        await refresh();
      } catch (error) {
        elements.cycleStatus.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderRuns(runs) {
  const root = document.getElementById("runs-list");
  if (!runs.length) {
    root.innerHTML = '<p class="table-empty">No runs yet.</p>';
    return;
  }
  root.innerHTML = runs
    .map((run) => {
      const tone = run.status === "completed" ? "positive" : run.status === "failed" ? "negative" : "";
      const jobLabel = run.job_id ? `job ${escapeHtml(String(run.job_id))}` : escapeHtml(String(run.source ?? ""));
      const execution = run.execution_status ? ` - ${escapeHtml(run.execution_status)}` : "";
      const error = run.error_message ? `<p class="negative">${escapeHtml(run.error_message)}</p>` : "";
      const payload = run.cycle_payload
        ? `
            <details class="details-block">
              <summary>Cycle payload</summary>
              <pre class="json-block">${escapeHtml(JSON.stringify(run.cycle_payload, null, 2))}</pre>
            </details>
          `
        : "";
      return `
        <article class="alert-item">
          <header>
            <strong>${escapeHtml(run.symbol)} - ${jobLabel}</strong>
            <time>${escapeHtml(new Date(run.started_at).toLocaleString())}</time>
          </header>
          <p><span class="${tone}">${escapeHtml(run.status)}</span>${execution}</p>
          ${error}
          ${payload}
        </article>
      `;
    })
    .join("");
}

function renderTradeAudit(events) {
  const root = document.getElementById("trade-audit-list");
  if (!events.length) {
    root.innerHTML = '<p class="table-empty">No trade decisions yet.</p>';
    return;
  }
  root.innerHTML = events
    .map((event) => {
      const tone = event.risk_check_passed ? "positive" : "negative";
      return `
        <article class="alert-item">
          <header>
            <strong>${escapeHtml(event.symbol)} - ${escapeHtml(event.signal)}</strong>
            <time>${escapeHtml(new Date(event.created_at).toLocaleString())}</time>
          </header>
          <p>${escapeHtml(event.rationale)}</p>
          <div class="audit-meta">
            <span class="audit-chip ${tone}">${escapeHtml(event.action_taken)}</span>
            <span class="audit-chip">${escapeHtml(event.order_status)}</span>
            <span class="audit-chip">${escapeHtml(event.router)}</span>
            <span class="audit-chip">confidence ${percent(event.confidence)}</span>
            <span class="audit-chip">${escapeHtml(event.risk_reason)}</span>
          </div>
          <details class="details-block">
            <summary>Order + execution report</summary>
            <pre class="json-block">${escapeHtml(
              JSON.stringify(
                {
                  order: event.order_payload,
                  report: event.report_payload,
                  metadata: event.metadata_payload,
                },
                null,
                2,
              ),
            )}</pre>
          </details>
        </article>
      `;
    })
    .join("");
}

function renderCycle(lastCycle) {
  if (!lastCycle) {
    setText("signal-value", "Awaiting cycle");
    setText("signal-subtext", "Run a paper cycle to populate agent output.");
    setText("risk-gate-value", "Standing by");
    setText("risk-gate-subtext", "Orders route through the execution engine only.");
    setText("cycle-confidence", "-");
    setText("analysis-summary", "No cycle has run yet.");
    setText("strategy-rationale", "The dashboard will stay passive until you trigger a paper cycle.");
    setText("consensus-bias-value", "-");
    setText("bull-score", "-");
    setText("bear-score", "-");
    setText("bull-argument", "Waiting for the first cycle.");
    setText("bear-argument", "Waiting for the first cycle.");
    renderTags("cycle-metadata", []);
    return;
  }

  const report = lastCycle.execution_report;
  const strategy = lastCycle.strategy;
  const debate = lastCycle.debate;
  const signalTone = strategy.signal === "BUY" ? "positive" : strategy.signal === "SELL" ? "negative" : "";
  setText("signal-value", strategy.signal, signalTone);
  setText("signal-subtext", `${percent(strategy.confidence)} confidence`);
  setText("cycle-confidence", percent(strategy.confidence));
  setText("analysis-summary", lastCycle.analysis.summary);
  setText("strategy-rationale", strategy.rationale);
  setText("consensus-bias-value", number(debate.consensus_bias, 2), debate.consensus_bias >= 0 ? "positive" : "negative");
  setText("bull-score", percent(debate.bull.score));
  setText("bear-score", percent(debate.bear.score));
  setText("bull-argument", debate.bull.argument);
  setText("bear-argument", debate.bear.argument);
  setText("cycle-status", report ? `${report.status} via ${report.router}` : "No order emitted");
  setText("risk-gate-value", report ? report.status : "No order");
  setText("risk-gate-subtext", report ? report.message : "Trader output stayed below the execution threshold.");

  const metadataTags = Object.entries(lastCycle.metadata || {}).map(([key, value]) => ({
    label: `${key.replaceAll("_", " ")}: ${String(value)}`,
    kind: value === true ? "success" : value === false ? "danger" : "",
  }));
  renderTags("cycle-metadata", metadataTags);
}

function renderWalkForwardWindows(researchView) {
  const root = document.getElementById("walk-forward-list");
  const windows = researchView.walk_forward_windows || [];
  if (!windows.length) {
    root.innerHTML = '<p class="table-empty">No walk-forward windows available.</p>';
    return;
  }
  root.innerHTML = windows
    .map((window, index) => `
      <article class="alert-item">
        <header>
          <strong>Window ${index + 1}</strong>
          <time>${escapeHtml(new Date(window.test_start).toLocaleDateString())} to ${escapeHtml(new Date(window.test_end).toLocaleDateString())}</time>
        </header>
        <div class="audit-meta">
          <span class="audit-chip">return ${percent(window.total_return_fraction)}</span>
          <span class="audit-chip">sharpe ${number(window.sharpe_ratio, 2)}</span>
          <span class="audit-chip negative">drawdown ${percent(window.max_drawdown_fraction)}</span>
        </div>
        <p>Train ${escapeHtml(new Date(window.train_start).toLocaleDateString())} to ${escapeHtml(new Date(window.train_end).toLocaleDateString())}</p>
        ${window.warnings?.length ? `<p>${escapeHtml(window.warnings.join(" | "))}</p>` : ""}
      </article>
    `)
    .join("");
}

function renderResearchTrades(researchView) {
  const root = document.getElementById("research-trades-list");
  const trades = researchView.trades || [];
  if (!trades.length) {
    root.innerHTML = '<p class="table-empty">No research trades available.</p>';
    return;
  }
  root.innerHTML = trades
    .map((trade) => {
      const tone = trade.pnl_fraction >= 0 ? "positive" : "negative";
      return `
        <article class="alert-item">
          <header>
            <strong>${escapeHtml(trade.side)}</strong>
            <time>${escapeHtml(new Date(trade.entry_time).toLocaleDateString())} to ${escapeHtml(new Date(trade.exit_time).toLocaleDateString())}</time>
          </header>
          <div class="audit-meta">
            <span class="audit-chip">entry ${money(trade.entry_price)}</span>
            <span class="audit-chip">exit ${money(trade.exit_price)}</span>
            <span class="audit-chip ${tone}">pnl ${percent(trade.pnl_fraction)}</span>
            <span class="audit-chip">bars ${Number(trade.bars_held)}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderPortfolioBreakdown(items) {
  const root = document.getElementById("portfolio-breakdown-list");
  if (!items.length) {
    root.innerHTML = '<p class="table-empty">No allocation yet.</p>';
    return;
  }
  root.innerHTML = items
    .map((item) => `
      <article class="alert-item">
        <header>
          <strong>${escapeHtml(item.symbol)}</strong>
          <time>${percent(item.weight_fraction)} weight</time>
        </header>
        <div class="audit-meta">
          <span class="audit-chip">value ${money(item.market_value)}</span>
          <span class="audit-chip ${item.unrealized_pnl >= 0 ? "positive" : "negative"}">
            unrealized ${money(item.unrealized_pnl)}
          </span>
          <span class="audit-chip ${item.realized_pnl >= 0 ? "positive" : "negative"}">
            realized ${money(item.realized_pnl)}
          </span>
        </div>
      </article>
    `)
    .join("");
}

function renderVenues(catalog) {
  const root = document.getElementById("venues-list");
  const venues = catalog?.venues || [];
  if (!venues.length) {
    root.innerHTML = '<p class="table-empty">No venue metadata available.</p>';
    return;
  }
  root.innerHTML = venues
    .map((venue) => `
      <article class="alert-item">
        <header>
          <strong>${escapeHtml(venue.venue_id)}</strong>
          <time>${venue.configured ? "configured" : "available"}</time>
        </header>
        <div class="audit-meta">
          <span class="audit-chip">${escapeHtml(venue.venue_kind)}</span>
          <span class="audit-chip">${escapeHtml(venue.transport)}</span>
          <span class="audit-chip">${escapeHtml(venue.symbol_format)}</span>
          ${venue.supports_sandbox ? '<span class="audit-chip">sandbox</span>' : ""}
          ${venue.venue_supported_order_types?.length ? `<span class="audit-chip">venue orders ${escapeHtml(venue.venue_supported_order_types.join(", "))}</span>` : ""}
          ${venue.engine_supported_order_types?.length ? `<span class="audit-chip">engine orders ${escapeHtml(venue.engine_supported_order_types.join(", "))}</span>` : ""}
        </div>
        <p>${escapeHtml((venue.notes || []).join(" "))}</p>
      </article>
    `)
    .join("");
}

function renderReadiness(readiness) {
  if (!readiness) {
    return;
  }

  const observedDays = Number(readiness.paper_burn_in_days_observed || 0);
  const requiredDays = Number(readiness.required_burn_in_days || 28);
  const progress = Math.min(100, (observedDays / Math.max(requiredDays, 1)) * 100);
  const allowed = readiness.live_capital_allowed === true;
  const blockers = readiness.blocking_reasons || [];
  const credentialPayload = readiness.credential_audit?.payload || {};
  const selftestPayload = readiness.drawdown_breaker_selftest?.payload || {};
  const rampPayload = readiness.ramp_plan?.payload || {};

  elements.liveReadinessStatus.textContent = allowed ? "Allowed" : "Blocked";
  elements.liveReadinessStatus.className = allowed ? "positive" : "negative";
  elements.liveReadinessVerdict.textContent = allowed ? "Live Capital Allowed" : "Live Gate Blocked";
  elements.liveReadinessVerdict.className = allowed ? "positive" : "negative";
  elements.liveReadinessSubtext.textContent = allowed ? "0 blockers" : `${blockers.length} blocker${blockers.length === 1 ? "" : "s"}`;
  elements.clientBriefAnswer.textContent = allowed ? "Ready for live capital" : "Not ready for live capital";
  elements.clientBriefAnswer.className = allowed ? "positive" : "negative";
  elements.clientBriefWhy.textContent = allowed
    ? "All coded gates are satisfied. Final approval still belongs to the operator."
    : `${blockers.length} issue${blockers.length === 1 ? "" : "s"} block the launch decision: ${blockers
        .slice(0, 2)
        .map((reason) => describeBlocker(reason, readiness))
        .join("; ")}${blockers.length > 2 ? "." : "."}`;
  elements.clientNextAction.textContent = nextActionFor(readiness, blockers);
  elements.burnInProgressLabel.textContent = `${observedDays} / ${requiredDays}`;
  elements.burnInProgress.style.width = `${progress}%`;

  const proofItems = [
    {
      label: "Paper evidence",
      value: `${observedDays} of ${requiredDays} days`,
      passed: readiness.twenty_eight_day_gate_passed,
    },
    {
      label: "Credential review",
      value: readiness.credential_audit_fresh ? "current" : "missing or stale",
      passed: readiness.credential_audit_fresh,
    },
    {
      label: "Drawdown halt",
      value: readiness.drawdown_breaker_selftest_passed ? "tested" : "not proven",
      passed: readiness.drawdown_breaker_selftest_fresh && readiness.drawdown_breaker_selftest_passed,
    },
    {
      label: "Ramp cap",
      value: readiness.ramp_plan_within_cap ? "within limit" : "not accepted",
      passed: readiness.ramp_plan_recorded && readiness.ramp_plan_within_cap,
    },
  ];

  elements.clientProofList.innerHTML = proofItems
    .map((item) => `
      <div class="proof-item ${item.passed ? "passed" : "blocked"}">
        <span>${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
      </div>
    `)
    .join("");

  const gates = [
    {
      label: "28-day burn-in",
      passed: readiness.twenty_eight_day_gate_passed,
      detail: `${observedDays} distinct UTC day${observedDays === 1 ? "" : "s"}`,
    },
    {
      label: "Credential audit",
      passed: readiness.credential_audit_fresh,
      detail: readiness.credential_audit
        ? `${credentialPayload.venue || "venue"} - ${labelFromKey(credentialPayload.scope || "scope")}`
        : "not recorded",
    },
    {
      label: "Drawdown self-test",
      passed: readiness.drawdown_breaker_selftest_fresh && readiness.drawdown_breaker_selftest_passed,
      detail: readiness.drawdown_breaker_selftest
        ? selftestPayload.reason || "recorded"
        : "not recorded",
    },
    {
      label: "Ramp plan",
      passed: readiness.ramp_plan_recorded && readiness.ramp_plan_within_cap,
      detail: readiness.ramp_plan
        ? `${rampPayload.target_venue || "venue"} at ${percent(rampPayload.capital_cap_fraction)}`
        : "not recorded",
    },
    {
      label: "Live trading config",
      passed: readiness.live_trading_enabled,
      detail: readiness.live_trading_enabled ? "enabled" : "disabled",
    },
  ];

  elements.readinessGatesList.innerHTML = gates
    .map((gate) => `
      <article class="gate-item ${gate.passed ? "passed" : "blocked"}">
        <span class="gate-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(gate.label)}</strong>
          <p>${escapeHtml(gate.detail)}</p>
        </div>
      </article>
    `)
    .join("");

  if (!blockers.length) {
    elements.readinessBlockersList.innerHTML = '<span class="tag success">No blockers</span>';
    return;
  }

  elements.readinessBlockersList.innerHTML = blockers
    .map((reason) => `<span class="tag danger">${escapeHtml(describeBlocker(reason, readiness))}</span>`)
    .join("");
}

function renderStrategyGraph(draft, strategyBuilder) {
  const root = document.getElementById("strategy-graph");
  if (!draft?.graph) {
    root.innerHTML = `
      <p class="table-empty">Build a strategy to inspect its graph, rules, and risk policy.</p>
      <p class="metric-subtext">${strategyBuilder?.sample_prompt || ""}</p>
    `;
    return;
  }
  const graph = draft.graph;
  const issues = draft.validation.issues || [];
  const warnings = draft.validation.warnings || [];
  root.innerHTML = `
    <section class="definition-group">
      <h3>${escapeHtml(graph.name)}</h3>
      <p class="metric-subtext">${escapeHtml(graph.source_prompt || "")}</p>
      <div class="tag-row">
        <span class="tag ${draft.validation.passed ? "success" : "danger"}">${draft.validation.passed ? "valid" : "blocked"}</span>
        ${draft.compiled_strategy_name ? `<span class="tag success">${escapeHtml(draft.compiled_strategy_name)}</span>` : ""}
      </div>
    </section>
    <section class="definition-group">
      <h3>Indicators</h3>
      <div class="split-list">
        ${graph.indicators
          .map((indicator) => `
            <div>
              <strong>${escapeHtml(indicator.node_id)}</strong>
              <p>${escapeHtml(String(indicator.kind).toUpperCase())} ${Number(indicator.window)}${indicator.multiplier ? ` x${Number(indicator.multiplier).toFixed(2)}` : ""}</p>
            </div>
          `)
          .join("")}
      </div>
    </section>
    <section class="definition-group">
      <h3>Rules</h3>
      <div class="split-list">
        ${graph.rules
          .map((rule) => `
            <div>
              <strong>${escapeHtml(rule.stage)}</strong>
              <p>${escapeHtml(rule.description)}</p>
            </div>
          `)
          .join("")}
      </div>
    </section>
    <section class="definition-group">
      <h3>Risk</h3>
      <p>Long only: ${graph.risk.long_only ? "yes" : "no"}.</p>
      <p>Stop loss: ${graph.risk.stop_loss_percent ? percent(graph.risk.stop_loss_percent) : "missing"}.</p>
    </section>
    ${issues.length ? `<section class="definition-group"><h3>Issues</h3><p class="negative">${escapeHtml(issues.join(" "))}</p></section>` : ""}
    ${warnings.length ? `<section class="definition-group"><h3>Warnings</h3><p>${escapeHtml(warnings.join(" "))}</p></section>` : ""}
  `;
}

function renderBacktest(researchView) {
  setText("research-title", state.strategyBacktest ? "Compiled Strategy Research" : "EMA Backtest");
  setText(
    "backtest-return-value",
    percent(researchView.metrics.total_return_fraction),
    researchView.metrics.total_return_fraction >= 0 ? "positive" : "negative",
  );
  setText("walk-forward-sharpe-value", number(researchView.walk_forward_summary.average_sharpe_ratio, 2));
  setText("max-drawdown-value", percent(researchView.metrics.max_drawdown_fraction), "negative");

  const equitySeries = researchView.equity_curve.map((point) => ({ value: point.equity }));
  document.getElementById("equity-chart").innerHTML = chartSvg(equitySeries, "#f5b667");

  const warningTags = [];
  if (researchView.leakage_check?.passed) {
    warningTags.push({ label: "Leakage check passed", kind: "success" });
  }
  (researchView.metrics.warnings || []).forEach((warning) => warningTags.push({ label: warning, kind: "warning" }));
  (researchView.walk_forward_summary.warnings || []).forEach((warning) => warningTags.push({ label: warning, kind: "warning" }));
  renderTags("backtest-warning-list", warningTags);
  renderWalkForwardWindows(researchView);
  renderResearchTrades(researchView);
}

function renderOverview(overview) {
  state.overview = overview;
  const {
    config,
    market,
    features,
    portfolio,
    portfolio_breakdown: portfolioBreakdown,
    alerts,
    jobs,
    runs,
    trade_audit: tradeAudit,
    venues,
    market_context: marketContext,
    live_readiness: liveReadiness,
    strategy_builder: strategyBuilder,
    backtest,
    last_cycle: lastCycle,
  } = overview;

  setText("mode-pill", config.mode);
  setText("provider-pill", config.provider);
  setText("live-pill", config.live_trading_enabled ? "enabled" : "disabled");
  setText("market-title", `${market.symbol} - ${market.timeframe}`);
  setText("latest-price", money(market.latest_price));
  setText("latest-timestamp", new Date(market.latest_timestamp).toLocaleString());

  const staleSuffix = portfolio.stale_symbols?.length ? ` - stale ${portfolio.stale_symbols.join(", ")}` : "";
  setText("equity-value", money(portfolio.equity));
  setText(
    "equity-subtext",
    `${money(portfolio.cash)} cash - ${Object.keys(portfolio.positions || {}).length} open positions${staleSuffix}`,
  );

  const dailyClass = portfolio.daily_pnl_fraction >= 0 ? "positive" : "negative";
  setText("daily-pnl-value", percent(portfolio.daily_pnl_fraction), dailyClass);
  setText("ema20-value", money(features.ema_20));
  setText("ema50-value", money(features.ema_50));
  setText("ema200-value", money(features.ema_200));
  setText("rsi-value", number(features.rsi_14, 1));

  const priceSeries = market.recent_bars.map((bar) => ({ value: bar.close }));
  document.getElementById("price-chart").innerHTML = chartSvg(priceSeries, "#73d5b2");

  const researchView = state.strategyBacktest || backtest;
  renderBacktest(researchView);
  renderPositions(portfolio.positions);
  renderPortfolioBreakdown(portfolioBreakdown || []);
  renderProfitPath(overview.profit_path);
  renderProfitHunter(marketContext?.profit_hunter);
  renderHypeRadar(marketContext?.polymarket_hype);
  renderPredictionTerminal(marketContext?.prediction_terminal);
  renderTerminalHistory(marketContext?.prediction_terminal_history);
  renderAlerts(alerts || []);
  renderJobs(jobs || []);
  renderRuns(runs || []);
  renderTradeAudit(tradeAudit || []);
  renderCycle(lastCycle);
  renderVenues(venues);
  renderReadiness(liveReadiness);
  renderStrategyGraph(state.strategyDraft, strategyBuilder);
}

async function fetchOverview() {
  const params = new URLSearchParams({
    symbol: state.symbol,
    timeframe: state.timeframe,
  });
  elements.refreshStatus.textContent = "Refreshing";
  const overview = await apiRequest(`/dashboard/data?${params.toString()}`);
  state.symbol = overview.market.symbol;
  state.timeframe = overview.market.timeframe;
  elements.symbolInput.value = state.symbol;
  elements.timeframeSelect.value = state.timeframe;
  renderOverview(overview);
  elements.refreshStatus.textContent = "Fresh";
}

async function runPaperCycle() {
  elements.paperCycleButton.disabled = true;
  elements.cycleStatus.textContent = "Running cycle";
  try {
    const params = new URLSearchParams({
      timeframe: state.timeframe,
      lookback_bars: "600",
    });
    const result = await apiRequest(`/paper/cycles/${encodeURIComponent(state.symbol)}?${params.toString()}`, {
      method: "POST",
    });
    renderCycle(result);
    await fetchOverview();
  } finally {
    elements.paperCycleButton.disabled = false;
  }
}

async function createJob(event) {
  event.preventDefault();
  elements.jobSubmitButton.disabled = true;
  try {
    await apiRequest("/paper/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: elements.jobSymbolInput.value.trim().toUpperCase(),
        timeframe: elements.jobTimeframeSelect.value,
        lookback_bars: Number(elements.jobLookbackInput.value),
        interval_seconds: Number(elements.jobIntervalInput.value),
        auto_start: elements.jobAutoStartInput.checked,
      }),
    });
    elements.cycleStatus.textContent = "Paper job created.";
    await refresh();
  } catch (error) {
    elements.cycleStatus.textContent = error.message;
  } finally {
    elements.jobSubmitButton.disabled = false;
  }
}

async function submitManualOrder(event) {
  event.preventDefault();
  elements.manualOrderButton.disabled = true;
  try {
    const takeProfit = elements.manualTakeProfitInput.value.trim();
    const result = await apiRequest("/paper/orders/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: elements.manualSymbolInput.value.trim().toUpperCase(),
        timeframe: elements.manualTimeframeSelect.value,
        side: elements.manualSideSelect.value,
        quantity: Number(elements.manualQuantityInput.value),
        stop_loss_price: Number(elements.manualStopLossInput.value),
        take_profit_price: takeProfit ? Number(takeProfit) : null,
      }),
    });
    elements.cycleStatus.textContent = `${result.report.status} manual order for ${result.order.symbol}.`;
    await refresh();
  } catch (error) {
    elements.cycleStatus.textContent = error.message;
  } finally {
    elements.manualOrderButton.disabled = false;
  }
}

async function runDrawdownSelftest() {
  elements.drawdownSelftestButton.disabled = true;
  elements.readinessActionStatus.textContent = "Running drawdown self-test.";
  try {
    const result = await apiRequest("/readiness/drawdown-breaker/selftest", { method: "POST" });
    renderReadiness(result.summary);
    elements.readinessActionStatus.textContent = result.result.passed
      ? "Drawdown self-test passed."
      : "Drawdown self-test failed.";
    await fetchOverview();
  } catch (error) {
    elements.readinessActionStatus.textContent = error.message;
  } finally {
    elements.drawdownSelftestButton.disabled = false;
  }
}

async function recordCredentialAudit(event) {
  event.preventDefault();
  elements.credentialAuditButton.disabled = true;
  elements.readinessActionStatus.textContent = "Recording credential audit.";
  try {
    const result = await apiRequest("/readiness/credential-audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        venue: elements.credentialVenueInput.value.trim(),
        scope: elements.credentialScopeSelect.value,
        auditor: elements.credentialAuditorInput.value.trim(),
        notes: elements.credentialNotesInput.value.trim(),
      }),
    });
    renderReadiness(result.summary);
    elements.readinessActionStatus.textContent = "Credential audit recorded.";
    await fetchOverview();
  } catch (error) {
    elements.readinessActionStatus.textContent = error.message;
  } finally {
    elements.credentialAuditButton.disabled = false;
  }
}

async function recordRampPlan(event) {
  event.preventDefault();
  elements.rampPlanButton.disabled = true;
  elements.readinessActionStatus.textContent = "Recording ramp plan.";
  try {
    const result = await apiRequest("/readiness/ramp-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_venue: elements.rampVenueInput.value.trim(),
        capital_cap_fraction: Number(elements.rampCapInput.value),
        notes: elements.rampNotesInput.value.trim(),
      }),
    });
    renderReadiness(result.summary);
    elements.readinessActionStatus.textContent = "Ramp plan recorded.";
    await fetchOverview();
  } catch (error) {
    elements.readinessActionStatus.textContent = error.message;
  } finally {
    elements.rampPlanButton.disabled = false;
  }
}

async function buildStrategy(event) {
  if (event) {
    event.preventDefault();
  }
  elements.strategyDraftButton.disabled = true;
  try {
    const draft = await apiRequest("/strategies/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: elements.strategyPromptInput.value.trim(),
      }),
    });
    state.strategyDraft = draft;
    state.strategyBacktest = null;
    elements.strategyStatus.textContent = draft.validation.passed
      ? "Graph compiled successfully. Validate or run research next."
      : draft.validation.issues.join(" ");
    renderStrategyGraph(draft, state.overview?.strategy_builder);
    if (state.overview) {
      renderBacktest(state.overview.backtest);
      setText("research-title", "EMA Backtest");
    }
  } catch (error) {
    elements.strategyStatus.textContent = error.message;
  } finally {
    elements.strategyDraftButton.disabled = false;
  }
}

async function validateStrategy() {
  if (!state.strategyDraft?.graph) {
    elements.strategyStatus.textContent = "Build a strategy graph before validation.";
    return;
  }
  elements.strategyValidateButton.disabled = true;
  try {
    const validation = await apiRequest("/strategies/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ graph: state.strategyDraft.graph }),
    });
    state.strategyDraft.validation = validation;
    elements.strategyStatus.textContent = validation.passed
      ? "Validation passed. Research run is available."
      : validation.issues.join(" ");
    renderStrategyGraph(state.strategyDraft, state.overview?.strategy_builder);
  } catch (error) {
    elements.strategyStatus.textContent = error.message;
  } finally {
    elements.strategyValidateButton.disabled = false;
  }
}

async function backtestStrategy() {
  if (!state.strategyDraft?.graph) {
    elements.strategyStatus.textContent = "Build a strategy graph before running research.";
    return;
  }
  elements.strategyBacktestButton.disabled = true;
  try {
    const result = await apiRequest("/strategies/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: state.symbol,
        timeframe: state.timeframe,
        lookback_bars: 700,
        graph: state.strategyDraft.graph,
      }),
    });
    state.strategyBacktest = {
      leakage_check: result.leakage_check,
      metrics: result.backtest.metrics,
      equity_curve: result.backtest.equity_curve,
      walk_forward_summary: result.walk_forward.summary,
      walk_forward_windows: result.walk_forward.windows.map((window) => ({
        train_start: window.train_start,
        train_end: window.train_end,
        test_start: window.test_start,
        test_end: window.test_end,
        total_return_fraction: window.result.metrics.total_return_fraction,
        sharpe_ratio: window.result.metrics.sharpe_ratio,
        max_drawdown_fraction: window.result.metrics.max_drawdown_fraction,
        warnings: window.result.metrics.warnings,
      })),
      trades: result.backtest.trades,
    };
    elements.strategyStatus.textContent = "Compiled strategy backtest complete.";
    renderBacktest(state.strategyBacktest);
  } catch (error) {
    elements.strategyStatus.textContent = error.message;
  } finally {
    elements.strategyBacktestButton.disabled = false;
  }
}

async function runEdgeScan() {
  elements.edgeScanButton.disabled = true;
  elements.edgeScanStatus.textContent = "Building strategy graph.";
  elements.edgeScanSummary.innerHTML = '<p class="table-empty">Scanning parameter grid on held-out windows.</p>';
  try {
    if (state.overview?.backtest?.walk_forward_summary?.window_count === 0) {
      elements.edgeScanStatus.textContent = "More history needed.";
      elements.edgeScanSummary.innerHTML = `
        <p class="metric-subtext">
          Edge Scan needs enough bars to split data into train and held-out test windows.
          Try a higher timeframe or a data provider with deeper history before optimizing.
        </p>
      `;
      return;
    }

    let draft = state.strategyDraft;
    if (!draft?.graph) {
      draft = await apiRequest("/strategies/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: elements.strategyPromptInput.value.trim(),
        }),
      });
      state.strategyDraft = draft;
      renderStrategyGraph(draft, state.overview?.strategy_builder);
    }
    if (!draft.validation?.passed) {
      elements.edgeScanStatus.textContent = "Graph blocked.";
      elements.edgeScanSummary.innerHTML = `<p class="negative">${escapeHtml((draft.validation?.issues || []).join(" "))}</p>`;
      return;
    }

    elements.edgeScanStatus.textContent = "Optimizing parameters.";
    const result = await apiRequest("/strategies/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: state.symbol,
        timeframe: state.timeframe,
        lookback_bars: 900,
        base_graph: draft.graph,
        parameter_grid: optimizationGridFor(draft.graph),
        selection_metric: "sharpe_ratio",
        max_combinations: 18,
      }),
    });
    const summary = result.optimization.summary;
    const best = result.optimization.leaderboard?.[0];
    const warnings = summary.warnings || [];
    elements.edgeScanStatus.textContent = "Edge scan complete.";
    elements.edgeScanSummary.innerHTML = `
      <div class="split-list">
        <div>
          <span class="metric-label">Held-out return</span>
          <strong class="${summary.out_of_sample_compounded_return_fraction >= 0 ? "positive" : "negative"}">
            ${percent(summary.out_of_sample_compounded_return_fraction)}
          </strong>
        </div>
        <div>
          <span class="metric-label">Held-out Sharpe</span>
          <strong>${number(summary.out_of_sample_average_sharpe_ratio, 2)}</strong>
        </div>
        <div>
          <span class="metric-label">Worst drawdown</span>
          <strong class="negative">${percent(summary.out_of_sample_worst_drawdown_fraction)}</strong>
        </div>
        <div>
          <span class="metric-label">Combinations tested</span>
          <strong>${Number(summary.parameter_combinations_evaluated)}</strong>
        </div>
      </div>
      ${
        best
          ? `<p class="metric-subtext">Best in-sample candidate: ${escapeHtml(JSON.stringify(best.parameters))}</p>`
          : ""
      }
      ${
        warnings.length
          ? `<div class="tag-row">${warnings.map((warning) => `<span class="tag warning">${escapeHtml(warning)}</span>`).join("")}</div>`
          : '<div class="tag-row"><span class="tag success">No optimizer warnings</span></div>'
      }
    `;
  } catch (error) {
    elements.edgeScanStatus.textContent = "Edge scan failed.";
    elements.edgeScanSummary.innerHTML = `<p class="negative">${escapeHtml(error.message)}</p>`;
  } finally {
    elements.edgeScanButton.disabled = false;
  }
}

async function saveTerminalSnapshot() {
  elements.terminalSnapshotButton.disabled = true;
  elements.terminalSnapshotStatus.textContent = "Saving terminal snapshot.";
  try {
    const params = new URLSearchParams({
      symbol: state.symbol,
      limit: "8",
    });
    const result = await apiRequest(`/market-context/polymarket/terminal/snapshots?${params.toString()}`, {
      method: "POST",
    });
    elements.terminalSnapshotStatus.textContent = `Saved snapshot #${result.snapshot.id}.`;
    renderTerminalHistory({
      snapshots: [result.snapshot],
      delta: result.delta,
    });
    await fetchOverview();
  } catch (error) {
    elements.terminalSnapshotStatus.textContent = error.message;
  } finally {
    elements.terminalSnapshotButton.disabled = false;
  }
}

async function runProfitHunter() {
  elements.profitHunterButton.disabled = true;
  elements.profitHunterStatus.textContent = "Scanning one-hour opportunity set.";
  try {
    const params = new URLSearchParams({
      symbol: state.symbol,
      horizon_minutes: "60",
      max_stake_usd: "25",
      min_trade_score: "0.72",
      limit: "8",
      record_snapshot: "true",
    });
    const result = await apiRequest(`/market-context/polymarket/hunter/run?${params.toString()}`, {
      method: "POST",
    });
    renderProfitHunter(result.report);
    if (result.snapshot) {
      elements.terminalSnapshotStatus.textContent = `Hunter saved snapshot #${result.snapshot.id}.`;
    }
    await fetchOverview();
  } catch (error) {
    elements.profitHunterStatus.textContent = error.message;
  } finally {
    elements.profitHunterButton.disabled = false;
  }
}

async function refresh() {
  state.symbol = elements.symbolInput.value.trim().toUpperCase() || "BTC-USD";
  state.timeframe = elements.timeframeSelect.value;
  try {
    await fetchOverview();
  } catch (error) {
    elements.refreshStatus.textContent = "Error";
    elements.cycleStatus.textContent = error.message;
  }
}

elements.refreshButton.addEventListener("click", refresh);
elements.paperCycleButton.addEventListener("click", async () => {
  try {
    await runPaperCycle();
  } catch (error) {
    elements.cycleStatus.textContent = error.message;
  }
});
elements.jobForm.addEventListener("submit", createJob);
elements.manualOrderForm.addEventListener("submit", submitManualOrder);
elements.drawdownSelftestButton.addEventListener("click", runDrawdownSelftest);
elements.credentialAuditForm.addEventListener("submit", recordCredentialAudit);
elements.rampPlanForm.addEventListener("submit", recordRampPlan);
elements.strategyForm.addEventListener("submit", buildStrategy);
elements.strategyValidateButton.addEventListener("click", validateStrategy);
elements.strategyBacktestButton.addEventListener("click", backtestStrategy);
elements.edgeScanButton.addEventListener("click", runEdgeScan);
elements.terminalSnapshotButton.addEventListener("click", saveTerminalSnapshot);
elements.profitHunterButton.addEventListener("click", runProfitHunter);

window.addEventListener("load", () => {
  elements.jobSymbolInput.value = state.symbol;
  elements.manualSymbolInput.value = state.symbol;
  refresh();
  window.setInterval(refresh, 15000);
});
