const state = {
  symbol: "BTC-USD",
  timeframe: "1h",
  overview: null,
  strategyDraft: null,
  strategyBacktest: null,
};

const elements = {
  symbolInput: document.getElementById("symbol-input"),
  timeframeSelect: document.getElementById("timeframe-select"),
  refreshButton: document.getElementById("refresh-button"),
  paperCycleButton: document.getElementById("paper-cycle-button"),
  refreshStatus: document.getElementById("refresh-status"),
  cycleStatus: document.getElementById("cycle-status"),
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
          <td>${position.symbol}</td>
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
      const symbol = alert.details?.symbol ? ` for ${alert.details.symbol}` : "";
      return `
        <article class="alert-item">
          <header>
            <strong>${alert.level}${symbol}</strong>
            <time>${new Date(alert.created_at).toLocaleString()}</time>
          </header>
          <p>${alert.message}</p>
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
      const lastStatus = job.last_status ? `<span class="audit-chip">${job.last_status}</span>` : "";
      const lastError = job.last_error ? `<p class="negative">${job.last_error}</p>` : "";
      return `
        <article class="alert-item">
          <header>
            <strong>${job.symbol} - ${job.timeframe}</strong>
            <time>every ${job.interval_seconds}s</time>
          </header>
          <p>
            <span class="${stateClass}">${job.is_active ? "active" : "paused"}</span>
            - lookback ${job.lookback_bars} bars
          </p>
          <div class="audit-meta">
            ${lastStatus}
          </div>
          ${lastError}
          <div class="job-actions">
            <button class="button subtle small" type="button" data-job-action="${actionPath}" data-job-id="${job.id}">
              ${actionLabel}
            </button>
            <button class="button subtle small" type="button" data-job-action="run" data-job-id="${job.id}">
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
      const jobLabel = run.job_id ? `job ${run.job_id}` : run.source;
      const execution = run.execution_status ? ` - ${run.execution_status}` : "";
      const error = run.error_message ? `<p class="negative">${run.error_message}</p>` : "";
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
            <strong>${run.symbol} - ${jobLabel}</strong>
            <time>${new Date(run.started_at).toLocaleString()}</time>
          </header>
          <p><span class="${tone}">${run.status}</span>${execution}</p>
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
            <strong>${event.symbol} - ${event.signal}</strong>
            <time>${new Date(event.created_at).toLocaleString()}</time>
          </header>
          <p>${event.rationale}</p>
          <div class="audit-meta">
            <span class="audit-chip ${tone}">${event.action_taken}</span>
            <span class="audit-chip">${event.order_status}</span>
            <span class="audit-chip">${event.router}</span>
            <span class="audit-chip">confidence ${percent(event.confidence)}</span>
            <span class="audit-chip">${event.risk_reason}</span>
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
          <time>${new Date(window.test_start).toLocaleDateString()} to ${new Date(window.test_end).toLocaleDateString()}</time>
        </header>
        <div class="audit-meta">
          <span class="audit-chip">return ${percent(window.total_return_fraction)}</span>
          <span class="audit-chip">sharpe ${number(window.sharpe_ratio, 2)}</span>
          <span class="audit-chip negative">drawdown ${percent(window.max_drawdown_fraction)}</span>
        </div>
        <p>Train ${new Date(window.train_start).toLocaleDateString()} to ${new Date(window.train_end).toLocaleDateString()}</p>
        ${window.warnings?.length ? `<p>${window.warnings.join(" | ")}</p>` : ""}
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
            <strong>${trade.side}</strong>
            <time>${new Date(trade.entry_time).toLocaleDateString()} to ${new Date(trade.exit_time).toLocaleDateString()}</time>
          </header>
          <div class="audit-meta">
            <span class="audit-chip">entry ${money(trade.entry_price)}</span>
            <span class="audit-chip">exit ${money(trade.exit_price)}</span>
            <span class="audit-chip ${tone}">pnl ${percent(trade.pnl_fraction)}</span>
            <span class="audit-chip">bars ${trade.bars_held}</span>
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
          <strong>${item.symbol}</strong>
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
          <strong>${venue.venue_id}</strong>
          <time>${venue.configured ? "configured" : "available"}</time>
        </header>
        <div class="audit-meta">
          <span class="audit-chip">${venue.venue_kind}</span>
          <span class="audit-chip">${venue.transport}</span>
          <span class="audit-chip">${venue.symbol_format}</span>
          ${venue.supports_sandbox ? '<span class="audit-chip">sandbox</span>' : ""}
          ${venue.venue_supported_order_types?.length ? `<span class="audit-chip">venue orders ${venue.venue_supported_order_types.join(", ")}</span>` : ""}
          ${venue.engine_supported_order_types?.length ? `<span class="audit-chip">engine orders ${venue.engine_supported_order_types.join(", ")}</span>` : ""}
        </div>
        <p>${venue.notes.join(" ")}</p>
      </article>
    `)
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
      <h3>${graph.name}</h3>
      <p class="metric-subtext">${graph.source_prompt || ""}</p>
      <div class="tag-row">
        <span class="tag ${draft.validation.passed ? "success" : "danger"}">${draft.validation.passed ? "valid" : "blocked"}</span>
        ${draft.compiled_strategy_name ? `<span class="tag success">${draft.compiled_strategy_name}</span>` : ""}
      </div>
    </section>
    <section class="definition-group">
      <h3>Indicators</h3>
      <div class="split-list">
        ${graph.indicators
          .map((indicator) => `
            <div>
              <strong>${indicator.node_id}</strong>
              <p>${indicator.kind.toUpperCase()} ${indicator.window}</p>
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
              <strong>${rule.stage}</strong>
              <p>${rule.description}</p>
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
    ${issues.length ? `<section class="definition-group"><h3>Issues</h3><p class="negative">${issues.join(" ")}</p></section>` : ""}
    ${warnings.length ? `<section class="definition-group"><h3>Warnings</h3><p>${warnings.join(" ")}</p></section>` : ""}
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
  renderAlerts(alerts || []);
  renderJobs(jobs || []);
  renderRuns(runs || []);
  renderTradeAudit(tradeAudit || []);
  renderCycle(lastCycle);
  renderVenues(venues);
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
elements.strategyForm.addEventListener("submit", buildStrategy);
elements.strategyValidateButton.addEventListener("click", validateStrategy);
elements.strategyBacktestButton.addEventListener("click", backtestStrategy);

window.addEventListener("load", () => {
  elements.jobSymbolInput.value = state.symbol;
  elements.manualSymbolInput.value = state.symbol;
  refresh();
  window.setInterval(refresh, 15000);
});
