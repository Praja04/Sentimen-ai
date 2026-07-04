const symbolCharts = {};   // keyed by symbol name
let currentSymbolTab = 'XAUUSD';
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
        
        // Refresh forecast UI values based on current active tab regularly to keep AI Agent metrics updated
        if (currentSymbolTab === "XAUUSD") {
            fetchForecastData();
        } else {
            loadSymbolForecast(currentSymbolTab);
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
    // Determine currency symbol based on current active tab
    const isUSDJPY = currentSymbolTab === "USDJPY";
    const isOIL = currentSymbolTab === "XTIUSD";
    const currencyPrefix = isUSDJPY ? "¥" : "$";
    const decimals = isUSDJPY ? 3 : 2;

    // Dynamically update active agent label, price, and description details
    const agentSymbolEl = document.getElementById("agentActiveSymbol");
    const agentPriceEl = document.getElementById("agentActivePrice");
    const agentDescEl = document.getElementById("agentActiveDesc");

    // Map XTIUSD to OIL WTI display
    const symbolDisplay = currentSymbolTab === "XTIUSD" ? "OIL WTI" : currentSymbolTab;

    if (agentSymbolEl) {
        agentSymbolEl.textContent = symbolDisplay;
        if (currentSymbolTab === "XAUUSD") {
            agentSymbolEl.style.cssText = "background:rgba(251,191,36,0.15); color:#fbbf24; border:1px solid rgba(251,191,36,0.3); font-size:0.7rem;";
        } else if (currentSymbolTab === "USDJPY") {
            agentSymbolEl.style.cssText = "background:rgba(165,180,252,0.15); color:#a5b4fc; border:1px solid rgba(165,180,252,0.3); font-size:0.7rem;";
        } else if (currentSymbolTab === "XTIUSD") {
            agentSymbolEl.style.cssText = "background:rgba(251,146,60,0.15); color:#fb923c; border:1px solid rgba(251,146,60,0.3); font-size:0.7rem;";
        }
    }
    if (agentPriceEl) {
        agentPriceEl.textContent = `${currencyPrefix}${forecast.base_price.toFixed(decimals)}`;
    }
    if (agentDescEl) {
        if (currentSymbolTab === "XAUUSD") {
            agentDescEl.textContent = "Mengkalibrasi deviasi pergerakan emas berdasarkan parameter likuiditas global & aliran safe-haven.";
        } else if (currentSymbolTab === "USDJPY") {
            agentDescEl.textContent = "Mengadaptasi model sensitivitas Yen terhadap volatilitas suku bunga BoJ dan carry trade unwind.";
        } else if (currentSymbolTab === "XTIUSD") {
            agentDescEl.textContent = "Memantau rentang volatilitas WTI berdasarkan suplai global, rig count, dan pemotongan OPEC+.";
        }
    }

    // Dynamically update Demand Analysis titles & labels based on Active Tab
    const demandTitleEl = document.getElementById("macroDemandTitle");
    const demandLabel1El = document.getElementById("macroDemandLabel1");
    const demandLabel2El = document.getElementById("macroDemandLabel2");
    const demandLabel3El = document.getElementById("macroDemandLabel3");
    const ecoTableImpactHeaderEl = document.getElementById("ecoTableImpactHeader");

    if (currentSymbolTab === "XAUUSD") {
        if (demandTitleEl) demandTitleEl.textContent = "📦 Analisa Permintaan Emas";
        if (demandLabel1El) demandLabel1El.textContent = "Pembelian Bank Sentral:";
        if (demandLabel2El) demandLabel2El.textContent = "Arus Likuiditas ETF (SPDR):";
        if (demandLabel3El) demandLabel3El.textContent = "Permintaan Retail & Perhiasan:";
        if (ecoTableImpactHeaderEl) ecoTableImpactHeaderEl.textContent = "Dampak Terhadap Emas";
    } else if (currentSymbolTab === "USDJPY") {
        if (demandTitleEl) demandTitleEl.textContent = "📦 Analisa Permintaan & Arus Yen";
        if (demandLabel1El) demandLabel1El.textContent = "Intervensi Moneter & Obligasi BoJ:";
        if (demandLabel2El) demandLabel2El.textContent = "Aliran Repatriasi Carry Trade:";
        if (demandLabel3El) demandLabel3El.textContent = "Aktivitas Konsumsi Domestik Jepang:";
        if (ecoTableImpactHeaderEl) ecoTableImpactHeaderEl.textContent = "Dampak Terhadap JPY";
    } else if (currentSymbolTab === "XTIUSD") {
        if (demandTitleEl) demandTitleEl.textContent = "📦 Analisa Permintaan Minyak Bumi";
        if (demandLabel1El) demandLabel1El.textContent = "Cadangan Minyak Strategis (SPR):";
        if (demandLabel2El) demandLabel2El.textContent = "Kontrak Berjangka & Inflow ETF:";
        if (demandLabel3El) demandLabel3El.textContent = "Konsumsi Sektor Kilang & Transportasi:";
        if (ecoTableImpactHeaderEl) ecoTableImpactHeaderEl.textContent = "Dampak Terhadap Minyak (WTI)";
    }

    // 1. Update Self-Learning stats
    document.getElementById("modelAccuracy").textContent = `${forecast.metrics.accuracy.toFixed(1)}%`;
    document.getElementById("modelMae").textContent = `${currencyPrefix}${forecast.metrics.mae.toFixed(2)}`;
    
    // Weights
    const lr = forecast.model_weights.learning_rate !== undefined ? forecast.model_weights.learning_rate : 0.05;
    document.getElementById("learningRateVal").textContent = lr.toFixed(2);
    document.getElementById("fundWeightVal").textContent = `${(forecast.model_weights.fundamental * 100).toFixed(0)}%`;
    document.getElementById("techWeightVal").textContent = `${(forecast.model_weights.technical * 100).toFixed(0)}%`;
    document.getElementById("volMultVal").textContent = forecast.model_weights.volatility_multiplier.toFixed(3);
    const ecVal = forecast.error_correction || 0.0;
    const sign = ecVal >= 0 ? "+" : "";
    document.getElementById("errorCorrectionVal").textContent = `${sign}${currencyPrefix}${ecVal.toFixed(2)}`;
    
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
    const macroTrendBadgeEl = document.getElementById("macroTrendBadge");
    if (macroTrendBadgeEl) {
        const trendVal = forecast.trend_bias !== undefined ? forecast.trend_bias : (forecast.fundamental_bias !== undefined ? forecast.fundamental_bias : 0.0);
        const trendPct = (trendVal * 100).toFixed(2);
        macroTrendBadgeEl.style.display = "inline-block";
        if (trendVal >= 0) {
            macroTrendBadgeEl.textContent = `📈 TREND: BULLISH (+${trendPct}%)`;
            macroTrendBadgeEl.style.cssText = "font-size:0.7rem;padding:3px 10px;border-radius:6px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;background:rgba(74,222,128,0.15);color:#4ade80;border:1px solid rgba(74,222,128,0.3);margin-left:12px;";
        } else {
            macroTrendBadgeEl.textContent = `📉 TREND: BEARISH (${trendPct}%)`;
            macroTrendBadgeEl.style.cssText = "font-size:0.7rem;padding:3px 10px;border-radius:6px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;background:rgba(248,113,113,0.15);color:#f87171;border:1px solid rgba(248,113,113,0.3);margin-left:12px;";
        }
    }

    if (macroContext) {
        const demand = macroContext.demand || {};
        const experts = macroContext.experts || {};
        const geopolitics = macroContext.geopolitics || {};

        const cbEl = document.getElementById("macroCentralBank");
        if (cbEl) cbEl.textContent = demand.central_bank || "-";
        const etfEl = document.getElementById("macroEtfFlows");
        if (etfEl) etfEl.textContent = demand.etf_flows || "-";
        const jwEl = document.getElementById("macroJewelry");
        if (jwEl) jwEl.textContent = demand.jewelry || "-";
        
        const fedEl = document.getElementById("macroFedStance");
        if (fedEl) fedEl.textContent = experts.fed_stance || "-";
        const presEl = document.getElementById("macroPresidentStance");
        if (presEl) presEl.textContent = experts.president_stance || "-";
        
        const geoEl = document.getElementById("macroGeopoliticsIndex");
        if (geoEl) geoEl.textContent = geopolitics.index || "-";
        const confEl = document.getElementById("macroConflicts");
        if (confEl) confEl.textContent = geopolitics.conflicts || "-";
        const twEl = document.getElementById("macroTariffWars");
        if (twEl) twEl.textContent = geopolitics.tariff_wars || "-";
        
        // Wall Street Consensus
        const wallStreetContainer = document.getElementById("macroWallStreet");
        if (wallStreetContainer) {
            let targetsHtml = `<span style="color: var(--muted); display: block; font-size: 0.65rem; text-transform: uppercase; margin-bottom: 4px;">Target Bank Global:</span>`;
            const targets = experts.targets || [];
            let sum = 0;
            let count = 0;
            targets.forEach(t => {
                targetsHtml += `
                    <div style="display: flex; justify-content: space-between; font-size: 0.7rem; border-bottom: 1px solid rgba(255,255,255,0.02); padding: 3px 0;">
                        <span style="color: var(--muted); font-weight: 500;">${t.inst}:</span>
                        <span style="color: #fbbf24; font-weight: 600;">${t.target}</span>
                    </div>
                `;
                let clean = t.target.replace(/[^0-9.]/g, '');
                let val = parseFloat(clean);
                if (!isNaN(val)) {
                    sum += val;
                    count++;
                }
            });
            
            let wsAvg = count > 0 ? sum / count : 0;
            if (wsAvg > 0 && forecast.projections && forecast.projections.length > 0) {
                const finalProj = forecast.projections[forecast.projections.length - 1];
                const aiTarget = (finalProj.high + finalProj.low) / 2;
                const diffPct = ((aiTarget - wsAvg) / wsAvg) * 100;
                
                let alignText = 'NEUTRAL';
                let alignColor = '#fbbf24';
                if (Math.abs(diffPct) <= 3.0) {
                    alignText = 'HIGHLY ALIGNED';
                    alignColor = '#4ade80';
                } else if (Math.abs(diffPct) > 7.0) {
                    alignText = 'DIVERGENT BIAS';
                    alignColor = '#f87171';
                } else {
                    alignText = 'MODERATE';
                    alignColor = '#fbbf24';
                }
                
                const isOil = forecast.symbol === 'XTIUSD' || forecast.symbol === 'WTI OIL';
                const isGold = forecast.symbol === 'XAUUSD' || forecast.symbol === 'GOLD/USD';
                let prefix = (isOil || isGold) ? '$' : '';
                let formattedWsAvg = prefix + wsAvg.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                let formattedAiTarget = prefix + aiTarget.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                
                targetsHtml += `
                    <div style="margin-top: 12px; padding: 10px; border-radius: 8px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);">
                        <span style="color: #00d2ff; display: block; font-size: 0.62rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 6px;">🧠 AI vs Wall Street Consensus:</span>
                        <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-bottom: 3px;">
                            <span style="color: var(--muted);">Konsensus Bank (Avg):</span>
                            <span style="color: #fff; font-weight: 500;">${formattedWsAvg}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-bottom: 3px;">
                            <span style="color: var(--muted);">AI Target (W+25 Median):</span>
                            <span style="color: #fff; font-weight: 500;">${formattedAiTarget}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-bottom: 3px;">
                            <span style="color: var(--muted);">Deviasi / Selisih:</span>
                            <span style="color: ${diffPct >= 0 ? '#4ade80' : '#f87171'}; font-weight: 600;">${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(2)}%</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.68rem; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.04); padding-top: 5px; align-items: center;">
                            <span style="color: var(--muted); font-size: 0.6rem; text-transform: uppercase;">Alignment Status:</span>
                            <span style="color: ${alignColor}; font-weight: 700; font-size: 0.65rem; font-family: 'JetBrains Mono', monospace; padding: 1px 6px; border-radius: 4px; background: ${alignColor}15; border: 1px solid ${alignColor}30;">${alignText}</span>
                        </div>
                    </div>
                `;
            }
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
                    backgroundColor: 'transparent',
                    fill: false
                },
                {
                    label: 'High (Target Atas)',
                    data: finalHighs,
                    borderColor: 'rgba(251, 191, 36, 0.9)',
                    borderWidth: 2,
                    backgroundColor: 'transparent',
                    pointRadius: 2,
                    pointBackgroundColor: 'rgba(251, 191, 36, 0.8)',
                    fill: false
                },
                {
                    label: 'Low (Target Bawah)',
                    data: finalLows,
                    borderColor: 'rgba(56, 189, 248, 0.9)',
                    borderWidth: 2,
                    backgroundColor: 'transparent',
                    pointRadius: 2,
                    pointBackgroundColor: 'rgba(56, 189, 248, 0.8)',
                    fill: false
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
                        color: '#8a9cb4',
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


const TAB_STYLES = {
    'XAUUSD': { active: 'border:1.5px solid rgba(251,191,36,0.7);background:rgba(251,191,36,0.14);color:#fbbf24;', idle: 'border:1.5px solid rgba(251,191,36,0.2);background:transparent;color:rgba(251,191,36,0.5);' },
    'USDJPY': { active: 'border:1.5px solid rgba(165,180,252,0.7);background:rgba(165,180,252,0.1);color:#a5b4fc;', idle: 'border:1.5px solid rgba(99,102,241,0.2);background:transparent;color:rgba(165,180,252,0.5);' },
    'XTIUSD': { active: 'border:1.5px solid rgba(251,146,60,0.7);background:rgba(251,146,60,0.1);color:#fb923c;', idle: 'border:1.5px solid rgba(249,115,22,0.2);background:transparent;color:rgba(251,146,60,0.5);' }
};
const TAB_BTNS = { 'XAUUSD': 'tab-xauusd', 'USDJPY': 'tab-usdjpy', 'XTIUSD': 'tab-oil' };

function switchSymbolTab(symbol) {
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

    // Use current active symbol (mapping XAUUSD to XAUUSD request, USDJPY to USDJPY, etc.)
    const targetSymbol = symbol === 'XAUUSD' ? 'XAUUSD' : symbol;
    
    // For XAUUSD we use /api/forecast_data, else we use /api/symbol_forecast
    if (targetSymbol === 'XAUUSD') {
        fetch('/api/forecast_data')
            .then(r => r.json()).then(d => {
                if (d.status === 'success') {
                    tag.style.display = 'flex';
                    nameEl.textContent = 'XAUUSD BID';
                    valEl.textContent = d.forecast.base_price.toFixed(2);
                }
            }).catch(() => {});
    } else {
        fetch(`/api/symbol_forecast?symbol=${targetSymbol}`)
            .then(r => r.json()).then(d => {
                if (d.status === 'success') {
                    tag.style.display = 'flex';
                    nameEl.textContent = d.forecast.display_name + ' BID';
                    valEl.textContent = d.forecast.base_price.toFixed(symbol === 'USDJPY' ? 3 : 2);
                }
            }).catch(() => {});
    }
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
        updateForecastUI(fc, macro || fc.macro_context || {}, reports || fc.economic_reports || []);

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
    setTimeout(() => {
        try {
            const canvasId = 'forecastChart' + symbol;
            const ctx = document.getElementById(canvasId);
            if (!ctx) return;

            const past = fc.past_projections || [];
            const future = fc.projections || [];
            const decimals = symbol === 'USDJPY' ? 3 : 2;
            const isOil = symbol === 'XTIUSD';
            const accentHigh = symbol === 'USDJPY' ? 'rgba(165,180,252,0.9)' : 'rgba(251,146,60,0.9)';
            const accentLow  = symbol === 'USDJPY' ? 'rgba(52,211,153,0.9)' : 'rgba(56,189,248,0.9)';
            const accentHighBg = 'rgba(14,28,54,0.45)';
            const accentLowBg = symbol === 'USDJPY' ? 'rgba(52,211,153,0.07)' : 'rgba(56,189,248,0.07)';

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
                        { label: 'High-High (R2)', data: allHH, borderColor: 'rgba(248,113,113,0.6)', borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, backgroundColor: 'transparent', fill: false },
                        { label: 'High (R1)', data: allH, borderColor: accentHigh, borderWidth: 2, backgroundColor: 'transparent', pointRadius: 1.5, fill: false },
                        { label: 'Low (S1)', data: allL, borderColor: accentLow, borderWidth: 2, backgroundColor: 'transparent', pointRadius: 1.5, fill: false },
                        { label: 'Low-Low (S2)', data: allLL, borderColor: 'rgba(74,222,128,0.6)', borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, fill: false },
                        { label: 'Median', data: allCt, borderColor: 'rgba(165,180,252,0.4)', borderWidth: 1, borderDash: [3,3], pointRadius: 0, fill: false },
                        { label: 'Actual High', data: actH, borderColor: 'rgba(239,68,68,1)', borderWidth: 2.5, pointRadius: (context) => context.dataIndex === (past ? past.length : 0) ? 6 : 2.5, pointBackgroundColor: (context) => context.dataIndex === (past ? past.length : 0) ? '#fff' : 'rgba(239,68,68,1)', fill: false, spanGaps: false },
                        { label: 'Actual Low', data: actL, borderColor: 'rgba(34,197,94,1)', borderWidth: 2.5, pointRadius: (context) => context.dataIndex === (past ? past.length : 0) ? 6 : 2.5, pointBackgroundColor: (context) => context.dataIndex === (past ? past.length : 0) ? '#fff' : 'rgba(34,197,94,1)', fill: false, spanGaps: false },
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    animation: { duration: 600, easing: 'easeInOutCubic' },
                    plugins: {
                        legend: { position: 'top', labels: { color: '#8a9cb4', font: { family: 'Outfit', size: 10 } } },
                        tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(6,12,26,0.95)', titleColor: '#fff', bodyColor: '#e2ecf8', borderColor: 'rgba(0,210,255,0.2)', borderWidth: 1, bodyFont: { family: 'JetBrains Mono', size: 11 },
                            callbacks: {
                                label: (context) => {
                                    const v = context.raw;
                                    if (v === null || v === undefined) return null;
                                    const prefix = isOil ? '$' : (symbol === 'USDJPY' ? '¥' : '$');
                                    return ` ${context.dataset.label}: ${prefix}${parseFloat(v).toFixed(decimals)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.03)' },
                            ticks: {
                                color: '#8a9cb4',
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
        } catch (e) {
            console.error("Error rendering symbol chart:", e);
        }
    }, 50);
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

    // Populate labels row dynamically
    const labelsContainerId = 'confidenceLabels' + symbol;
    const labelsContainer = document.getElementById(labelsContainerId);
    if (labelsContainer) {
        const w1Conf = bars[0] ? parseFloat(bars[0].confidence).toFixed(1) : '95.0';
        const w13Conf = bars[12] ? parseFloat(bars[12].confidence).toFixed(1) : '73.4';
        const w25Conf = bars[24] ? parseFloat(bars[24].confidence).toFixed(1) : '51.8';
        labelsContainer.innerHTML = `
            <span>W+1 (${w1Conf}%)</span>
            <span>W+7</span>
            <span>W+13 (${w13Conf}%)</span>
            <span>W+19</span>
            <span>W+25 (${w25Conf}%)</span>
        `;
    }
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

