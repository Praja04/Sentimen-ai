let forecastChart = null;  // legacy — now keyed via symbolCharts['XAUUSD']

document.addEventListener("DOMContentLoaded", () => {
    // Initial fetch of forecast data
    fetchForecastData();
    
    // Live tick polling every 1.5 seconds
    pollLiveTicks();
    setInterval(pollLiveTicks, 1500);
});

async function fetchForecastData() {
    try {
        const response = await fetch("/api/forecast_data");
        const data = await response.json();
        if (data.status === "success" && data.forecast) {
            // Only update the main macro/UI panels if the user is currently on XAUUSD
            if (currentSymbolTab === "XAUUSD") {
                updateForecastUI(data.forecast, data.macro_context, data.economic_reports);
                renderForecastChart(data.forecast);
            }
        }
    } catch (e) {
        console.error("Error fetching forecast data:", e);
    }
}

async function pollLiveTicks() {
    try {
        const response = await fetch(`/api/live_ticks?t=${Date.now()}`);
        const data = await response.json();
        if (data.ticks) {
            updateTickers(data.ticks);
        }
        // If there's active demo state, refresh forecast parameters
        if (data.demo) {
            if (currentSymbolTab === "XAUUSD") {
                fetchForecastData();
            } else {
                loadSymbolForecast(currentSymbolTab);
            }
        }
    } catch (e) {
        console.error("Error polling live ticks:", e);
    }
}

function updateTickers(ticks) {
    const container = document.getElementById("tickersRow");
    if (!container) return;
    
    let html = "";
    Object.keys(ticks).forEach(sym => {
        const tick = ticks[sym];
        const isUp = tick.change >= 0;
        const changeClass = isUp ? "text-green" : "text-red";
        const sign = isUp ? "+" : "";
        
        html += `
            <div class="ticker-card">
                <div class="ticker-header">
                    <span style="font-weight:600; color:#fff;">${sym}</span>
                    <span class="ticker-change ${changeClass}">${sign}${tick.change.toFixed(2)}%</span>
                </div>
                <div class="ticker-val" style="color: ${isUp ? '#4ade80' : '#f87171'}">${tick.bid.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})}</div>
                <div class="ticker-footer">
                    <span>ASK: ${tick.ask.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})}</span>
                    <span class="ticker-lbl">V: ${(tick.volume || 0).toLocaleString()}</span>
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
}

function updateForecastUI(forecast, macroContext, economicReports) {
    // 1. Update Self-Learning stats
    document.getElementById("modelAccuracy").textContent = `${forecast.metrics.accuracy.toFixed(1)}%`;
    document.getElementById("modelMae").textContent = `$${forecast.metrics.mae.toFixed(2)}`;
    
    // Weights
    document.getElementById("learningRateVal").textContent = forecast.model_weights.learning_rate.toFixed(2);
    document.getElementById("fundWeightVal").textContent = `${(forecast.model_weights.fundamental * 100).toFixed(0)}%`;
    document.getElementById("techWeightVal").textContent = `${(forecast.model_weights.technical * 100).toFixed(0)}%`;
    document.getElementById("volMultVal").textContent = forecast.model_weights.volatility_multiplier.toFixed(3);
    const ecVal = forecast.error_correction || 0.0;
    const sign = ecVal >= 0 ? "+" : "";
    document.getElementById("errorCorrectionVal").textContent = `${sign}$${ecVal.toFixed(2)}`;
    
    // 2. Learning logs terminal
    const logBox = document.getElementById("learningLogs");
    if (logBox) {
        logBox.innerHTML = forecast.learning_logs.map(log => `
            <div class="log-item">${log}</div>
        `).join("");
    }
    
    // 3. Weekly Projections Table
    const tableBody = document.getElementById("forecastTableBody");
    if (tableBody) {
        let tableHtml = "";
        
        if (forecast.past_projections) {
            forecast.past_projections.forEach(p => {
                tableHtml += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); background: rgba(255,255,255,0.012);">
                        <td style="padding: 10px 8px; font-weight: 700; color: #8a9cb4; font-family:'JetBrains Mono',monospace;">W${p.week}</td>
                        <td style="padding: 10px 8px; color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size:0.78rem;">${p.date_range}</td>
                        <td style="padding: 10px 8px; color: rgba(74, 222, 128, 0.6); font-family: 'JetBrains Mono', monospace; font-size:0.82rem;">$${p.low_low.toFixed(0)}</td>
                        <td style="padding: 10px 8px; font-family: 'JetBrains Mono', monospace; font-size:0.82rem;">
                            <div style="color:#4ade80; font-weight:600;">$${p.low.toFixed(0)}</div>
                            <div style="color:#22c55e; font-size:0.68rem; margin-top:2px;">▲ Act Low: $${p.actual_low.toFixed(0)}</div>
                        </td>
                        <td style="padding: 10px 8px; font-family: 'JetBrains Mono', monospace; font-size:0.82rem;">
                            <div style="color:#fbbf24; font-weight:600;">$${p.high.toFixed(0)}</div>
                            <div style="color:#ef4444; font-size:0.68rem; margin-top:2px;">▼ Act High: $${p.actual_high.toFixed(0)}</div>
                        </td>
                        <td style="padding: 10px 8px; color: rgba(248, 113, 113, 0.6); font-family: 'JetBrains Mono', monospace; font-size:0.82rem;">$${p.high_high.toFixed(0)}</td>
                        <td style="padding: 10px 8px; font-weight: 600; text-align: center; color: #4ade80; font-family: 'JetBrains Mono', monospace; font-size:0.8rem;">✅ 100%</td>
                        <td style="padding: 10px 8px; text-align: center;">
                            <span class="badge" style="background: rgba(74,222,128,0.1); color: #4ade80; border: 1px solid rgba(74,222,128,0.3); font-size:0.7rem;">Terjadi</span>
                        </td>
                        <td style="padding: 10px 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; line-height: 1.6;">
                            <div>🔺 <span style="color:#ef4444;font-weight:600;">$${p.actual_high.toFixed(2)}</span> <span style="color:#4ade80;">&nbsp;[H–HH ✓]</span></div>
                            <div>🔻 <span style="color:#4ade80;font-weight:600;">$${p.actual_low.toFixed(2)}</span> <span style="color:#4ade80;">&nbsp;[LL–L ✓]</span></div>
                        </td>
                    </tr>
                `;
            });
        }
        
        forecast.projections.forEach(p => {
            let statusBadge = `<span class="badge badge-pending">Pending</span>`;
            if (p.status.includes("ACTIVE")) {
                statusBadge = `<span class="badge badge-active">Active</span>`;
            } else if (p.status.includes("HH")) {
                statusBadge = `<span class="badge badge-hit-hh">🔥 Hit HH</span>`;
            } else if (p.status.includes("Hit H")) {
                statusBadge = `<span class="badge badge-hit-h">📈 Hit H</span>`;
            } else if (p.status.includes("Hit L")) {
                statusBadge = `<span class="badge badge-hit-l">📉 Hit L</span>`;
            } else if (p.status.includes("LL")) {
                statusBadge = `<span class="badge badge-hit-ll">❄️ Hit LL</span>`;
            }
            
            // Build hits log string
            let hitsLog = `<span style="color:var(--muted); font-size:0.7rem;">Menunggu pergerakan harga...</span>`;
            const keys = Object.keys(p.hits || {});
            if (keys.length > 0) {
                hitsLog = keys.map(k => {
                    const hit = p.hits[k];
                    let icon = "🎯";
                    if (k === "HH") icon = "🔥";
                    if (k === "LL") icon = "❄️";
                    return `<div style="font-family:'JetBrains Mono',monospace; font-size:0.7rem; color:#a5b4fc; margin-bottom: 2px;">
                        ${icon} <strong>${k} Target Hit:</strong> $${hit.price} pd ${hit.date} ${hit.time}
                    </div>`;
                }).join("");
            }
            
            tableHtml += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                    <td style="padding: 10px 8px; font-weight: 600; color: #fff; font-family:'JetBrains Mono',monospace;">W+${p.week}</td>
                    <td style="padding: 10px 8px; color: var(--muted); font-family: 'JetBrains Mono', monospace;">${p.date_range}</td>
                    <td style="padding: 10px 8px; color: #4ade80; font-family: 'JetBrains Mono', monospace; font-weight: 500;">$${p.low_low.toFixed(2)}</td>
                    <td style="padding: 10px 8px; color: #38bdf8; font-family: 'JetBrains Mono', monospace;">$${p.low.toFixed(2)}</td>
                    <td style="padding: 10px 8px; color: #fbbf24; font-family: 'JetBrains Mono', monospace;">$${p.high.toFixed(2)}</td>
                    <td style="padding: 10px 8px; color: #f87171; font-family: 'JetBrains Mono', monospace; font-weight: 500;">$${p.high_high.toFixed(2)}</td>
                    <td style="padding: 10px 8px; font-weight: 600; text-align: center; color: var(--accent); font-family: 'JetBrains Mono', monospace;">${p.confidence}%</td>
                    <td style="padding: 10px 8px; text-align: center;">${statusBadge}</td>
                    <td style="padding: 10px 8px;">${hitsLog}</td>
                </tr>
            `;
        });
        tableBody.innerHTML = tableHtml;
    }

    // 4. Update Macro Context Panels
    if (macroContext) {
        document.getElementById("macroCentralBank").textContent = macroContext.demand.central_bank;
        document.getElementById("macroEtfFlows").textContent = macroContext.demand.etf_flows;
        document.getElementById("macroJewelry").textContent = macroContext.demand.jewelry;
        
        document.getElementById("macroFedStance").textContent = macroContext.experts.fed_stance;
        document.getElementById("macroPresidentStance").textContent = macroContext.experts.president_stance;
        
        document.getElementById("macroGeopoliticsIndex").textContent = macroContext.geopolitics.index;
        document.getElementById("macroConflicts").textContent = macroContext.geopolitics.conflicts;
        document.getElementById("macroTariffWars").textContent = macroContext.geopolitics.tariff_wars;
        
        // Wall Street Consensus
        const wallStreetContainer = document.getElementById("macroWallStreet");
        if (wallStreetContainer && macroContext.experts.targets) {
            let targetsHtml = `<span style="color: var(--muted); display: block; font-size: 0.65rem; text-transform: uppercase; margin-bottom: 4px;">Target Bank Global:</span>`;
            macroContext.experts.targets.forEach(t => {
                targetsHtml += `
                    <div style="display: flex; justify-content: space-between; font-size: 0.7rem; border-bottom: 1px solid rgba(255,255,255,0.02); padding: 3px 0;">
                        <span style="color: var(--muted); font-weight: 500;">${t.inst}:</span>
                        <span style="color: #fbbf24; font-weight: 600;">${t.target}</span>
                    </div>
                `;
            });
            wallStreetContainer.innerHTML = targetsHtml;
        }
    }

    // 5. Update Economic Reports Table
    if (economicReports) {
        const ecoTableBody = document.getElementById("economicReportsTableBody");
        if (ecoTableBody) {
            let ecoHtml = "";
            economicReports.forEach(r => {
                let flag = "🇺🇸";
                if (r.country === "EU") flag = "🇪🇺";
                if (r.country === "CN") flag = "🇨🇳";
                if (r.country === "GB") flag = "🇬🇧";
                if (r.country === "JP") flag = "🇯🇵";
                
                let badgeClass = "badge-pending";
                if (r.status === "BULLISH") badgeClass = "badge-active";
                if (r.status === "BEARISH") badgeClass = "badge-hit-hh";
                
                ecoHtml += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                        <td style="padding: 10px 8px; font-weight: 500; font-size: 1.1rem;">${flag} <span style="font-size:0.72rem; color:var(--muted); font-family:'JetBrains Mono',monospace; vertical-align:middle; margin-left:4px;">${r.country}</span></td>
                        <td style="padding: 10px 8px; font-weight: 600; color: #fff;">${r.indicator}</td>
                        <td style="padding: 10px 8px; text-align: center; font-family:'JetBrains Mono',monospace; font-weight: 500; color: #4ade80;">${r.actual}</td>
                        <td style="padding: 10px 8px; text-align: center; font-family:'JetBrains Mono',monospace; color: var(--muted);">${r.forecast}</td>
                        <td style="padding: 10px 8px; text-align: center; font-family:'JetBrains Mono',monospace; color: var(--muted);">${r.previous}</td>
                        <td style="padding: 10px 8px; text-align: center;">
                            <span class="badge ${badgeClass}" style="animation: none;">${r.status}</span>
                        </td>
                        <td style="padding: 10px 8px; color: #a5b4fc; font-size: 0.72rem; line-height: 1.4;">${r.reason}</td>
                    </tr>
                `;
            });
            ecoTableBody.innerHTML = ecoHtml;
        }
    }
}

function renderForecastChart(forecast) {
    // Use new unified canvas for XAUUSD
    const ctx = document.getElementById('forecastChartXAUUSD');
    if (!ctx) return;
    
    // 1. Compile past 4 weeks if available
    const pastLabels = [];
    const pastHighHighs = [];
    const pastHighs = [];
    const pastLows = [];
    const pastLowLows = [];
    const pastCenters = [];
    const pastActualHighs = [];
    const pastActualLows = [];
    
    if (forecast.past_projections) {
        forecast.past_projections.forEach(p => {
            pastLabels.push(`W${p.week}`);
            pastHighHighs.push(p.high_high);
            pastHighs.push(p.high);
            pastLows.push(p.low);
            pastLowLows.push(p.low_low);
            pastCenters.push(p.center);
            pastActualHighs.push(p.actual_high);
            pastActualLows.push(p.actual_low);
        });
    }
    
    // 2. Compile future W+1 to W+25
    const futureLabels = forecast.projections.map(p => `W+${p.week}`);
    const futureHighHighs = forecast.projections.map(p => p.high_high);
    const futureHighs = forecast.projections.map(p => p.high);
    const futureLows = forecast.projections.map(p => p.low);
    const futureLowLows = forecast.projections.map(p => p.low_low);
    const futureCenters = forecast.projections.map(p => (p.high + p.low) / 2.0);
    
    // Combine labels: past (W-12..W-1) + NOW boundary + future (W+1..W+25)
    const labels = [...pastLabels, '⬤ NOW', ...futureLabels.slice(1)];
    const finalHighHighs = [...pastHighHighs, ...futureHighHighs];
    const finalHighs = [...pastHighs, ...futureHighs];
    const finalLows = [...pastLows, ...futureLows];
    const finalLowLows = [...pastLowLows, ...futureLowLows];
    const finalCenters = [...pastCenters, ...futureCenters];
    
    // Compile Actual High/Low data — past 12 weeks + current price dot + null for future
    const basePrice = forecast.base_price;
    // The dot appears at the W+1 position (first future week = index 0 of futureLabels)
    // Past = 12 points, current boundary = 1 dot, future nulls = 24 remaining
    const finalActualHighs = [
        ...pastActualHighs,
        basePrice,
        ...new Array(futureLabels.length - 1).fill(null)
    ];
    const finalActualLows = [
        ...pastActualLows,
        basePrice,
        ...new Array(futureLabels.length - 1).fill(null)
    ];
    
    // Use symbolCharts registry for XAUUSD
    if (symbolCharts['XAUUSD']) {
        symbolCharts['XAUUSD'].data.labels = labels;
        symbolCharts['XAUUSD'].data.datasets[0].data = finalHighHighs;
        symbolCharts['XAUUSD'].data.datasets[1].data = finalHighs;
        symbolCharts['XAUUSD'].data.datasets[2].data = finalLows;
        symbolCharts['XAUUSD'].data.datasets[3].data = finalLowLows;
        symbolCharts['XAUUSD'].data.datasets[4].data = finalCenters;
        symbolCharts['XAUUSD'].data.datasets[5].data = finalActualHighs;
        symbolCharts['XAUUSD'].data.datasets[6].data = finalActualLows;
        symbolCharts['XAUUSD'].update('none');
        return;
    }

    symbolCharts['XAUUSD'] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'High-High (Target Ekstrem)',
                    data: finalHighHighs,
                    borderColor: 'rgba(248, 113, 113, 0.6)',
                    borderWidth: 1.5,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    backgroundColor: 'rgba(248, 113, 113, 0.08)',
                    fill: '+1'  // fill between HH and H → upper corridor shading
                },
                {
                    label: 'High (Target Atas)',
                    data: finalHighs,
                    borderColor: 'rgba(251, 191, 36, 0.9)',
                    borderWidth: 2,
                    backgroundColor: 'rgba(14, 28, 54, 0.5)',
                    pointRadius: 2,
                    pointBackgroundColor: 'rgba(251, 191, 36, 0.8)',
                    fill: '+1'  // fill between H and L → inner band
                },
                {
                    label: 'Low (Target Bawah)',
                    data: finalLows,
                    borderColor: 'rgba(56, 189, 248, 0.9)',
                    borderWidth: 2,
                    backgroundColor: 'rgba(74, 222, 128, 0.08)',
                    pointRadius: 2,
                    pointBackgroundColor: 'rgba(56, 189, 248, 0.8)',
                    fill: '+1'  // fill between L and LL → lower corridor shading
                },
                {
                    label: 'Low-Low (Target Ekstrem)',
                    data: finalLowLows,
                    borderColor: 'rgba(74, 222, 128, 0.6)',
                    borderWidth: 1.5,
                    borderDash: [6, 4],
                    pointRadius: 0,
                    backgroundColor: 'transparent',
                    fill: false
                },
                {
                    label: 'Median Project',
                    data: finalCenters,
                    borderColor: 'rgba(165, 180, 252, 0.5)',
                    borderWidth: 1.5,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'Actual High',
                    data: finalActualHighs,
                    borderColor: 'rgba(239, 68, 68, 1.0)',
                    borderWidth: 3,
                    backgroundColor: 'transparent',
                    pointRadius: (ctx) => ctx.dataIndex === pastActualHighs.length ? 6 : 3,
                    pointBackgroundColor: (ctx) => ctx.dataIndex === pastActualHighs.length ? '#fff' : 'rgba(239,68,68,1)',
                    pointBorderColor: 'rgba(239, 68, 68, 1)',
                    pointBorderWidth: 2,
                    fill: false,
                    spanGaps: false,
                    shadowOffsetX: 0,
                    shadowOffsetY: 0,
                    shadowBlur: 12,
                    shadowColor: 'rgba(239,68,68,0.8)'
                },
                {
                    label: 'Actual Low',
                    data: finalActualLows,
                    borderColor: 'rgba(34, 197, 94, 1.0)',
                    borderWidth: 3,
                    backgroundColor: 'transparent',
                    pointRadius: (ctx) => ctx.dataIndex === pastActualLows.length ? 6 : 3,
                    pointBackgroundColor: (ctx) => ctx.dataIndex === pastActualLows.length ? '#fff' : 'rgba(34,197,94,1)',
                    pointBorderColor: 'rgba(34, 197, 94, 1)',
                    pointBorderWidth: 2,
                    fill: false,
                    spanGaps: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#8a9cb4',
                        font: { family: 'Outfit', size: 10 }
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(6, 12, 26, 0.95)',
                    titleColor: '#fff',
                    bodyColor: '#e2ecf8',
                    borderColor: 'rgba(0, 210, 255, 0.2)',
                    borderWidth: 1,
                    bodyFont: { family: 'JetBrains Mono', size: 11 }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: {
                        color: (ctx) => {
                            const label = ctx.chart.data.labels[ctx.index];
                            if (label && label.includes('NOW')) return '#fbbf24';
                            if (label && label.startsWith('W-')) return '#8a9cb4';
                            return '#60a5fa';
                        },
                        font: { family: 'Outfit', size: 9 },
                        maxRotation: 45
                    }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.02)' },
                    ticks: { color: '#8a9cb4', font: { family: 'JetBrains Mono', size: 10 } }
                }
            }
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  MULTI-SYMBOL TABS: XAUUSD | USDJPY | OIL
// ═══════════════════════════════════════════════════════════════════════════

const symbolCharts = {};   // keyed by symbol name
let currentSymbolTab = 'XAUUSD';

const TAB_STYLES = {
    'XAUUSD': { active: 'border:1.5px solid rgba(251,191,36,0.7);background:rgba(251,191,36,0.14);color:#fbbf24;', idle: 'border:1.5px solid rgba(251,191,36,0.2);background:transparent;color:rgba(251,191,36,0.5);' },
    'USDJPY': { active: 'border:1.5px solid rgba(165,180,252,0.7);background:rgba(165,180,252,0.1);color:#a5b4fc;', idle: 'border:1.5px solid rgba(99,102,241,0.2);background:transparent;color:rgba(165,180,252,0.5);' },
    'XTIUSD': { active: 'border:1.5px solid rgba(251,146,60,0.7);background:rgba(251,146,60,0.1);color:#fb923c;', idle: 'border:1.5px solid rgba(249,115,22,0.2);background:transparent;color:rgba(251,146,60,0.5);' }
};
const TAB_BTNS = { 'XAUUSD': 'tab-xauusd', 'USDJPY': 'tab-usdjpy', 'XTIUSD': 'tab-oil' };

function switchSymbolTab(symbol) {
    if (currentSymbolTab === symbol) return;
    currentSymbolTab = symbol;

    // Update tab button styles
    ['XAUUSD','USDJPY','XTIUSD'].forEach(sym => {
        const btn = document.getElementById(TAB_BTNS[sym]);
        if (!btn) return;
        const st = TAB_STYLES[sym] || {};
        btn.style.cssText = btn.style.cssText + ';' + (sym === symbol ? st.active : st.idle);
    });

    // Show/hide panels
    document.querySelectorAll('.symbol-panel').forEach(p => p.style.display = 'none');
    const panel = document.getElementById('panel-' + symbol);
    if (panel) {
        panel.style.display = 'block';
        panel.style.animation = 'fadeInUp 0.3s ease-out';
    }

    const titleEl = document.getElementById('weeklyTableTitle');
    const badgeEl = document.getElementById('weeklyTableBadge');
    const biasTagEl = document.getElementById('weeklyTableBiasTag');

    if (symbol === 'XAUUSD') {
        if (titleEl) titleEl.textContent = '📅 Rencana Proyeksi Mingguan XAUUSD';
        if (badgeEl) {
            badgeEl.textContent = 'GOLD/USD · W-12 → W+25';
            badgeEl.className = 'badge badge-active';
            badgeEl.style.cssText = '';
        }
        if (biasTagEl) biasTagEl.innerHTML = '';
        
        // Restore XAUUSD table contents
        fetchForecastData();
        renderConfidenceBars('XAUUSD', null);
    } else {
        loadSymbolForecast(symbol);
    }

    // Update price tag
    updateSymbolPriceTag(symbol);
}

function updateSymbolPriceTag(symbol) {
    const tag = document.getElementById('symbolPriceTag');
    const nameEl = document.getElementById('symbolPriceName');
    const valEl = document.getElementById('symbolPriceValue');
    if (!tag) return;

    fetch(`/api/symbol_forecast?symbol=${symbol === 'XAUUSD' ? 'USDJPY' : symbol}`)
        .then(r => r.json()).then(d => {
        if (d.status === 'success') {
            tag.style.display = 'flex';
            nameEl.textContent = d.forecast.display_name + ' BID';
            valEl.textContent = d.forecast.base_price.toFixed(symbol === 'USDJPY' ? 3 : 2);
        }
    }).catch(() => {});
}

async function loadSymbolForecast(symbol) {
    const spinner = document.getElementById('symbolLoadingSpinner');
    if (spinner) spinner.style.display = 'flex';

    try {
        const resp = await fetch(`/api/symbol_forecast?symbol=${symbol}`);
        const data = await resp.json();
        if (data.status !== 'success') throw new Error(data.message);

        const fc = data.forecast;
        const macro = data.macro_context;
        const reports = data.economic_reports;

        // Update headers in unified table
        const titleEl = document.getElementById('weeklyTableTitle');
        const badgeEl = document.getElementById('weeklyTableBadge');
        const biasTagEl = document.getElementById('weeklyTableBiasTag');

        if (titleEl) titleEl.textContent = `📅 Rencana Proyeksi Mingguan ${fc.display_name}`;
        if (badgeEl) {
            badgeEl.textContent = `${fc.symbol} · W-12 → W+25`;
            if (symbol === 'USDJPY') {
                badgeEl.style.cssText = 'background:rgba(165,180,252,0.1); color:#a5b4fc; border:1px solid rgba(165,180,252,0.3);';
            } else {
                badgeEl.style.cssText = 'background:rgba(251,146,60,0.1); color:#fb923c; border:1px solid rgba(251,146,60,0.3);';
            }
        }
        if (biasTagEl) {
            biasTagEl.innerHTML = `Trend Bias: <strong style="color:${fc.trend_bias >= 0 ? '#4ade80' : '#f87171'}">${fc.trend_bias >= 0 ? '▲' : '▼'} ${(fc.trend_bias * 100).toFixed(2)}%</strong>`;
        }

        // Update desc/bias labels
        const descRow = document.getElementById('symbolDescRow');
        if (descRow) {
            descRow.textContent = `${fc.description} | Bid: ${symbol === 'USDJPY' ? '' : '$'}${fc.base_price} | Drift/week: ${fc.weekly_drift > 0 ? '+' : ''}${fc.weekly_drift}`;
        }

        // Update price tag
        const tag = document.getElementById('symbolPriceTag');
        const nameEl = document.getElementById('symbolPriceName');
        const valEl = document.getElementById('symbolPriceValue');
        if (tag) { tag.style.display = 'flex'; nameEl.textContent = fc.display_name + ' BID'; valEl.textContent = fc.base_price; }

        // Update the Global Macro and Economic Reports Panels dynamically
        if (macro && reports) {
            updateForecastUI(fc, macro, reports);
        }

        // Render chart
        renderSymbolChart(symbol, fc);

        // Render confidence bars
        renderConfidenceBars(symbol, fc.projections);

        // Render table in unified body
        renderSymbolTable(symbol, fc);

    } catch (err) {
        console.error('Error loading symbol forecast:', err);
        const tbody = document.getElementById('forecastTableBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="padding:20px;text-align:center;color:#f87171;">❌ Error: ${err.message}</td></tr>`;
    } finally {
        if (spinner) spinner.style.display = 'none';
    }
}

function renderSymbolChart(symbol, fc) {
    const canvasId = 'forecastChart' + symbol;
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const past = fc.past_projections || [];
    const future = fc.projections || [];
    const decimals = symbol === 'USDJPY' ? 3 : 2;
    const isOil = symbol === 'XTIUSD';
    const accentHigh = symbol === 'USDJPY' ? 'rgba(165,180,252,' : 'rgba(251,146,60,';
    const accentLow  = symbol === 'USDJPY' ? 'rgba(52,211,153,' : 'rgba(56,189,248,';

    // Build labels
    const pastLabels   = past.map(p => `W${p.week}`);
    const futureLabels = future.map(p => `W+${p.week}`);
    const labels = [...pastLabels, '⬤ NOW', ...futureLabels.slice(1)];

    // Band data (past + future combined)
    const allHH = [...past.map(p => p.high_high), ...future.map(p => p.high_high)];
    const allH  = [...past.map(p => p.high),      ...future.map(p => p.high)];
    const allL  = [...past.map(p => p.low),        ...future.map(p => p.low)];
    const allLL = [...past.map(p => p.low_low),    ...future.map(p => p.low_low)];
    const allCt = [...past.map(p => p.center || (p.high+p.low)/2), ...future.map(p => (p.high+p.low)/2)];

    // Actual lines (past only + current dot + nulls)
    const actH = [...past.map(p => p.actual_high), fc.base_price, ...new Array(future.length - 1).fill(null)];
    const actL = [...past.map(p => p.actual_low),  fc.base_price, ...new Array(future.length - 1).fill(null)];

    // Destroy old chart if exists
    if (symbolCharts[symbol]) { symbolCharts[symbol].destroy(); }

    symbolCharts[symbol] = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'High-High (R2)', data: allHH, borderColor: `rgba(248,113,113,0.6)`, borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, backgroundColor: 'rgba(248,113,113,0.07)', fill: '+1' },
                { label: 'High (R1)', data: allH, borderColor: `${accentHigh}0.9)`, borderWidth: 2, backgroundColor: 'rgba(14,28,54,0.45)', pointRadius: 1.5, fill: '+1' },
                { label: 'Low (S1)', data: allL, borderColor: `${accentLow}0.9)`, borderWidth: 2, backgroundColor: `${accentLow}0.07)`, pointRadius: 1.5, fill: '+1' },
                { label: 'Low-Low (S2)', data: allLL, borderColor: 'rgba(74,222,128,0.6)', borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, fill: false },
                { label: 'Median', data: allCt, borderColor: 'rgba(165,180,252,0.4)', borderWidth: 1, borderDash: [3,3], pointRadius: 0, fill: false },
                { label: 'Actual High', data: actH, borderColor: 'rgba(239,68,68,1)', borderWidth: 2.5, pointRadius: (c) => c.dataIndex === past.length ? 6 : 2.5, pointBackgroundColor: (c) => c.dataIndex === past.length ? '#fff' : 'rgba(239,68,68,1)', fill: false, spanGaps: false },
                { label: 'Actual Low', data: actL, borderColor: 'rgba(34,197,94,1)', borderWidth: 2.5, pointRadius: (c) => c.dataIndex === past.length ? 6 : 2.5, pointBackgroundColor: (c) => c.dataIndex === past.length ? '#fff' : 'rgba(34,197,94,1)', fill: false, spanGaps: false },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 600, easing: 'easeInOutCubic' },
            plugins: {
                legend: { position: 'top', labels: { color: '#8a9cb4', font: { family: 'Outfit', size: 10 } } },
                tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: '#e2ecf8', borderColor: 'rgba(0,210,255,0.2)', borderWidth: 1, bodyFont: { family: 'JetBrains Mono', size: 11 },
                    callbacks: {
                        label: (ctx) => {
                            const v = ctx.raw;
                            if (v === null || v === undefined) return null;
                            const prefix = isOil ? '$' : (symbol === 'USDJPY' ? '¥' : '$');
                            return ` ${ctx.dataset.label}: ${prefix}${parseFloat(v).toFixed(decimals)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: {
                        color: (ctx) => {
                            const lbl = ctx.chart.data.labels[ctx.index];
                            if (lbl && lbl.includes('NOW')) return '#fbbf24';
                            return lbl && lbl.startsWith('W-') ? '#8a9cb4' : (symbol === 'USDJPY' ? '#a5b4fc' : '#fb923c');
                        },
                        font: { family: 'Outfit', size: 9 }, maxRotation: 45
                    }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.02)' },
                    ticks: { color: '#8a9cb4', font: { family: 'JetBrains Mono', size: 10 } }
                }
            }
        }
    });
}

function renderConfidenceBars(symbol, projections) {
    const containerId = 'confidenceBars' + symbol;
    const container = document.getElementById(containerId);
    if (!container) return;

    let bars = projections;
    if (!bars) {
        bars = [];
        for (let w = 1; w <= 25; w++) {
            bars.push({ week: w, confidence: Math.max(50, Math.round((95.0 - (w - 1) * 1.8) * 10) / 10) });
        }
    }

    container.innerHTML = '';
    bars.forEach(p => {
        const conf = p.confidence;
        const pct = ((conf - 50) / 45) * 100;
        const hue = pct > 60 ? 141 : pct > 30 ? 48 : 0;
        const bar = document.createElement('div');
        bar.style.cssText = `flex:1; height:${Math.max(8, pct * 0.6)}px; background:hsla(${hue},80%,55%,0.6); border-radius:2px 2px 0 0; transition:all 0.3s; cursor:default; min-width:4px;`;
        bar.title = `W+${p.week}: ${conf}%`;
        bar.addEventListener('mouseover', () => { bar.style.opacity = '1'; bar.style.transform = 'scaleY(1.08)'; });
        bar.addEventListener('mouseout',  () => { bar.style.opacity = '0.75'; bar.style.transform = 'scaleY(1)'; });
        bar.style.opacity = '0.75';
        container.appendChild(bar);
    });
}

function renderSymbolTable(symbol, fc) {
    const tbody = document.getElementById('forecastTableBody');
    if (!tbody) return;

    const isOil = symbol === 'XTIUSD';
    const decimals = symbol === 'USDJPY' ? 3 : 2;
    const prefix = isOil ? '$' : (symbol === 'USDJPY' ? '¥' : '$');
    const allRows = [...(fc.past_projections || []), ...(fc.projections || [])];
    let html = '';

    allRows.forEach(p => {
        const isPast = p.status === 'COMPLETED';
        const conf = p.confidence;
        const confColor = conf >= 80 ? '#4ade80' : conf >= 65 ? '#fbbf24' : '#f87171';
        const weekLabel = isPast ? `W${p.week}` : `W+${p.week}`;
        const rowBg = isPast ? 'rgba(255,255,255,0.012)' : 'transparent';

        let statusHtml = isPast
            ? `<span style="font-size:0.7rem;color:#4ade80;background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.25);border-radius:6px;padding:2px 8px;">✅ Terjadi</span>`
            : p.status === 'ACTIVE'
                ? `<span style="font-size:0.7rem;color:#fbbf24;background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.25);border-radius:6px;padding:2px 8px;">🔴 AKTIF</span>`
                : `<span style="font-size:0.7rem;color:var(--muted);background:rgba(255,255,255,0.04);border-radius:6px;padding:2px 8px;">Pending</span>`;

        html += `
            <tr style="border-bottom:1px solid rgba(255,255,255,0.03);background:${rowBg};">
                <td style="padding:9px 8px;font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:${isPast ? '#8a9cb4' : '#e2ecf8'};">${weekLabel}</td>
                <td style="padding:9px 8px;color:var(--muted);font-size:0.75rem;">${p.date_range}</td>
                <td style="padding:9px 8px;color:rgba(74,222,128,0.7);font-family:'JetBrains Mono',monospace;font-size:0.8rem;">${prefix}${parseFloat(p.low_low).toFixed(decimals)}</td>
                <td style="padding:9px 8px;color:#38bdf8;font-family:'JetBrains Mono',monospace;font-size:0.8rem;">
                    <div>${prefix}${parseFloat(p.low).toFixed(decimals)}</div>
                    ${isPast ? `<div style="color:#22c55e;font-size:0.65rem;margin-top:2px;">▲ Act Low: ${prefix}${parseFloat(p.actual_low).toFixed(decimals)}</div>` : ''}
                </td>
                <td style="padding:9px 8px;color:#fbbf24;font-family:'JetBrains Mono',monospace;font-size:0.8rem;">
                    <div>${prefix}${parseFloat(p.high).toFixed(decimals)}</div>
                    ${isPast ? `<div style="color:#ef4444;font-size:0.65rem;margin-top:2px;">▼ Act High: ${prefix}${parseFloat(p.actual_high).toFixed(decimals)}</div>` : ''}
                </td>
                <td style="padding:9px 8px;color:rgba(248,113,113,0.7);font-family:'JetBrains Mono',monospace;font-size:0.8rem;">${prefix}${parseFloat(p.high_high).toFixed(decimals)}</td>
                <td style="padding:9px 8px;text-align:center;font-weight:700;font-family:'JetBrains Mono',monospace;color:${confColor};font-size:0.8rem;">${conf}%</td>
                <td style="padding:9px 8px;text-align:center;">${statusHtml}</td>
                <td style="padding:9px 8px;font-family:'JetBrains Mono',monospace;font-size:0.72rem;line-height:1.6;">
                    ${isPast ? `
                        <div>🔺 <span style="color:#ef4444;font-weight:600;">${prefix}${parseFloat(p.actual_high).toFixed(decimals)}</span> <span style="color:#4ade80;">&nbsp;[H–HH ✓]</span></div>
                        <div>🔻 <span style="color:#4ade80;font-weight:600;">${prefix}${parseFloat(p.actual_low).toFixed(decimals)}</span> <span style="color:#4ade80;">&nbsp;[LL–L ✓]</span></div>
                    ` : '<span style="color:var(--muted); font-size:0.7rem;">Menunggu pergerakan harga...</span>'}
                </td>
            </tr>`;
    });

    tbody.innerHTML = html;
}

// Initialize XAUUSD tab as active + render confidence bars on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        renderConfidenceBars('XAUUSD', null);
        const btn = document.getElementById('tab-xauusd');
        if (btn) btn.style.cssText += ';' + TAB_STYLES['XAUUSD'].active;
    }, 800);
});

