document.addEventListener('DOMContentLoaded', () => {
    // Top Date/Time Update
    const sysDate = document.getElementById('sys-date');
    const sysTime = document.getElementById('sys-time');
    const sysUpdate = document.getElementById('sys-update');
    
    function updateTime() {
        const now = new Date();
        sysDate.innerText = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
        sysTime.innerText = now.toLocaleTimeString('en-GB', { hour12: false }) + ' WIB';
        sysUpdate.innerText = sysTime.innerText;
        
        // Update Global Times
        const options = { hour12: false, hour: '2-digit', minute: '2-digit' };
        
        const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
        document.getElementById('ny-time').innerText = nyTime.toLocaleTimeString('en-GB', options);
        let nyOpen = nyTime.getHours() >= 9 && nyTime.getHours() < 16;
        document.getElementById('ny-status').innerHTML = nyOpen ? '<span class="text-green">OPEN</span>' : '<span class="text-red">CLOSED</span>';
        
        const lonTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/London' }));
        document.getElementById('lon-time').innerText = lonTime.toLocaleTimeString('en-GB', options);
        let lonOpen = lonTime.getHours() >= 8 && lonTime.getHours() < 16;
        document.getElementById('lon-status').innerHTML = lonOpen ? '<span class="text-green">OPEN</span>' : '<span class="text-red">CLOSED</span>';
        
        const tokTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Tokyo' }));
        document.getElementById('tok-time').innerText = tokTime.toLocaleTimeString('en-GB', options);
        let tokOpen = tokTime.getHours() >= 9 && tokTime.getHours() < 15;
        document.getElementById('tok-status').innerHTML = tokOpen ? '<span class="text-green">OPEN</span>' : '<span class="text-red">CLOSED</span>';
        
        const sydTime = new Date(now.toLocaleString('en-US', { timeZone: 'Australia/Sydney' }));
        document.getElementById('syd-time').innerText = sydTime.toLocaleTimeString('en-GB', options);
        let sydOpen = sydTime.getHours() >= 10 && sydTime.getHours() < 16;
        document.getElementById('syd-status').innerHTML = sydOpen ? '<span class="text-green">OPEN</span>' : '<span class="text-red">CLOSED</span>';
    }
    setInterval(updateTime, 1000);
    updateTime();

    // FETCH DATA FROM BACKEND
    async function fetchXedyData() {
        try {
            // Add timestamp parameter and no-cache header to prevent aggressive browser caching
            const res = await fetch(`/api/xedy_v30?t=${new Date().getTime()}`, {
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            const data = await res.json();
            if(!data.error) {
                renderDashboard(data);
            }
        } catch (e) {
            console.error("Failed to load XEDY data", e);
        }
    }
    
    // 1-SECOND LIVE TICK TICKER
    async function fetchLiveTicks() {
        try {
            const res = await fetch(`/api/live_ticks?t=${new Date().getTime()}`, {
                cache: 'no-store',
                headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
            });
            const data = await res.json();
            if(!data.error && data.ticks) {
                for (const [symbol, tickInfo] of Object.entries(data.ticks)) {
                    const el = document.getElementById(`live-price-${symbol.replace(/\s+/g, '-')}`);
                    const decimals = symbol.includes('JPY') ? 3 : (symbol.includes('EUR') || symbol.includes('GBP') ? 4 : 2);
                    if (el) {
                        el.innerText = tickInfo.bid.toLocaleString('en-US', {
                            minimumFractionDigits: decimals,
                            maximumFractionDigits: decimals
                        });
                    }
                    
                    // Update detailed stats inside asset cards on homepage
                    const bidEl = document.getElementById(`live-bid-${symbol.replace(/\s+/g, '-')}`);
                    const askEl = document.getElementById(`live-ask-${symbol.replace(/\s+/g, '-')}`);
                    const chgEl = document.getElementById(`live-chg-${symbol.replace(/\s+/g, '-')}`);
                    const volEl = document.getElementById(`live-vol-${symbol.replace(/\s+/g, '-')}`);
                    
                    if (bidEl) bidEl.innerText = tickInfo.bid.toFixed(decimals);
                    if (askEl) askEl.innerText = tickInfo.ask.toFixed(decimals);
                    if (chgEl) {
                        const formattedChg = tickInfo.change >= 0 ? `+${tickInfo.change.toFixed(decimals)}%` : `${tickInfo.change.toFixed(decimals)}%`;
                        chgEl.innerText = formattedChg;
                        chgEl.className = tickInfo.change >= 0 ? 'text-green' : 'text-red';
                    }
                    if (volEl) volEl.innerText = tickInfo.volume.toLocaleString('en-US');
                }
                updateBacktestNavStatus(data.backtest_running);
            }
        } catch (e) {
            console.error("Fast tick fetch failed:", e);
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

    // LAGGARD ROTATION DETECTOR FETCH & RENDER
    async function fetchLaggardData() {
        try {
            const res = await fetch(`/api/laggard_detection?t=${new Date().getTime()}`, {
                cache: 'no-store',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });
            const data = await res.json();
            if (data.status === "success" && data.results) {
                const tbody = document.getElementById("laggard-table-body");
                if (tbody) {
                    tbody.innerHTML = "";
                    for (const [symbol, info] of Object.entries(data.results)) {
                        const isLaggard = symbol === data.laggard_leader;
                        const statusClass = info.gap < 0 ? "text-green" : "text-red";
                        const gapSign = info.gap >= 0 ? "+" : "";
                        const rowStyle = isLaggard ? "background: rgba(0, 210, 255, 0.05); font-weight: bold; border-left: 2px solid var(--text-cyan);" : "";
                        
                        const aiClass = info.ai_direction === "BULLISH" ? "text-green" : (info.ai_direction === "BEARISH" ? "text-red" : "text-yellow");
                        const confluenceClass = info.confluence === "MATCHED" ? "text-green" : "text-muted";
                        
                        // Action styling
                        let actionHtml = `<span class="text-muted">HOLD</span>`;
                        if (info.action === "BUY") {
                            actionHtml = `<span class="text-green" style="border: 1px solid var(--text-green); padding: 1px 6px; border-radius: 3px; background: rgba(0, 255, 0, 0.05); box-shadow: 0 0 5px rgba(0,255,0,0.15);">BUY</span>`;
                        } else if (info.action === "SELL") {
                            actionHtml = `<span class="text-red" style="border: 1px solid var(--text-red); padding: 1px 6px; border-radius: 3px; background: rgba(255, 0, 0, 0.05); box-shadow: 0 0 5px rgba(255,0,0,0.15);">SELL</span>`;
                        }
                        
                        tbody.innerHTML += `
                            <tr style="${rowStyle}">
                                <td>${isLaggard ? '⚡ ' : ''}${symbol}</td>
                                <td>${info.actual.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})}</td>
                                <td>${info.fair_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})}</td>
                                <td class="${statusClass}">${gapSign}${info.gap.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 4})} (${gapSign}${info.pct_gap}%)</td>
                                <td class="${aiClass}">${info.ai_direction}</td>
                                <td class="${confluenceClass}">${info.confluence}</td>
                            </tr>
                        `;
                    }
                }
                
                // Update footer / stats of laggard panel
                const leaderVal = document.getElementById("laggard-leader-val");
                const recVal = document.getElementById("laggard-recommendation-val");
                if (leaderVal) {
                    const leaderInfo = data.results[data.laggard_leader];
                    const leaderAction = leaderInfo ? leaderInfo.action : "HOLD";
                    leaderVal.innerText = `${data.laggard_leader} (${leaderInfo ? (leaderInfo.pct_gap >= 0 ? '+' : '') + leaderInfo.pct_gap : 0}%)`;
                    
                    if (recVal) {
                        if (leaderAction === "BUY") {
                            recVal.innerHTML = `<span class="text-green" style="text-shadow: 0 0 8px rgba(0,255,0,0.4);">⚡ OPPORTUNITY: BUY ${data.laggard_leader} (LAGGARD CONFLUENCE)</span>`;
                        } else if (leaderAction === "SELL") {
                            recVal.innerHTML = `<span class="text-red" style="text-shadow: 0 0 8px rgba(255,0,0,0.4);">⚡ OPPORTUNITY: SELL ${data.laggard_leader} (LAGGARD CONFLUENCE)</span>`;
                        } else {
                            recVal.innerHTML = `<span class="text-yellow">SIDEWAYS / AWAITING CONFLUENCE</span>`;
                        }
                    }
                }
                
                // Update asset cards on homepage
                for (const [symbol, info] of Object.entries(data.results)) {
                    const cleanSymbol = symbol.replace(/\s+/g, '-');
                    const fairEl = document.getElementById(`card-fair-value-${cleanSymbol}`);
                    const gapEl = document.getElementById(`card-gap-${cleanSymbol}`);
                    const aiEl = document.getElementById(`card-ai-dir-${cleanSymbol}`);
                    const btnContainer = document.getElementById(`card-action-btn-container-${cleanSymbol}`);
                    
                    const isJpy = symbol.includes('JPY');
                    const decimals = isJpy ? 3 : (symbol.includes('EUR') || symbol.includes('GBP') ? 4 : 2);
                    
                    if (fairEl) {
                        fairEl.innerText = info.fair_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: decimals});
                    }
                    if (gapEl) {
                        const gapSign = info.gap >= 0 ? "+" : "";
                        const statusClass = info.gap < 0 ? "text-green" : "text-red";
                        gapEl.className = statusClass;
                        gapEl.innerText = `${gapSign}${info.gap.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: decimals})} (${gapSign}${info.pct_gap}%)`;
                    }
                    if (aiEl) {
                        aiEl.className = info.ai_direction === "BULLISH" ? "text-green" : (info.ai_direction === "BEARISH" ? "text-red" : "text-yellow");
                        aiEl.innerText = info.ai_direction;
                    }
                    if (btnContainer) {
                        if (info.action === "BUY") {
                            btnContainer.innerHTML = `<button class="action-btn buy" style="width: 100%; border: 1.5px solid var(--text-green); box-shadow: 0 0 10px rgba(0,255,0,0.15); background: rgba(0,255,0,0.08); color: var(--text-green); font-weight: bold; cursor: pointer; padding: 4px; border-radius: 4px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; text-shadow: 0 0 5px rgba(0,255,0,0.3);">BUY DIP</button>`;
                        } else if (info.action === "SELL") {
                            btnContainer.innerHTML = `<button class="action-btn sell" style="width: 100%; border: 1.5px solid var(--text-red); box-shadow: 0 0 10px rgba(255,0,0,0.15); background: rgba(255,0,0,0.08); color: var(--text-red); font-weight: bold; cursor: pointer; padding: 4px; border-radius: 4px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; text-shadow: 0 0 5px rgba(255,0,0,0.3);">SELL RALLY</button>`;
                        } else {
                            btnContainer.innerHTML = `<button class="action-btn" style="width: 100%; border: 1px solid var(--text-yellow); background: rgba(255,183,0,0.05); color: var(--text-yellow); cursor: default; padding: 4px; border-radius: 4px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem;">HOLD / WAIT</button>`;
                        }
                    }
                }

                // === CURRENCY STRENGTH INDEX (CSI) BARS ===
                const csiContainer = document.getElementById('csi-bars-container');
                if (csiContainer && data.currency_indices) {
                    const indices = data.currency_indices;
                    const CSI_META = {
                        'DXY': { name: 'USD', color: '#00d4ff', index: 'DXY' },
                        'EXY': { name: 'EUR', color: '#3b82f6', index: 'EXY' },
                        'BXY': { name: 'GBP', color: '#8b5cf6', index: 'BXY' },
                        'JXY': { name: 'JPY', color: '#f59e0b', index: 'JXY' },
                        'SFX': { name: 'CHF', color: '#10b981', index: 'SFX' },
                        'CXY': { name: 'CAD', color: '#ef4444', index: 'CXY' },
                        'AXY': { name: 'AUD', color: '#f97316', index: 'AXY' },
                        'ZXY': { name: 'NZD', color: '#06b6d4', index: 'ZXY' }
                    };
                    const sorted = Object.entries(indices).sort((a, b) => b[1].score - a[1].score);
                    let html = '<div style="display:grid; grid-template-columns:1fr; gap:5px;">';
                    sorted.forEach(([key, val], rank) => {
                        const meta = CSI_META[key] || { name: key, color: '#94a3b8', index: key };
                        const score = val.score;
                        const pct = val.percentage;
                        const pctSign = pct >= 0 ? '+' : '';
                        const barWidth = Math.max(2, Math.min(100, score));
                        const isStrong = score >= 50;
                        const barColor = isStrong ? meta.color : '#334155';
                        const textColor = isStrong ? meta.color : '#64748b';
                        const arrowIcon = isStrong ? '▲' : '▼';
                        const arrowColor = isStrong ? '#00ff41' : '#ff3333';
                        const rankColor = rank === 0 ? '#ffd700' : (rank <= 2 ? '#c0c0c0' : '#64748b');
                        html += `<div style="display:flex; flex-direction:column; gap:2px;">
                            <div style="display:flex; align-items:center; gap:5px;">
                                <span style="color:${rankColor}; font-size:0.6rem; width:12px; font-weight:bold;">#${rank+1}</span>
                                <span style="color:${textColor}; font-weight:bold; flex:1;">${meta.name} <span style="color:#475569; font-size:0.55rem;">${meta.index}</span></span>
                                <span style="color:${arrowColor}; font-size:0.6rem;">${arrowIcon}</span>
                                <span style="color:${textColor};">${pctSign}${pct.toFixed(3)}%</span>
                                <span style="color:#475569; font-size:0.55rem; min-width:30px; text-align:right;">${score.toFixed(1)}</span>
                            </div>
                            <div style="background:rgba(255,255,255,0.05); border-radius:3px; height:5px; overflow:hidden;">
                                <div style="width:${barWidth}%; height:100%; background:linear-gradient(90deg,${barColor}88,${barColor}); border-radius:3px; transition:width 0.6s ease; box-shadow:0 0 6px ${barColor}44;"></div>
                            </div>
                        </div>`;
                    });
                    html += '</div>';
                    // Update timestamp
                    const csiTime = document.getElementById('csi-update-time');
                    if (csiTime) csiTime.innerText = 'LIVE ' + new Date().toLocaleTimeString('en-GB', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
                    csiContainer.innerHTML = html;
                }

                // === INTERMARKET INDICES ===
                const imContainer = document.getElementById('intermarket-container');
                if (imContainer && data.intermarket) {
                    const IM_COLORS = { 'BULLISH': '#00ff41', 'BEARISH': '#ff3333', 'NEUTRAL': '#fbbf24' };
                    let html = '';
                    for (const im of data.intermarket) {
                        const chgSign = im.change_pct >= 0 ? '+' : '';
                        const chgColor = im.change_pct >= 0 ? '#00ff41' : '#ff3333';
                        const impColor = IM_COLORS[im.gold_impact] || '#fbbf24';
                        const impIcon = im.gold_impact === 'BULLISH' ? '▲' : (im.gold_impact === 'BEARISH' ? '▼' : '─');
                        const stars = '⭐'.repeat(im.stars);
                        const priceStr = im.price !== null ? im.price.toLocaleString('en-US', {maximumFractionDigits: 3}) : 'N/A';
                        html += `<div style="display:flex; align-items:center; gap:4px; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <div style="flex:1;">
                                <span style="color:#fff; font-weight:bold;">${im.name}</span>
                                <span style="color:#475569; font-size:0.55rem; margin-left:4px;">${im.desc}</span>
                            </div>
                            <span style="color:${chgColor}; min-width:48px; text-align:right;">${chgSign}${im.change_pct.toFixed(2)}%</span>
                            <span style="color:${impColor}; min-width:22px; text-align:center; font-size:0.7rem; font-weight:bold;">${impIcon}</span>
                            <span style="color:${impColor}; min-width:58px; font-size:0.6rem; text-align:right; font-weight:bold;">${im.gold_impact}</span>
                        </div>`;
                    }
                    imContainer.innerHTML = html || '<div style="color:var(--text-muted); text-align:center; padding:10px;">Data N/A dari broker</div>';
                }

                // === PAIR RECOMMENDATIONS ===
                const pairContainer = document.getElementById('pair-rec-container');
                if (pairContainer && data.pair_recommendations) {
                    const recs = data.pair_recommendations;
                    if (recs.length === 0) {
                        pairContainer.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:10px;">CSI gap terlalu kecil - pasar sideways</div>';
                    } else {
                        let html = `<div style="display:flex; justify-content:space-between; color:#475569; font-size:0.6rem; padding:0 2px 4px; border-bottom:1px solid rgba(255,255,255,0.1); letter-spacing:0.5px;">
                            <span>PAIR</span><span>AKSI</span><span>GAP</span><span>KUALITAS</span><span>CONF%</span>
                        </div>`;
                        for (const rec of recs) {
                            const actColor = rec.action === 'BUY' ? '#00ff41' : '#ff3333';
                            const actBg = rec.action === 'BUY' ? 'rgba(0,255,65,0.08)' : 'rgba(255,51,51,0.08)';
                            html += `<div style="display:flex; align-items:center; gap:4px; padding:4px 2px; border-bottom:1px solid rgba(255,255,255,0.04);">
                                <span style="color:#fff; font-weight:bold; flex:1;">${rec.pair}</span>
                                <span style="color:${actColor}; background:${actBg}; border:1px solid ${actColor}44; padding:1px 6px; border-radius:3px; font-weight:bold; font-size:0.6rem;">${rec.action}</span>
                                <span style="color:#94a3b8; min-width:36px; text-align:center;">${rec.gap.toFixed(3)}</span>
                                <span style="color:#fbbf24; min-width:52px; text-align:center; font-size:0.6rem;">${rec.quality}</span>
                                <span style="color:${actColor}; min-width:30px; text-align:right; font-weight:bold;">${rec.confidence}%</span>
                            </div>`;
                        }
                        pairContainer.innerHTML = html;
                    }
                }
            }
        } catch (e) {
            console.error("Failed to fetch laggard data", e);
        }
    }

    // INITIALIZATION
    fetchXedyData();
    fetchLiveTicks();
    fetchLaggardData();
    setInterval(fetchXedyData, 60000); // Heavy 60s dashboard refresh
    setInterval(fetchLiveTicks, 1000); // Lightweight 1s tick updates
    setInterval(fetchLaggardData, 5000); // 5s laggard updates

    // Auto-reload at 3 AM to flush browser memory/garbage collection
    function checkDailyReload() {
        const now = new Date();
        if (now.getHours() === 3 && now.getMinutes() === 0) {
            console.log("Memory flush reload...");
            window.location.reload();
        }
    }
    setInterval(checkDailyReload, 60000); // Check once per minute

    function renderDashboard(data) {
        // Render Macro Dashboard
        const macroListEl = document.getElementById('macro-dashboard-list');
        let mHtml = '';
        data.macro_dashboard.forEach(m => {
            let vClass = "text-green";
            if(m.val.includes("WEAK") || m.val.includes("FALLING") || m.val.includes("BEARISH")) vClass = "text-red";
            if(m.val === "NEUTRAL" || m.val === "MODERATE") vClass = "text-yellow";
            
            let dClass = m.dir === 'up' ? 'arrow-up text-green' : (m.dir === 'down' ? 'arrow-down text-red' : 'arrow-right text-yellow');
            
            mHtml += `
            <div class="macro-item">
                <span class="macro-name">${m.name}</span>
                <div class="macro-val-group">
                    <span class="macro-text ${vClass}">${m.val}</span>
                    <span class="macro-score ${dClass}">${m.score}</span>
                </div>
            </div>
            `;
        });
        macroListEl.innerHTML = mHtml;

        // Render Top 5 Macro Drivers dynamically
        const driversListEl = document.getElementById('drivers-list');
        if (driversListEl && data.top_drivers) {
            let drHtml = '';
            data.top_drivers.forEach((dr, idx) => {
                drHtml += `<div class="driver-item"><span class="idx">${idx + 1}</span> ${dr}</div>`;
            });
            driversListEl.innerHTML = drHtml;
        }

        // Render Institutional Flow
        const flowListEl = document.getElementById('flow-list');
        let fHtml = '';
        data.institutional_flow.forEach(f => {
            const svgMock = f.color === 'text-green' ? `<svg width="40" height="15"><polyline points="0,15 10,10 20,12 30,5 40,0" fill="none" stroke="#00ff41" stroke-width="1.5"/></svg>` : `<svg width="40" height="15"><polyline points="0,0 10,8 20,5 30,12 40,15" fill="none" stroke="#ff3333" stroke-width="1.5"/></svg>`;
            fHtml += `
            <div class="flow-item">
                <span class="flow-name">${f.name}</span>
                <div class="macro-val-group">
                    <span class="macro-text ${f.color}">${f.val}</span>
                    ${svgMock}
                </div>
            </div>
            `;
        });
        flowListEl.innerHTML = fHtml;

        // Render Assets
        const assetsContainer = document.getElementById('assets-container');
        let aHtml = '';
        
        const forecastHTML = (f, currentPrice, isJpy) => {
            const openVal = f.open || currentPrice;
            let closeVal = f.close;
            if (!closeVal) {
                const p = parseFloat(currentPrice.toString().replace(/[^0-9.]/g, ''));
                const high = parseFloat(f.high.toString().replace(/[^0-9.]/g, ''));
                const low = parseFloat(f.low.toString().replace(/[^0-9.]/g, ''));
                if (!isNaN(p) && !isNaN(high) && !isNaN(low)) {
                    const isBull = f.dir && f.dir.includes('BULL');
                    const diff = isBull ? (high - p) : (p - low);
                    const change = diff * 0.4;
                    const close = isBull ? (p + change) : (p - change);
                    const decimals = isJpy ? 3 : (f.high.toString().includes('.') ? f.high.toString().split('.')[1].length : 2);
                    closeVal = close.toFixed(decimals);
                } else {
                    closeVal = currentPrice;
                }
            }
            return `
                <div class="fc-row"><span class="fc-label">DIRECTION</span><span class="fc-val ${f.dirClass}">${f.dir}</span></div>
                <div class="fc-row"><span class="fc-label">OPEN</span><span class="fc-val">${openVal}</span></div>
                <div class="fc-row"><span class="fc-label">LOW</span><span class="fc-val">${f.low}</span></div>
                <div class="fc-row"><span class="fc-label">HIGH</span><span class="fc-val">${f.high}</span></div>
                <div class="fc-row"><span class="fc-label">CLOSE</span><span class="fc-val">${closeVal}</span></div>
                <div class="fc-row"><span class="fc-label">BULL PROB.</span><span class="fc-val">${f.bp}</span></div>
                <div class="fc-row"><span class="fc-label">BEAR PROB.</span><span class="fc-val">${f.bearp}</span></div>
                <div class="fc-row"><span class="fc-label">CONFIDENCE</span><span class="fc-val">${f.conf}</span></div>
                <div class="fc-row"><span class="fc-label">ACCURACY</span><span class="fc-val text-green" style="font-weight:bold;">${f.accuracy}</span></div>
                <button class="action-btn ${f.btn}">${f.action}</button>
            `;
        };

        data.assets.forEach(a => {
            let chgColor = a.cColor || 'text-green';
            const isJpy = a.symbol.includes('JPY');
            aHtml += `
            <div class="asset-card">
                <div class="asset-header" style="flex-direction: column; align-items: flex-start; gap: 8px;">
                    <div style="display: flex; align-items: center; gap: 8px; width: 100%;">
                        <div class="asset-icon">${a.icon}</div>
                        <div class="asset-info">
                            <span class="asset-name">${a.symbol}</span>
                            <span class="asset-price ${chgColor}" id="live-price-${a.symbol.replace(/\s+/g, '-')}">${a.price}</span>
                        </div>
                    </div>
                    <!-- Detailed Tick Metrics -->
                    <div class="tick-details" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; font-size: 0.55rem; width: 100%; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px; font-family: var(--font-mono);">
                        <div><span style="color:var(--text-muted);">BID:</span> <strong id="live-bid-${a.symbol.replace(/\s+/g, '-')}" style="color:#fff;">...</strong></div>
                        <div><span style="color:var(--text-muted);">ASK:</span> <strong id="live-ask-${a.symbol.replace(/\s+/g, '-')}" style="color:#fff;">...</strong></div>
                        <div><span style="color:var(--text-muted);">CHG:</span> <strong id="live-chg-${a.symbol.replace(/\s+/g, '-')}" class="${chgColor}">${a.change}</strong></div>
                        <div><span style="color:var(--text-muted);">VOL:</span> <strong id="live-vol-${a.symbol.replace(/\s+/g, '-')}" style="color:#fff;">...</strong></div>
                    </div>
                </div>
                <!-- Fair Value & FVG Detector -->
                <div class="laggard-detail-box" style="margin-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 10px; font-family: 'Share Tech Mono', monospace; font-size: 0.68rem; display: flex; flex-direction: column; gap: 6px;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted);">FAIR VALUE (EST):</span>
                        <strong id="card-fair-value-${a.symbol.replace(/\s+/g, '-')}" style="color: var(--text-yellow);">...</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted);">FVG / GAP:</span>
                        <strong id="card-gap-${a.symbol.replace(/\s+/g, '-')}" style="color: #fff;">...</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted);">AI FORECAST (D+1):</span>
                        <span id="card-ai-dir-${a.symbol.replace(/\s+/g, '-')}" style="font-weight: bold;">...</span>
                    </div>
                </div>
                <div style="margin-top: 10px; text-align: center;" id="card-action-btn-container-${a.symbol.replace(/\s+/g, '-')}">
                    <button class="action-btn" style="width: 100%; font-size: 0.7rem; border-radius: 4px; padding: 4px; cursor: default; border: 1px solid var(--border-glow); background: rgba(255,255,255,0.03); color: var(--text-muted);">AWAITING DATA</button>
                </div>
            </div>
            `;
        });
        assetsContainer.innerHTML = aHtml;

        // Render Correlation Matrix dynamically
        if (data.correlation_matrix) {
            const tableBody = document.getElementById('correlation-table-body');
            if (tableBody) {
                const cols = ["XAUUSD", "USDJPY", "WTI OIL", "DXY", "US10Y", "DJI", "VIX"];
                let cHtml = '';
                cols.forEach(rowAsset => {
                    cHtml += `<tr><th>${rowAsset}</th>`;
                    cols.forEach(colAsset => {
                        let val = data.correlation_matrix[colAsset][rowAsset];
                        let valStr = val.toFixed(2);
                        let colorClass = 'text-white';
                        if (val >= 0.20 || val === 1.0) colorClass = 'text-green';
                        else if (val <= -0.20) colorClass = 'text-red';
                        else colorClass = 'text-muted'; // Neutral correlation
                        cHtml += `<td class="${colorClass}">${valStr}</td>`;
                    });
                    cHtml += `</tr>`;
                });
                tableBody.innerHTML = cHtml;
            }
        }

        // Initialize Gauges if they don't exist yet
        if (!window.gaugesInitialized) {
            initGauges(data.gauges);
            window.gaugesInitialized = true;
        }

        // Render Header Dynamic Info
        let phase = data.gauges.market_sentiment_score > 50 ? 'RISK ON' : 'RISK OFF';
        let pClass = phase === 'RISK ON' ? 'text-green' : 'text-red';
        document.getElementById('market-phase-val').innerText = phase;
        document.getElementById('market-phase-val').className = 'phase-value ' + pClass;
        
        if (data.top_drivers && data.top_drivers.length >= 2) {
            document.getElementById('top-driver-val').innerHTML = data.top_drivers[0] + '<br>' + data.top_drivers[1];
        }
        
        // Render News
        const newsListEl = document.getElementById('news-list');
        if (newsListEl && data.news_feed) {
            let newsHtml = '';
            data.news_feed.forEach(n => {
                newsHtml += `
                <div class="news-item">
                    <div class="news-time">${n.time}</div>
                    <div class="news-title ${n.impact}">${n.title}</div>
                </div>
                `;
            });
            // Pure CSS Marquee Approach (Bulletproof)
            // Duplicate the news list so it seamlessly loops via CSS transform
            const infiniteHtml = newsHtml + newsHtml;
            const wrappedHtml = `<div class="news-ticker-content">${infiniteHtml}</div>`;
            if (newsListEl.innerHTML !== wrappedHtml) {
                newsListEl.innerHTML = wrappedHtml;
            }
            // NO JS SCROLLING NEEDED ANYMORE! Handled 100% by CSS.

            // Floating Overlay Helper to handle Autoplay Policy restrictions
            function showTtsResumeOverlay(sentences, index) {
                if (document.getElementById('tts-resume-overlay')) return;
                
                const overlay = document.createElement('div');
                overlay.id = 'tts-resume-overlay';
                overlay.style.cssText = `
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 99999;
                    background: rgba(8, 16, 40, 0.95);
                    border: 2px solid var(--accent, #3b82f6);
                    box-shadow: 0 0 15px rgba(59, 130, 246, 0.6);
                    border-radius: 8px;
                    padding: 10px 15px;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    cursor: pointer;
                    animation: slideInUp 0.3s ease;
                    font-family: var(--mono, monospace);
                    color: #fff;
                    font-size: 0.72rem;
                    letter-spacing: 1px;
                `;
                overlay.innerHTML = `
                    <span style="animation: blink-neon 1.2s infinite; color: var(--gold, #fbbf24); font-size:0.9rem;">🎙️</span>
                    <span>RESUME NEWS READOUT (CLICK TO LISTEN)</span>
                    <button style="background: var(--accent, #3b82f6); border:none; color:#fff; border-radius:3px; padding:2px 6px; font-weight:bold; font-size:0.65rem; cursor:pointer;">PLAY</button>
                `;

                if (!document.getElementById('tts-animation-style')) {
                    const style = document.createElement('style');
                    style.id = 'tts-animation-style';
                    style.innerHTML = `
                        @keyframes slideInUp {
                            from { transform: translateY(50px); opacity: 0; }
                            to { transform: translateY(0); opacity: 1; }
                        }
                        @keyframes blink-neon {
                            0% { opacity: 0.3; }
                            50% { opacity: 1; }
                            100% { opacity: 0.3; }
                        }
                    `;
                    document.head.appendChild(style);
                }

                overlay.addEventListener('click', () => {
                    overlay.remove();
                    speakQueue(sentences, index);
                });

                document.body.appendChild(overlay);
            }

            // Persistent Text to Speech Manager
            function speakQueue(sentences, index) {
                if (index >= sentences.length) {
                    localStorage.removeItem('tts_active');
                    localStorage.removeItem('tts_index');
                    localStorage.removeItem('tts_sentences');
                    const btn = document.getElementById('btn-read-news');
                    if (btn) btn.innerText = '🔊 BACA';
                    return;
                }
                
                localStorage.setItem('tts_active', 'true');
                localStorage.setItem('tts_index', index.toString());
                localStorage.setItem('tts_sentences', JSON.stringify(sentences));
                
                window.speechSynthesis.cancel(); // Stop any current speech
                
                const utterance = new SpeechSynthesisUtterance(sentences[index]);
                utterance.lang = 'id-ID';
                utterance.rate = 1.4;
                
                let voices = window.speechSynthesis.getVoices();
                let idVoice = voices.find(v => v.lang.includes('id') && v.name.toLowerCase().includes('female'));
                if (!idVoice) idVoice = voices.find(v => v.lang.includes('id'));
                if (idVoice) utterance.voice = idVoice;
                
                utterance.onend = () => {
                    if (localStorage.getItem('tts_active') === 'true') {
                        speakQueue(sentences, index + 1);
                    }
                };
                
                utterance.onerror = () => {
                    if (localStorage.getItem('tts_active') === 'true') {
                        speakQueue(sentences, index + 1);
                    }
                };
                
                window.speechSynthesis.speak(utterance);
                const btn = document.getElementById('btn-read-news');
                if (btn) btn.innerText = '⏸ STOP';
            }

            // Text to Speech (Indonesian Female)
            const btnReadNews = document.getElementById('btn-read-news');
            if (btnReadNews && !window.newsTtsBound) {
                window.newsTtsBound = true;
                
                // Auto-resume speech if it was active on page load
                setTimeout(() => {
                    if (localStorage.getItem('tts_active') === 'true') {
                        const savedSentences = JSON.parse(localStorage.getItem('tts_sentences') || '[]');
                        const savedIndex = parseInt(localStorage.getItem('tts_index') || '0');
                        if (savedSentences.length > 0) {
                            speakQueue(savedSentences, savedIndex);
                            
                            // Check if blocked by browser autoplay policy after 400ms
                            setTimeout(() => {
                                if (!window.speechSynthesis.speaking && localStorage.getItem('tts_active') === 'true') {
                                    showTtsResumeOverlay(savedSentences, savedIndex);
                                }
                            }, 400);
                        }
                    }
                }, 1000);

                btnReadNews.addEventListener('click', () => {
                    if (localStorage.getItem('tts_active') === 'true') {
                        localStorage.removeItem('tts_active');
                        window.speechSynthesis.cancel();
                        btnReadNews.innerText = '🔊 BACA';
                        const overlay = document.getElementById('tts-resume-overlay');
                        if (overlay) overlay.remove();
                    } else {
                        const titles = Array.from(document.querySelectorAll('.news-title')).map(el => el.innerText);
                        if (titles.length === 0) return;
                        
                        const sentences = ["Berita Makro Terkini."];
                        titles.slice(0, 10).forEach(t => sentences.push(t));
                        speakQueue(sentences, 0);
                    }
                });
            }
        }

        // Render Liquidity Zones
        if (data.liquidity_zones) {
            const pocXau = document.getElementById('liquidity-poc-xau');
            const pocJpy = document.getElementById('liquidity-poc-jpy');
            const pocOil = document.getElementById('liquidity-poc-oil');
            const pocEur = document.getElementById('liquidity-poc-eur');
            const pocGbp = document.getElementById('liquidity-poc-gbp');
            
            if(pocXau && data.liquidity_zones['XAUUSD'] !== undefined) {
                const val = Number(data.liquidity_zones['XAUUSD']);
                pocXau.innerText = isNaN(val) ? data.liquidity_zones['XAUUSD'] : val.toFixed(0);
            }
            if(pocJpy && data.liquidity_zones['USDJPY'] !== undefined) {
                const val = Number(data.liquidity_zones['USDJPY']);
                pocJpy.innerText = isNaN(val) ? data.liquidity_zones['USDJPY'] : val.toFixed(1);
            }
            if(pocOil && data.liquidity_zones['WTI OIL'] !== undefined) {
                const val = Number(data.liquidity_zones['WTI OIL']);
                pocOil.innerText = isNaN(val) ? data.liquidity_zones['WTI OIL'] : val.toFixed(1);
            }
            if(pocEur && data.liquidity_zones['EURUSD'] !== undefined) {
                const val = Number(data.liquidity_zones['EURUSD']);
                pocEur.innerText = isNaN(val) ? data.liquidity_zones['EURUSD'] : val.toFixed(4);
            }
            if(pocGbp && data.liquidity_zones['GBPUSD'] !== undefined) {
                const val = Number(data.liquidity_zones['GBPUSD']);
                pocGbp.innerText = isNaN(val) ? data.liquidity_zones['GBPUSD'] : val.toFixed(4);
            }
        }

        // Render Macro Conclusion Badge
        const biasResEl = document.getElementById('bias-result');
        const biasSubEl = document.getElementById('bias-sub');
        if (biasResEl && biasSubEl && data.assets && data.assets.length >= 3) {
            let goldDir = data.assets[0].f1.dir;
            let oilDir = data.assets[2].f1.dir; 
            let usdDir = data.assets[1].f1.dir === 'BULLISH' ? 'BULLISH USD' : 'BEARISH USD'; // if USDJPY is bullish, USD is strong
            biasResEl.innerHTML = goldDir + '<br>GOLD & ' + oilDir + '<br>OIL';
            biasResEl.className = 'result ' + (goldDir === 'BULLISH' ? 'text-green' : 'text-red');
            biasSubEl.innerText = usdDir;
        }

        // Update Sentiment Score Text and Color dynamically
        let sentScore = data.gauges.market_sentiment_score;
        let sentColorClass = 'text-green';
        let sentDesc = 'GREED';
        let sentColorHex = '#00ff41';
        let sentColorRgba = 'rgba(0, 255, 65, ';
        
        if (sentScore <= 45) {
            sentColorClass = 'text-red';
            sentDesc = 'FEAR';
            sentColorHex = '#ff3333';
            sentColorRgba = 'rgba(255, 51, 51, ';
        } else if (sentScore <= 55) {
            sentColorClass = 'text-yellow';
            sentDesc = 'SIDEWAY';
            sentColorHex = '#ffb700';
            sentColorRgba = 'rgba(255, 183, 0, ';
        }

        let sentNumEl = document.querySelector('.sentiment-score .num');
        let sentDescEl = document.querySelector('.sentiment-score .desc');
        if (sentNumEl && sentDescEl) {
            sentNumEl.innerText = sentScore;
            sentNumEl.className = `${sentColorClass} num`;
            sentDescEl.innerText = sentDesc;
            sentDescEl.className = `${sentColorClass} desc`;
        }
        
        // Update Chart Color dynamically if initialized
        if (window.sentimentChartInstance) {
            window.sentimentChartInstance.data.datasets[0].borderColor = sentColorHex;
            let sCtx = document.getElementById('sentimentChart').getContext('2d');
            let sGrad = sCtx.createLinearGradient(0, 0, 0, 100);
            sGrad.addColorStop(0, sentColorRgba + '0.4)');
            sGrad.addColorStop(1, sentColorRgba + '0.0)');
            window.sentimentChartInstance.data.datasets[0].backgroundColor = sGrad;
            
            // Append new data point and remove oldest
            let sData = window.sentimentChartInstance.data.datasets[0].data;
            let sLabels = window.sentimentChartInstance.data.labels;
            sData.push(sentScore);
            sData.shift();
            
            let nowTime = new Date().toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' });
            sLabels.push(nowTime);
            sLabels.shift();
            
            if (window.sentimentChartInstance.data.datasets[1]) {
                let sData50 = window.sentimentChartInstance.data.datasets[1].data;
                sData50.push(50);
                sData50.shift();
            }
            
            window.sentimentChartInstance.update();
            window.sentimentChartInstance.update();
        }

        // Render Economic Calendar
        if (data.economic_calendar) {
            const ecoListEl = document.getElementById('eco-calendar-list');
            if (ecoListEl) {
                let ecHtml = '';
                data.economic_calendar.forEach(e => {
                    ecHtml += `
                    <div class="eco-item">
                        <span class="time">${e.time}</span>
                        <span class="cur">${e.cur}</span>
                        <span class="event">${e.event}</span>
                        <span class="impact ${e.impact}">${e.impact}</span>
                    </div>`;
                });
                if (ecoListEl.innerHTML !== ecHtml) ecoListEl.innerHTML = ecHtml;
            }
        }

        // Render Technical Signals
        if (data.technical_signals) {
            const techBodyEl = document.getElementById('tech-table-body');
            if (techBodyEl) {
                let tHtml = '';
                ["XAUUSD", "USDJPY", "WTI OIL", "EURUSD", "GBPUSD"].forEach(sym => {
                    const t = data.technical_signals[sym];
                    if (t) {
                        const trClass = t.trend === "BULLISH" ? "text-green" : "text-red";
                        const rsiClass = t.rsi > 70 ? "text-red" : (t.rsi < 30 ? "text-green" : "text-yellow");
                        const maClass = t.ma50 === "UP" ? "text-green" : "text-red";
                        tHtml += `
                        <tr>
                            <td style="color:var(--text-yellow);">${sym}</td>
                            <td class="${rsiClass}">${t.rsi}</td>
                            <td class="${maClass}">${t.ma50}</td>
                            <td class="${trClass}" style="font-weight:bold;">${t.trend}</td>
                        </tr>`;
                    }
                });
                if (techBodyEl.innerHTML !== tHtml) techBodyEl.innerHTML = tHtml;
            }
        }
    }

    function initGauges(gaugeData) {
        function drawDoughnut(ctxId, value, colors) {
            new Chart(document.getElementById(ctxId), {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [value, 100 - value],
                        backgroundColor: colors,
                        borderWidth: 0,
                        circumference: 180,
                        rotation: 270
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '80%',
                    plugins: { tooltip: { enabled: false } },
                    animation: { duration: 2000, easing: 'easeOutQuart' }
                }
            });
        }

        // Macro Alignment Gauge
        let mCtx = document.getElementById('macroGauge').getContext('2d');
        let mGrad = mCtx.createLinearGradient(0, 0, 200, 0);
        mGrad.addColorStop(0, '#ff3333');
        mGrad.addColorStop(0.5, '#ffb700');
        mGrad.addColorStop(1, '#00ff41');
        drawDoughnut('macroGauge', gaugeData.macro_alignment_score, [mGrad, 'rgba(255,255,255,0.05)']);
        document.querySelector('#macroGauge + .gauge-value .num').innerText = gaugeData.macro_alignment_score;
        let mDesc = document.querySelector('#macroGauge + .gauge-value .desc');
        mDesc.className = 'desc';
        if (gaugeData.macro_alignment_score > 55) { mDesc.innerText = 'STRONG'; mDesc.classList.add('text-green'); }
        else if (gaugeData.macro_alignment_score >= 45) { mDesc.innerText = 'NEUTRAL'; mDesc.classList.add('text-yellow'); }
        else { mDesc.innerText = 'WEAK'; mDesc.classList.add('text-red'); }

        // Market Regime Gauge
        let rCanvas = document.getElementById('regimeGauge');
        if (rCanvas) {
            let rCtx = rCanvas.getContext('2d');
            let rGrad = rCtx.createLinearGradient(0, 0, 150, 0);
            rGrad.addColorStop(0, '#ff3333');
            rGrad.addColorStop(0.5, '#00d4ff');
            rGrad.addColorStop(1, '#00ff41');
            drawDoughnut('regimeGauge', gaugeData.market_regime_score, [rGrad, 'rgba(255,255,255,0.05)']);
            document.querySelector('#regimeGauge + .gauge-value .num').innerText = gaugeData.market_regime_score + '%';
            let rDesc = document.querySelector('#regimeGauge + .gauge-value .desc');
            rDesc.className = 'desc';
            if (gaugeData.market_regime_score > 55) { rDesc.innerText = 'RISK ON'; rDesc.classList.add('text-green'); }
            else if (gaugeData.market_regime_score >= 45) { rDesc.innerText = 'NEUTRAL'; rDesc.classList.add('text-yellow'); }
            else { rDesc.innerText = 'RISK OFF'; rDesc.classList.add('text-red'); }
        }

        // LINE CHART: Sentiment
        let sCtx = document.getElementById('sentimentChart').getContext('2d');
        
        let sentScore = gaugeData.market_sentiment_score;
        let sentColorHex = '#00ff41';
        let sentColorRgba = 'rgba(0, 255, 65, ';
        if (sentScore <= 45) {
            sentColorHex = '#ff3333';
            sentColorRgba = 'rgba(255, 51, 51, ';
        } else if (sentScore <= 55) {
            sentColorHex = '#ffb700';
            sentColorRgba = 'rgba(255, 183, 0, ';
        }
        
        let sGrad = sCtx.createLinearGradient(0, 0, 0, 100);
        sGrad.addColorStop(0, sentColorRgba + '0.4)');
        sGrad.addColorStop(1, sentColorRgba + '0.0)');
        
        let sData = new Array(1440);
        let sLabels = new Array(1440);
        let now = new Date();
        let cur = sentScore; 
        
        // 1440 points = 24 hours (1 point per minute). Walk backwards from current score.
        for(let i=0; i<1440; i++) {
            sData[1439 - i] = cur;
            
            let d = new Date(now.getTime() - i * 60000);
            sLabels[1439 - i] = d.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' });
            
            // Random walk backwards with mean reversion to 50
            let drift = (Math.random() - 0.5) * 4;
            let pull = (50 - cur) * 0.02;
            cur += drift + pull;
            
            if(cur > 98) cur = 98;
            if(cur < 2) cur = 2;
        }

        window.sentimentChartInstance = new Chart(sCtx, {
            type: 'line',
            data: {
                labels: sLabels,
                datasets: [{
                    data: sData,
                    borderColor: sentColorHex,
                    borderWidth: 2,
                    backgroundColor: sGrad,
                    fill: true,
                    pointRadius: 0,
                    tension: 0.1
                }, {
                    data: new Array(sLabels.length).fill(50),
                    borderColor: 'rgba(255, 183, 0, 0.4)',
                    borderWidth: 1,
                    borderDash: [5, 5],
                    fill: false,
                    pointRadius: 0,
                    tension: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { tooltip: { enabled: false }, legend: { display: false } },
                scales: {
                    x: { display: true, ticks: { maxTicksLimit: 6, font: {size: 8}, color: '#64748b' }, border: {display: false}, grid: {display: false} },
                    y: { display: true, min: 0, max: 100, ticks: { maxTicksLimit: 3, font: {size: 8}, color: '#64748b' }, border: {display: false}, grid: {color: 'rgba(255,255,255,0.05)'} }
                },
                layout: { padding: { right: 70, left: 0, top: 10, bottom: 0 } }
            }
        });
    }
});
