let backtestResultsPerTF = null;
let backtestPayloadInfo = null;
let backtestAbortController = null;
let currentDemoState = null;
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

        // Check if this strategy is currently the active one in the demo state
        const activeConfig = currentDemoState?.active_config;
        const isActive = activeConfig &&
                         activeConfig.timeframe === payload.timeframe &&
                         activeConfig.strategy_type === item.strategy_type;

        return `
            <article class="result-card" style="${isActive ? 'border: 1.5px solid var(--text-yellow); box-shadow: 0 0 15px rgba(255,215,0,0.15);' : ''}">
                <div class="result-head">
                    <div>
                        <div class="label">#${index + 1} | ${payload.method} | ${item.strategy_type}</div>
                        <h3>${item.strategy_name} <span class="badge tf-badge">${payload.timeframe}</span></h3>
                    </div>
                    <!-- Single selection checkbox -->
                    <div class="strategy-select-container" style="background: rgba(255,215,0,0.05); border: 1px solid rgba(255,215,0,0.2); padding: 4px 10px; border-radius: 20px; display: flex; align-items: center; gap: 8px;">
                        <input type="checkbox" class="strategy-selector-chk" 
                               data-tf="${payload.timeframe}"
                               data-risk="${payload.risk_pct || payload.risk_percent || document.getElementById('riskPct')?.value || 1.0}"
                               data-type="${item.strategy_type}"
                               data-name="${item.strategy_name.replace(/'/g, "\'")}"
                               data-win="${item.win_rate}"
                               data-dd="${item.max_drawdown_pct}"
                               data-profit="${item.net_profit_pct}"
                               ${isActive ? "checked" : ""}
                               onchange="handleStrategySelect(this)"
                               style="width: 14px !important; height: 14px !important; margin: 0; accent-color: var(--text-yellow); cursor: pointer;" />
                        <span style="font-size: 0.65rem; font-weight: bold; color: var(--text-yellow); font-family: 'Rajdhani', sans-serif; cursor: pointer;" onclick="const chk=this.previousElementSibling; chk.checked=!chk.checked; chk.dispatchEvent(new Event('change'));">SIAP LIVE TEST</span>
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
        
        // Save to localStorage for persistence across refreshes
        localStorage.setItem("xedy_backtest_results", JSON.stringify(backtestResultsPerTF));
        localStorage.setItem("xedy_backtest_payload", JSON.stringify(backtestPayloadInfo));
        if (typeof toggleResetBacktestBtn === "function") toggleResetBacktestBtn();
        
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
            for (const [symbol, tickInfo] of Object.entries(data.ticks)) {
                // Handle naming conversion for HTML IDs
                const key = symbol.replace(/\s+/g, '-');
                const bidEl = document.getElementById(`ticker-bid-${key}`);
                const askEl = document.getElementById(`ticker-ask-${key}`);
                const chgEl = document.getElementById(`ticker-chg-${key}`);
                const volEl = document.getElementById(`ticker-vol-${key}`);
                
                // Formats
                const isJPY = symbol.includes('JPY');
                const isDJI = symbol.includes('DJI');
                let decimals = 2;
                if (isJPY) decimals = 3;
                else if (isDJI) decimals = 1;
                else if (symbol.includes('EUR') || symbol.includes('GBP')) decimals = 5;
                
                const lowEl = document.getElementById(`ticker-low-${key}`);
                const highEl = document.getElementById(`ticker-high-${key}`);
                
                if (bidEl) bidEl.innerText = tickInfo.bid.toFixed(decimals);
                if (askEl) askEl.innerText = tickInfo.ask.toFixed(decimals);
                if (chgEl) {
                    chgEl.innerText = (tickInfo.change >= 0 ? "+" : "") + tickInfo.change.toFixed(3) + "%";
                    chgEl.className = tickInfo.change >= 0 ? "text-green" : "text-red";
                }
                if (volEl) volEl.innerText = tickInfo.volume.toLocaleString('en-US');
                if (lowEl) lowEl.innerText = tickInfo.low.toFixed(decimals);
                if (highEl) highEl.innerText = tickInfo.high.toFixed(decimals);
            }
        }
        if(!data.error && data.demo) {
            currentDemoState = data.demo;
            renderLiveDemo(data.demo);
        }
    } catch (e) {
        console.error("Fast tick fetch failed on backtest page:", e);
    }
}

function renderLiveDemo(demo) {
    // Live test demo rendering disabled
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

// Handle single checklist strategy selection across all timeframes with confirmation
async function handleStrategySelect(checkbox) {
    const isChecked = checkbox.checked;
    
    const tf = checkbox.getAttribute('data-tf');
    const risk = checkbox.getAttribute('data-risk');
    const type = checkbox.getAttribute('data-type');
    const name = checkbox.getAttribute('data-name');
    const win = checkbox.getAttribute('data-win');
    const dd = checkbox.getAttribute('data-dd');
    const profit = checkbox.getAttribute('data-profit');

    if (isChecked) {
        // Show confirmation prompt BEFORE applying
        if (confirm(`Apakah Anda yakin ingin memilih strategi ini untuk LIVE TEST?\n\n- Nama: ${name}\n- Timeframe: ${tf}\n- Risk: ${risk}%`)) {
            // Uncheck all other checkboxes instantly
            const allCheckboxes = document.querySelectorAll('.strategy-selector-chk');
            allCheckboxes.forEach(chk => {
                if (chk !== checkbox) chk.checked = false;
            });
            
            await deployToLiveTest(tf, risk, type, name, win, dd, profit);
        } else {
            checkbox.checked = false; // Revert checkbox if canceled
        }
    } else {
        // Show confirmation prompt BEFORE disabling
        if (confirm("Apakah Anda yakin ingin menonaktifkan strategi ini dari Live Test?")) {
            await clearActiveLiveTestStrategy();
        } else {
            checkbox.checked = true; // Revert checkbox if canceled
        }
    }
}

// Deploy strategy config parameters to the backend active configuration
async function deployToLiveTest(timeframe, riskPercent, strategyType, strategyName, winRate, maxDrawdown, netProfit) {
    try {
        const payload = {
            timeframe,
            risk_percent: parseFloat(riskPercent),
            strategy_type: strategyType,
            strategy_name: strategyName,
            win_rate: parseFloat(winRate),
            max_drawdown: parseFloat(maxDrawdown),
            net_profit: parseFloat(netProfit)
        };
        
        const res = await fetch('/api/livetest/apply_parameters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        if (data.status === "success") {
            alert(`🚀 SUKSES!\n\nParameter Strategi "${strategyName}" (${timeframe}) berhasil diterapkan ke Live Test.`);
            location.reload(); // Reload to refresh layouts and configurations
        } else {
            alert(`❌ Gagal menerapkan parameter: ${data.message}`);
        }
    } catch (e) {
        console.error("Deploy parameters failed:", e);
        alert(`❌ Error: ${e.message}`);
    }
}

// Clear active strategy parameters from the live test
async function clearActiveLiveTestStrategy() {
    try {
        const res = await fetch('/api/livetest/clear_parameters', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.status === "success") {
            alert("✅ Reset Sukses! Live Test kini berjalan dengan parameter bawaan.");
            location.reload();
        } else {
            alert(`❌ Gagal reset: ${data.message}`);
        }
    } catch (e) {
        console.error("Reset active strategy failed:", e);
        alert(`❌ Error: ${e.message}`);
    }
}


// Toggle visibility of the Reset Backtest button
function toggleResetBacktestBtn() {
    const btnReset = document.getElementById("resetBacktest");
    if (btnReset) {
        if (localStorage.getItem("xedy_backtest_results")) {
            btnReset.style.display = "inline-block";
        } else {
            btnReset.style.display = "none";
        }
    }
}

// Reset the live test simulation (balance back to $10,000, empty history and active trades)
async function resetLiveSimulation() {
    if (confirm("⚠️ PERINGATAN!\n\nApakah Anda yakin ingin me-reset simulasi Live Test?\nSemua riwayat transaksi dan perdagangan aktif akan dihapus, dan modal akan dikembalikan ke $10,000.00.")) {
        try {
            const res = await fetch('/api/livetest/reset_simulation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            if (data.status === "success") {
                alert("✅ Reset Sukses! Simulasi Live Test dikembalikan ke modal awal.");
                location.reload();
            } else {
                alert(`❌ Gagal reset: ${data.message}`);
            }
        } catch (e) {
            console.error("Reset simulation failed:", e);
            alert(`❌ Error: ${e.message}`);
        }
    }
}

// Initialize persistence and button wiring on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
    // 1. Wire up reset backtest button
    const btnReset = document.getElementById("resetBacktest");
    if (btnReset) {
        toggleResetBacktestBtn();
        btnReset.addEventListener("click", () => {
            if (confirm("Apakah Anda yakin ingin menghapus seluruh hasil backtest yang tersimpan?")) {
                localStorage.removeItem("xedy_backtest_results");
                localStorage.removeItem("xedy_backtest_payload");
                backtestResultsPerTF = null;
                backtestPayloadInfo = null;
                elements.resultsContainer.innerHTML = '<div class="empty-state">Belum ada hasil. Jalankan pencarian dulu.</div>';
                
                // Hide tabs
                const tfTabsContainer = document.getElementById("tfTabs");
                if (tfTabsContainer) tfTabsContainer.innerHTML = "";
                
                toggleResetBacktestBtn();
            }
        });
    }
    
    // 2. Restore saved backtest results from localStorage
    const savedResults = localStorage.getItem("xedy_backtest_results");
    const savedPayload = localStorage.getItem("xedy_backtest_payload");
    if (savedResults && savedPayload) {
        try {
            backtestResultsPerTF = JSON.parse(savedResults);
            backtestPayloadInfo = JSON.parse(savedPayload);
            
            elements.statusText.textContent = "Selesai! Hasil pencarian backtest tersimpan dipulihkan.";
            
            const activeTFs = Object.keys(backtestResultsPerTF);
            const tfTabsContainer = document.getElementById("tfTabs");
            if (tfTabsContainer) {
                tfTabsContainer.innerHTML = activeTFs.map((tf, index) => {
                    const activeClass = index === 0 ? "active" : "";
                    return `<button class="tf-tab ${activeClass}" data-tf="${tf}">${tf}</button>`;
                }).join("");
                
                document.querySelectorAll(".tf-tab").forEach(tab => {
                    tab.addEventListener("click", () => {
                        const tf = tab.getAttribute("data-tf");
                        switchTF(tf);
                    });
                });
            }
            
            if (activeTFs.length > 0) {
                switchTF(activeTFs[0]);
            }
            toggleResetBacktestBtn();
        } catch (e) {
            console.error("Failed to restore saved backtest results:", e);
        }
    }
});

async function handleStrategySelect(checkbox) {
    // Disabled
}
async function deployToLiveTest(timeframe, riskPercent, strategyType, strategyName, winRate, maxDrawdown, netProfit) {
    // Disabled
}
async function clearActiveLiveTestStrategy() {
    // Disabled
}
async function resetLiveSimulation() {
    // Disabled
}
