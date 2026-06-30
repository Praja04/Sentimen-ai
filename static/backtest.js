let backtestResultsPerTF = null;
let backtestPayloadInfo = null;
let backtestAbortController = null;
const elements = {
    symbol: document.getElementById("symbol"),
    initialCapital: document.getElementById("initialCapital"),
    startMonth: document.getElementById("startMonth"),
    endMonth: document.getElementById("endMonth"),
    riskPct: document.getElementById("riskPct"),
    ddOperator: document.getElementById("ddOperator"),
    ddValue: document.getElementById("ddValue"),
    wrOperator: document.getElementById("wrOperator"),
    wrValue: document.getElementById("wrValue"),
    mpOperator: document.getElementById("mpOperator"),
    mpValue: document.getElementById("mpValue"),
    priority1: document.getElementById("priority1"),
    priority2: document.getElementById("priority2"),
    priority3: document.getElementById("priority3"),
    priority1: document.getElementById("priority1"),
    priority2: document.getElementById("priority2"),
    priority3: document.getElementById("priority3"),
    runBacktest: document.getElementById("runBacktest"),
    stopBacktest: document.getElementById("stopBacktest"),
    statusText: document.getElementById("statusText"),
    resultsContainer: document.getElementById("resultsContainer"),
    summarySymbol: document.getElementById("summarySymbol"),
    summaryBars: document.getElementById("summaryBars"),
    summaryStrategies: document.getElementById("summaryStrategies"),
    summaryPassing: document.getElementById("summaryPassing"),
};

function metricCard(label, value) {
    return `
        <div class="metric">
            <div class="label">${label}</div>
            <strong>${value}</strong>
        </div>
    `;
}

function renderMonthlyReport(rows) {
    if (!rows || !rows.length) {
        return `<div class="empty-state">Tidak ada data bulanan.</div>`;
    }

    const body = rows.map((row) => `
        <tr>
            <td>${row.month}</td>
            <td>${row.trades}</td>
            <td>${row.lot}</td>
            <td>${row.avg_lot}</td>
            <td>${row.avg_mae_r}</td>
            <td>${row.avg_mfe_r}</td>
            <td>$${row.profit_amount}</td>
            <td>${row.profit_pct}%</td>
            <td>${row.drawdown_pct}%</td>
            <td>${row.win_rate}%</td>
        </tr>
    `).join("");

    return `
        <div class="monthly-report">
            <div class="label">Monthly Report</div>
            <div class="table-wrap">
                <table class="monthly-table">
                    <thead>
                        <tr>
                            <th>Month</th>
                            <th>Trade</th>
                            <th>Lot</th>
                            <th>Avg Lot</th>
                            <th>MAE</th>
                            <th>MFE</th>
                            <th>Profit $</th>
                            <th>Profit %</th>
                            <th>DD</th>
                            <th>Winrate</th>
                        </tr>
                    </thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        </div>
    `;
}

function renderResults(payload) {
    const results = payload.results || [];
    const rangeLabel = payload.range?.start_month && payload.range?.end_month
        ? `${payload.range.start_month} -> ${payload.range.end_month}`
        : `${payload.symbol} / ${payload.timeframe}`;

    elements.summarySymbol.textContent = `${payload.symbol} / ${payload.timeframe} / ${rangeLabel}`;
    elements.summaryBars.textContent = payload.bars.toLocaleString("en-US");
    elements.summaryStrategies.textContent = payload.strategies_tested;
    elements.summaryPassing.textContent = payload.target_reached ? `Tercapai (${payload.passing_count})` : `Belum (${payload.passing_count})`;

    if (!results.length) {
        elements.resultsContainer.innerHTML = `<div class="empty-state">Tidak ada strategi yang punya trade cukup untuk dinilai. Coba tambah hari data atau ubah filter.</div>`;
        return;
    }

    elements.resultsContainer.innerHTML = results.map((item, index) => {
        const params = Object.entries(item.parameters)
            .map(([key, value]) => `<div class="param-chip">${key}: <strong>${value}</strong></div>`)
            .join("");

        const sampleTrades = (item.sample_trades || [])
            .map((trade) => `${trade.side} ${trade.reason} | R ${trade.r_multiple} | ${trade.profit_pct}%`)
            .join("<br>");

        return `
            <article class="result-card">
                <div class="result-head">
                    <div>
                        <div class="label">#${index + 1} | ${payload.method} | ${item.strategy_type}</div>
                        <h3>${item.strategy_name} <span class="badge tf-badge">${payload.timeframe}</span></h3>
                    </div>
                    <div class="badge ${item.passes_filters ? "pass" : "fail"}">
                        ${item.passes_filters ? "LOLOS FILTER" : "TIDAK LOLOS"}
                    </div>
                    <div>
                        <div class="label">Score</div>
                        <strong>${item.score}</strong>
                    </div>
                </div>
                <div class="metrics-grid">
                    ${metricCard("Win rate", `${item.win_rate}%`)}
                    ${metricCard("Max drawdown", `${item.max_drawdown_pct}%`)}
                    ${metricCard("Avg profit / month", `${item.avg_monthly_profit_pct}%`)}
                    ${metricCard("Net profit", `${item.net_profit_pct}%`)}
                </div>
                <div class="metrics-grid">
                    ${metricCard("Total trades", `${item.total_trades} (Buy: ${item.total_buy || 0}, Sell: ${item.total_sell || 0})`)}
                    ${metricCard("Ending balance", `$${item.ending_balance}`)}
                    ${metricCard("Avg MAE (R)", item.avg_mae_r)}
                    ${metricCard("Avg MFE (R)", item.avg_mfe_r)}
                </div>
                <div class="metrics-grid">
                    ${metricCard("Fundamental", `${payload.weighting.fundamental}%`)}
                    ${metricCard("Teknikal", `${payload.weighting.technical}%`)}
                    ${metricCard("RRR", item.parameters.rr)}
                    ${metricCard("Validasi filter", item.passes_filters ? "Lolos" : "Tidak")}
                </div>
                
                <div class="metrics-grid">
                    <div class="metric full-width" style="grid-column: span 4; border-top: 1px dashed var(--line); padding-top: 8px; margin-top: 8px;">
                        <div class="label" style="text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 4px;">Detail Logika Perdagangan (Rules)</div>
                        <div style="font-size: 12px; line-height: 1.5; color: var(--text);">
                            <strong>Trigger Isyarat:</strong> ${
                                item.strategy_type === 'xedy_v30_ai' ? 'Dynamic combined score + trend filter' :
                                item.strategy_type === 'xedy_trend_pullback' ? 'Trend alignment + EMA 21 pullback filter' :
                                item.strategy_type === 'xedy_mean_revert' ? 'Mean Reversion RSI Extreme boundary' :
                                item.strategy_type === 'xedy_breakout_confirm' ? 'Support/Resistance channel breakout' :
                                'MACD Momentum Crossover confirmation'
                            }<br>
                            <strong>Aturan Grid Averaging:</strong> Multi-Level Entry (maks. 3 tingkat, step 1.5 * ATR), Arah order wajib searah dengan Trend Fundamental (Strictly ${payload.fundamental_bias > 0 ? 'LONG Only' : 'SHORT Only'}).
                        </div>
                    </div>
                </div>

                <div class="param-row">${params}</div>
                <div class="sample-trades">
                    <div class="label">Sample trades</div>
                    ${sampleTrades || "Tidak ada sample trade."}
                </div>
                ${renderMonthlyReport(item.monthly_report)}
            </article>
        `;
    }).join("");
}

async function runBacktestSearch() {
    elements.runBacktest.disabled = true;
    elements.stopBacktest.style.display = "inline-block";
    const selectedTFs = Array.from(document.querySelectorAll('input[name="tf_select"]:checked')).map(el => el.value);
    if (!selectedTFs.length) {
        elements.statusText.textContent = "Error: Harap pilih minimal satu Timeframe pengujian.";
        elements.runBacktest.disabled = false;
        elements.stopBacktest.style.display = "none";
        return;
    }
    elements.statusText.textContent = `Menjalankan AI XEDY_V30 (${selectedTFs.join(", ")}) dengan bobot fundamental 80% dan teknikal 20%...`;
    
    backtestAbortController = new AbortController();

    const payload = {
        symbol: elements.symbol.value.trim() || "XAUUSD",
        sort_priority: [
            elements.priority1.value,
            elements.priority2.value,
            elements.priority3.value
        ],
        initial_capital: Number(elements.initialCapital.value || 10000),
        start_month: elements.startMonth.value || null,
        end_month: elements.endMonth.value || null,
        days: 30,
        risk_pct: Number(elements.riskPct.value || 1),
        timeframes: Array.from(document.querySelectorAll('input[name="tf_select"]:checked')).map(el => el.value),
        filters: {
            drawdown: {
                operator: elements.ddOperator.value,
                value: Number(elements.ddValue.value || 5),
            },
            win_rate: {
                operator: elements.wrOperator.value,
                value: Number(elements.wrValue.value || 80),
            },
            monthly_profit: {
                operator: elements.mpOperator.value,
                value: Number(elements.mpValue.value || 40),
            },
        },
    };

    try {
        const response = await fetch("/api/backtest/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: backtestAbortController.signal,
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Backtest request failed.");
        }

        elements.statusText.textContent = "Selesai! Backtest seluruh TF berhasil dijalankan.";
        backtestResultsPerTF = result.data.results_per_tf;
        backtestPayloadInfo = result.data;
        
        // Dynamically build TF tabs based on keys returned
        const activeTFs = Object.keys(backtestResultsPerTF);
        const tfTabsContainer = document.getElementById("tfTabs");
        tfTabsContainer.innerHTML = activeTFs.map((tf, index) => {
            const activeClass = index === 0 ? "active" : "";
            return `<button class="tf-tab ${activeClass}" data-tf="${tf}">${tf}</button>`;
        }).join("");
        
        // Re-attach event listeners to new tabs
        document.querySelectorAll(".tf-tab").forEach(tab => {
            tab.addEventListener("click", () => {
                const tf = tab.getAttribute("data-tf");
                switchTF(tf);
            });
        });
        
        if (activeTFs.length > 0) {
            switchTF(activeTFs[0]);
        }
    } catch (error) {
        elements.resultsContainer.innerHTML = `<div class="empty-state">${error.message}</div>`;
        elements.statusText.textContent = "Backtest gagal dijalankan.";
    } finally {
        elements.runBacktest.disabled = false;
        elements.stopBacktest.style.display = "none";
        backtestAbortController = null;
    }
}

function passingSummary(payload) {
    const passing = (payload.results || []).filter((item) => item.passes_filters).length;
    return `${passing} dari ${payload.results.length} hasil top-10 lolos filter validasi`;
}

elements.runBacktest.addEventListener("click", runBacktestSearch);

async function stopBacktestExecution() {
    try {
        // Send stop command to backend
        fetch("/api/backtest/stop", { method: "POST" });
    } catch (e) {
        console.error("Failed to notify backend stop:", e);
    }
    
    if (backtestAbortController) {
        backtestAbortController.abort();
    }
    
    elements.statusText.textContent = "Backtest dihentikan oleh user.";
    elements.runBacktest.disabled = false;
    elements.stopBacktest.style.display = "none";
}

elements.stopBacktest.addEventListener("click", stopBacktestExecution);

function switchTF(tf) {
    if (!backtestResultsPerTF || !backtestResultsPerTF[tf]) return;
    
    // Update active tab styling
    document.querySelectorAll(".tf-tab").forEach(tab => {
        if (tab.getAttribute("data-tf") === tf) {
            tab.classList.add("active");
        } else {
            tab.classList.remove("active");
        }
    });
    
    const tfData = backtestResultsPerTF[tf];
    renderResults(tfData);
}


