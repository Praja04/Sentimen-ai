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
        elements.statusText.textContent = `Backtest gagal dijalankan: ${error.message}`;
        console.error("Backtest Error:", error);
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



// ==========================================================
// LIVETEST REAL-TIME TICKER & POSITION RENDER
// ==========================================================
async function fetchLiveTicks() {
    try {
        const res = await fetch(`/api/live_ticks?t=${new Date().getTime()}`, {
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });
        const data = await res.json();
        if(!data.error && data.ticks) {
            // Update XAUUSD live pricing card inside hero-card
            const goldTick = data.ticks["XAUUSD"];
            if (goldTick) {
                const bidEl = document.getElementById("live-bid-XAUUSD");
                const askEl = document.getElementById("live-ask-XAUUSD");
                const chgEl = document.getElementById("live-chg-XAUUSD");
                const volEl = document.getElementById("live-vol-XAUUSD");
                
                if (bidEl) bidEl.innerText = goldTick.bid.toFixed(2);
                if (askEl) askEl.innerText = goldTick.ask.toFixed(2);
                if (chgEl) {
                    chgEl.innerText = (goldTick.change >= 0 ? "+" : "") + goldTick.change.toFixed(3) + "%";
                    chgEl.className = goldTick.change >= 0 ? "text-green" : "text-red";
                }
                if (volEl) volEl.innerText = goldTick.volume.toLocaleString('en-US');
            }
        }
        if(!data.error && data.demo) {
            renderLiveDemo(data.demo);
        }
    } catch (e) {
        console.error("Fast tick fetch failed on backtest page:", e);
    }
}

function renderLiveDemo(demo) {
    // 1. Account Cards
    document.getElementById("live-balance").innerText = `$${demo.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    document.getElementById("live-equity").innerText = `$${demo.equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    
    const totalProfit = demo.equity - 10000.0;
    const totalProfitPct = (totalProfit / 10000.0) * 100.0;
    const profitEl = document.getElementById("live-profit");
    
    if (totalProfit >= 0) {
        profitEl.innerText = `+$${totalProfit.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (+${totalProfitPct.toFixed(2)}%)`;
        profitEl.className = "text-green";
    } else {
        profitEl.innerText = `-$${Math.abs(totalProfit).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${totalProfitPct.toFixed(2)}%)`;
        profitEl.className = "text-red";
    }
    
    // 2. Current Status
    const statusEl = document.getElementById("live-status");
    const activeList = demo.active_trades || [];
    if (activeList.length > 0) {
        const t = activeList[0];
        statusEl.innerText = `TRADING ${t.type} / ENTRY: ${t.entry_price}`;
        statusEl.className = t.type === "BUY" ? "text-green" : "text-red";
    } else {
        statusEl.innerText = "SCANNING FOR SIGNALS...";
        statusEl.className = "text-yellow";
    }
    
    // 3. Active Trades Table (MT5 layout)
    const activeBody = document.getElementById("live-active-trades-body");
    let activeHtml = "";
    let runningProfitTotal = 0;
    
    if (activeList.length > 0) {
        activeHtml = activeList.map(t => {
            runningProfitTotal += t.profit;
            const formattedProfit = t.profit >= 0 ? `+${t.profit.toFixed(2)}` : t.profit.toFixed(2);
            return `
                <tr>
                    <td>${t.symbol}</td>
                    <td>${t.ticket}</td>
                    <td>${t.time}</td>
                    <td class="${t.type === 'BUY' ? 'text-green' : 'text-red'}" style="font-weight:bold;">${t.type.toLowerCase()}</td>
                    <td>${t.lots.toFixed(2)}</td>
                    <td>${t.entry_price.toFixed(2)}</td>
                    <td>${t.sl.toFixed(2)}</td>
                    <td>${t.tp.toFixed(2)}</td>
                    <td>${t.current_price.toFixed(2)}</td>
                    <td class="${t.profit >= 0 ? 'text-green' : 'text-red'}" style="font-weight:bold; text-align:right;">
                        ${formattedProfit}
                    </td>
                </tr>
            `;
        }).join("");
    } else {
        activeHtml = `<tr><td colspan="10" class="empty-state">Tidak ada transaksi aktif saat ini.</td></tr>`;
    }
    
    // Insert MT5 summary row for Trade tab
    const formattedTotalProfit = runningProfitTotal >= 0 ? `+${runningProfitTotal.toFixed(2)}` : runningProfitTotal.toFixed(2);
    activeHtml += `
        <tr class="mt5-summary-row">
            <td colspan="9">
                <b>• Balance: ${demo.balance.toFixed(2)} USD Equity: ${demo.equity.toFixed(2)} Free Margin: ${demo.equity.toFixed(2)}</b>
            </td>
            <td class="${runningProfitTotal >= 0 ? 'text-green' : 'text-red'}" style="font-weight:bold; text-align:right;">
                ${runningProfitTotal !== 0 ? formattedTotalProfit : '0.00'}
            </td>
        </tr>
    `;
    activeBody.innerHTML = activeHtml;
    
    // 4. Closed History Table (MT5 layout)
    const historyBody = document.getElementById("live-history-trades-body");
    const historyList = demo.history || [];
    let historyHtml = "";
    let totalClosedProfit = 0;
    
    if (historyList.length > 0) {
        historyHtml = historyList.map(h => {
            totalClosedProfit += h.net_profit;
            const formattedProfit = h.net_profit >= 0 ? `+${h.net_profit.toFixed(2)}` : h.net_profit.toFixed(2);
            
            // Calculate percentage change return
            const initialCap = 10000.0;
            const pctChange = (h.net_profit / initialCap) * 100.0;
            const formattedChange = pctChange >= 0 ? `+${pctChange.toFixed(3)}%` : `${pctChange.toFixed(3)}%`;
            
            return `
                <tr>
                    <td>${h.open_time}</td>
                    <td>${h.symbol || 'XAUUSD'}</td>
                    <td>${h.ticket}</td>
                    <td class="${h.type === 'BUY' ? 'text-green' : 'text-red'}" style="font-weight:bold;">${h.type.toLowerCase()}</td>
                    <td>${h.lots.toFixed(2)}</td>
                    <td>${h.entry.toFixed(2)}</td>
                    <td>${h.sl.toFixed(2)}</td>
                    <td>${h.tp.toFixed(2)}</td>
                    <td>${h.close_time}</td>
                    <td>${h.exit.toFixed(2)}</td>
                    <td class="${h.net_profit >= 0 ? 'text-green' : 'text-red'}" style="font-weight:bold;">
                        ${formattedProfit}
                    </td>
                    <td class="${h.net_profit >= 0 ? 'text-green' : 'text-red'}" style="font-weight:bold; text-align:right;">
                        ${formattedChange}
                    </td>
                </tr>
            `;
        }).join("");
    } else {
        historyHtml = `<tr><td colspan="12" class="empty-state">Belum ada riwayat transaksi.</td></tr>`;
    }
    
    // Insert MT5 summary row for History tab
    const formattedTotalClosed = totalClosedProfit >= 0 ? `+${totalClosedProfit.toFixed(2)}` : totalClosedProfit.toFixed(2);
    historyHtml += `
        <tr class="mt5-summary-row">
            <td colspan="10">
                <b>• Profit: ${totalClosedProfit.toFixed(2)} Credit: 0.00 Deposit: 10000.00 Withdrawal: 0.00 Balance: ${demo.balance.toFixed(2)}</b>
            </td>
            <td class="${totalClosedProfit >= 0 ? 'text-green' : 'text-red'}" style="font-weight:bold; text-align:right;" colspan="2">
                ${formattedTotalClosed}
            </td>
        </tr>
    `;
    historyBody.innerHTML = historyHtml;
}

// Initialise live tick fetch loop
document.addEventListener("DOMContentLoaded", () => {
    fetchLiveTicks();
    setInterval(fetchLiveTicks, 1000);
    
    // checklist state persistence
    const chkLiveReady = document.getElementById("chk-live-ready");
    if (chkLiveReady) {
        const savedState = localStorage.getItem("chk-live-ready-state");
        if (savedState === "true") {
            chkLiveReady.checked = true;
        }
        chkLiveReady.addEventListener("change", (e) => {
            localStorage.setItem("chk-live-ready-state", e.target.checked);
        });
    }
});
