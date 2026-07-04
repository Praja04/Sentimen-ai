let forecastChart = null;

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
            updateForecastUI(data.forecast, data.macro_context, data.economic_reports);
            renderForecastChart(data.forecast);
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
        // If there's active demo state, we can also refresh forecast parameters
        if (data.demo) {
            // Re-fetch forecast variables to keep logs and hit states animated
            fetchForecastData();
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
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); hover: background: rgba(255,255,255,0.01);">
                    <td style="padding: 10px 8px; font-weight: 600; color: #fff;">M${p.week}</td>
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
    const ctx = document.getElementById("forecastChart");
    if (!ctx) return;
    
    // Extract datasets
    const labels = forecast.projections.map(p => `Minggu ${p.week}`);
    const lowLows = forecast.projections.map(p => p.low_low);
    const lows = forecast.projections.map(p => p.low);
    const highs = forecast.projections.map(p => p.high);
    const highHighs = forecast.projections.map(p => p.high_high);
    const centers = forecast.projections.map(p => (p.high + p.low) / 2.0);
    
    const basePrice = forecast.base_price;
    const actualData = new Array(labels.length).fill(null);
    actualData[0] = basePrice; // Start actual line from base price
    
    // Draw running actual ticks if we have hit events showing recent price ticks
    // For visual simulation, we can draw a slight line tracking recent prices
    
    if (forecastChart) {
        // Just update values and update chart to avoid flickering
        forecastChart.data.datasets[0].data = highHighs;
        forecastChart.data.datasets[1].data = highs;
        forecastChart.data.datasets[2].data = lows;
        forecastChart.data.datasets[3].data = lowLows;
        forecastChart.data.datasets[4].data = centers;
        forecastChart.update('none'); // silent update
        return;
    }
    
    forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'High-High (Target Ekstrem)',
                    data: highHighs,
                    borderColor: 'rgba(248, 113, 113, 0.4)',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'High (Target Atas)',
                    data: highs,
                    borderColor: 'rgba(251, 191, 36, 0.8)',
                    borderWidth: 2,
                    backgroundColor: 'rgba(251, 191, 36, 0.05)',
                    pointRadius: 2,
                    fill: '+1' // fill up to High-High
                },
                {
                    label: 'Low (Target Bawah)',
                    data: lows,
                    borderColor: 'rgba(56, 189, 248, 0.8)',
                    borderWidth: 2,
                    backgroundColor: 'rgba(10, 20, 38, 0.4)',
                    pointRadius: 2,
                    fill: '-1' // fill down to Low-Low
                },
                {
                    label: 'Low-Low (Target Ekstrem)',
                    data: lowLows,
                    borderColor: 'rgba(74, 222, 128, 0.4)',
                    borderWidth: 1.5,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false
                },
                {
                    label: 'Median Project',
                    data: centers,
                    borderColor: 'rgba(0, 210, 255, 0.9)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false
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
                    grid: { color: 'rgba(255,255,255,0.02)' },
                    ticks: { color: '#8a9cb4', font: { family: 'Outfit', size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.02)' },
                    ticks: { color: '#8a9cb4', font: { family: 'JetBrains Mono', size: 10 } }
                }
            }
        }
    });
}
