let activeSymbol = 'XAUUSD';
let activeHorizon = 'D+1';
let forecastData = null;

document.addEventListener("DOMContentLoaded", () => {
    // Initial data load
    loadForecastData();
    
    // Setup symbol tabs
    renderSymbolPills();
    
    // Auto poll updates every 5 seconds
    setInterval(loadForecastData, 5000);
});

function renderSymbolPills() {
    const container = document.getElementById("v32-symbol-pills");
    if (!container) return;
    
    const symbols = ['XAUUSD', 'USDJPY', 'WTI OIL', 'EURUSD', 'GBPUSD'];
    let html = '';
    symbols.forEach(sym => {
        const isActive = sym === activeSymbol;
        const activeStyle = isActive 
            ? 'background: var(--neon-blue); color: #02060e; border-color: var(--neon-blue); font-weight: bold; box-shadow: 0 0 10px rgba(0, 210, 255, 0.3);' 
            : 'background: transparent; color: #a5b4fc; border-color: rgba(165,180,252,0.2); cursor: pointer;';
        
        html += `
            <button onclick="switchSymbol('${sym}')" style="padding: 8px 18px; border-radius: 20px; border: 1.5px solid; font-family:'Outfit', sans-serif; font-size: 0.8rem; transition: all 0.3s; ${activeStyle}">
                ${sym}
            </button>
        `;
    });
    container.innerHTML = html;
}

window.switchSymbol = function(sym) {
    activeSymbol = sym;
    renderSymbolPills();
    updateUI();
};

window.switchHorizon = function(horizon) {
    activeHorizon = horizon;
    
    // Toggle active classes
    const btnD = document.getElementById("hor-D");
    const btnW = document.getElementById("hor-W");
    if (horizon === 'D+1') {
        btnD.classList.add('active');
        btnW.classList.remove('active');
    } else {
        btnW.classList.add('active');
        btnD.classList.remove('active');
    }
    
    updateUI();
};

async function loadForecastData() {
    try {
        const res = await fetch('/api/xedy_v32_forecast');
        const data = await res.json();
        if (data.status === 'success') {
            forecastData = data.forecast;
            updateUI();
        }
        updateBacktestNavStatus(data.backtest_running);
    } catch (err) {
        console.error("Error loading forecast v32 data:", err);
    }
}

function updateBacktestNavStatus(isRunning) {
    const link = document.querySelector('a[href="/backtest"]');
    if (!link) return;
    let dot = link.querySelector('.backtest-running-dot');
    if (isRunning) {
        if (!dot) {
            dot = document.createElement('span');
            dot.className = 'backtest-running-dot';
            dot.style.cssText = 'display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #10a37f; margin-left: 6px; box-shadow: 0 0 8px #10a37f; animation: pulse-running-dot 1.2s infinite; vertical-align: middle;';
            if (!document.getElementById('running-dot-style')) {
                const style = document.createElement('style');
                style.id = 'running-dot-style';
                style.innerHTML = `
                    @keyframes pulse-running-dot {
                        0% { opacity: 0.3; transform: scale(0.8); }
                        50% { opacity: 1; transform: scale(1.2); }
                        100% { opacity: 0.3; transform: scale(0.8); }
                    }
                `;
                document.head.appendChild(style);
            }
            link.appendChild(dot);
        }
    } else {
        if (dot) dot.remove();
    }
}

function updateUI() {
    if (!forecastData || !forecastData.assets || !forecastData.assets[activeSymbol]) return;
    
    const assetData = forecastData.assets[activeSymbol][activeHorizon];
    if (!assetData) return;
    
    // Currency configuration
    const currency = activeSymbol === 'USDJPY' ? '¥' : '$';
    const dec = activeSymbol === 'USDJPY' ? 3 : 2;
    
    // Base details
    document.getElementById('v32-base-price').innerText = `${currency}${assetData.base_price.toFixed(dec)}`;
    document.getElementById('v32-error-band').innerText = assetData.error_band;
    document.getElementById('v32-atr').innerText = assetData.expected_range_atr;
    document.getElementById('v32-calc-time').innerText = forecastData.calculated_at;
    
    // Regime & Sessions
    document.getElementById('regime-badge').innerText = assetData.market_regime;
    if (assetData.market_regime.includes('BULLISH')) {
        document.getElementById('regime-badge').className = 'badge badge-hit-ll';
        document.getElementById('regime-badge').style.cssText = 'background: rgba(74, 222, 128, 0.15); color: #4ade80; border-color: rgba(74, 222, 128, 0.3);';
    } else if (assetData.market_regime.includes('BEARISH')) {
        document.getElementById('regime-badge').className = 'badge badge-hit-hh';
        document.getElementById('regime-badge').style.cssText = 'background: rgba(248, 113, 113, 0.15); color: #f87171; border-color: rgba(248, 113, 113, 0.3);';
    } else {
        document.getElementById('regime-badge').className = 'badge badge-active';
        document.getElementById('regime-badge').style.cssText = 'background: rgba(0, 210, 255, 0.1); color: var(--neon-blue); border-color: rgba(0, 210, 255, 0.2);';
    }
    
    // OHLC Projection
    const ohlc = assetData.ohlc;
    document.getElementById('v32-open').innerText = `${currency}${ohlc.open}`;
    document.getElementById('v32-high').innerText = `${currency}${ohlc.high}`;
    document.getElementById('v32-low').innerText = `${currency}${ohlc.low}`;
    document.getElementById('v32-close').innerText = `${currency}${ohlc.close}`;
    
    // Confidence intervals
    document.getElementById('v32-ci80').innerText = assetData.confidence_intervals.ci_80;
    document.getElementById('v32-ci95').innerText = assetData.confidence_intervals.ci_95;
    
    // ICI & FQI Scores
    document.getElementById('v32-ici').innerText = `${assetData.indexes.ici}%`;
    document.getElementById('v32-fqi').innerText = `${assetData.indexes.fqi}%`;
    
    // Sub-Pillars
    document.getElementById('v32-score-macro').innerText = `${assetData.scores.macro}%`;
    document.getElementById('v32-score-liq').innerText = `${assetData.scores.liquidity}%`;
    document.getElementById('v32-score-inter').innerText = `${assetData.scores.intermarket}%`;
    document.getElementById('v32-score-fund').innerText = `${assetData.scores.fundamental}%`;
    
    // Decision Gate Card
    const dg = assetData.decision_gate;
    const gateCard = document.getElementById('decision-gate-card');
    const gateIcon = document.getElementById('decision-gate-icon');
    const gateStatus = document.getElementById('v32-gate-status');
    const gateReason = document.getElementById('v32-gate-reason');
    
    if (dg.status === 'APPROVED') {
        gateCard.className = 'gate-card';
        gateIcon.className = 'gate-indicator';
        gateIcon.innerText = '✓';
        gateStatus.innerText = 'APPROVED & VALIDATED';
        gateStatus.style.color = 'var(--neon-green)';
        gateReason.innerText = dg.reason;
    } else {
        gateCard.className = 'gate-card hold';
        gateIcon.className = 'gate-indicator hold';
        gateIcon.innerText = '⚠';
        gateStatus.innerText = 'HOLD / AWAIT SIGNAL';
        gateStatus.style.color = 'var(--neon-red)';
        gateReason.innerText = dg.reason;
    }
    
    // Scenario Targets
    const sc = assetData.scenarios;
    document.getElementById('v32-scenario-bull-target').innerText = `${currency}${sc.bullish.target}`;
    document.getElementById('v32-scenario-bull-prob').innerText = `PROB: ${sc.bullish.probability}`;
    
    document.getElementById('v32-scenario-neu-target').innerText = `${currency}${sc.neutral.target}`;
    document.getElementById('v32-scenario-neu-prob').innerText = `PROB: ${sc.neutral.probability}`;
    
    document.getElementById('v32-scenario-bear-target').innerText = `${currency}${sc.bearish.target}`;
    document.getElementById('v32-scenario-bear-prob').innerText = `PROB: ${sc.bearish.probability}`;
    
    document.getElementById('v32-max-dd').innerText = `${currency}${assetData.expected_drawdown}`;
    document.getElementById('v32-max-rally').innerText = `${currency}${assetData.expected_rally}`;
    
    // Top 10 matches Table
    document.getElementById('v32-match-overall-score').innerText = `OVERALL SIMILARITY: ${assetData.similarity.overall_score}`;
    const top10Container = document.getElementById('v32-top10-body');
    let t10Html = '';
    assetData.similarity.top_10.forEach((m, idx) => {
        const cls = m.outcome === 'UP' ? 'text-green' : 'text-red';
        const symbol = m.outcome === 'UP' ? '▲' : '▼';
        t10Html += `
            <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="padding:6px 4px; color:var(--text-muted);">#${idx + 1}</td>
                <td style="padding:6px 4px; font-weight:500; color:#fff;">${m.date}</td>
                <td style="padding:6px 4px; text-align:center; color:var(--text-cyan);">${m.similarity_score}</td>
                <td style="padding:6px 4px; text-align:center;"><span class="${cls}">${symbol} ${m.outcome}</span></td>
                <td style="padding:6px 4px; text-align:right; font-weight:bold;" class="${cls}">${m.close_delta}</td>
            </tr>
        `;
    });
    top10Container.innerHTML = t10Html;
    
    // Explainable AI consensus factors
    const xaiContainer = document.getElementById('v32-xai-factors');
    let xaiHtml = '';
    assetData.explainable_ai.forEach(f => {
        const isNeg = f.weight.startsWith('-');
        const cls = isNeg ? 'text-red' : 'text-green';
        xaiHtml += `
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.03); padding-bottom:3px;">
                <span style="color:#fff;">• ${f.factor}</span>
                <strong class="${cls}">${f.weight}</strong>
            </div>
        `;
    });
    xaiContainer.innerHTML = xaiHtml;
}
