const state = {
  symbol: "BTC-USD",
  timeframe: "1h",
  overview: null,
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

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof payload === "object" && payload?.detail ? payload.detail : payload;
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
        const path =
          action === "run"
            ? `/paper/jobs/${jobId}/run`
            : `/paper/jobs/${jobId}/${action}`;
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
      return `
        <article class="alert-item">
          <header>
            <strong>${run.symbol} - ${jobLabel}</strong>
            <time>${new Date(run.started_at).toLocaleString()}</time>
          </header>
          <p><span class="${tone}">${run.status}</span>${execution}</p>
          ${error}
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

function renderOverview(overview) {
  state.overview = overview;
  const {
    config,
    market,
    features,
    portfolio,
    alerts,
    jobs,
    runs,
    trade_audit: tradeAudit,
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
  setText(
    "equity-value",
    money(portfolio.equity),
  );
  setText(
    "equity-subtext",
    `${money(portfolio.cash)} cash - ${Object.keys(portfolio.positions || {}).length} open positions${staleSuffix}`,
  );

  const dailyClass = portfolio.daily_pnl_fraction >= 0 ? "positive" : "negative";
  setText("daily-pnl-value", percent(portfolio.daily_pnl_fraction), dailyClass);
  setText(
    "backtest-return-value",
    percent(backtest.metrics.total_return_fraction),
    backtest.metrics.total_return_fraction >= 0 ? "positive" : "negative",
  );
  setText("walk-forward-sharpe-value", number(backtest.walk_forward_summary.average_sharpe_ratio, 2));
  setText("max-drawdown-value", percent(backtest.metrics.max_drawdown_fraction), "negative");
  setText("ema20-value", money(features.ema_20));
  setText("ema50-value", money(features.ema_50));
  setText("ema200-value", money(features.ema_200));
  setText("rsi-value", number(features.rsi_14, 1));

  const priceSeries = market.recent_bars.map((bar) => ({ value: bar.close }));
  document.getElementById("price-chart").innerHTML = chartSvg(priceSeries, "#73d5b2");

  const equitySeries = backtest.equity_curve.map((point) => ({ value: point.equity }));
  document.getElementById("equity-chart").innerHTML = chartSvg(equitySeries, "#f5b667");

  const warningTags = [];
  if (backtest.leakage_check.passed) {
    warningTags.push({ label: "Leakage check passed", kind: "success" });
  }
  backtest.metrics.warnings.forEach((warning) => warningTags.push({ label: warning, kind: "warning" }));
  backtest.walk_forward_summary.warnings.forEach((warning) => warningTags.push({ label: warning, kind: "warning" }));
  renderTags("backtest-warning-list", warningTags);

  renderPositions(portfolio.positions);
  renderAlerts(alerts || []);
  renderJobs(jobs || []);
  renderRuns(runs || []);
  renderTradeAudit(tradeAudit || []);
  renderCycle(lastCycle);
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
    await fetchOverview();
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
    await fetchOverview();
  } catch (error) {
    elements.cycleStatus.textContent = error.message;
  } finally {
    elements.manualOrderButton.disabled = false;
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

window.addEventListener("load", () => {
  elements.jobSymbolInput.value = state.symbol;
  elements.manualSymbolInput.value = state.symbol;
  refresh();
  window.setInterval(refresh, 15000);
});
