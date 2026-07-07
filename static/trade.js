let activeTab = 'trade';
let updateInterval = null;

function switchTab(tab) {
    activeTab = tab;
    
    // Update tabs active state
    document.querySelectorAll('.terminal-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    
    // Update views visibility
    document.getElementById('view-trade').style.display = tab === 'trade' ? 'block' : 'none';
    document.getElementById('view-history').style.display = tab === 'history' ? 'block' : 'none';
    document.getElementById('view-news').style.display = tab === 'news' ? 'block' : 'none';
    document.getElementById('view-calendar').style.display = tab === 'calendar' ? 'block' : 'none';
    
    // Refresh content immediately
    fetchStatus();
}

async function fetchStatus() {
    try {
        const response = await fetch('/api/trade_status');
        const data = await response.json();
        
        // Update Live Tickers if available
        if (data.ticks) {
            renderTicker(data.ticks);
        }
        
        // Hide loader overlay once loaded
        document.getElementById('loading-overlay').style.display = 'none';

        if (data.status === 'error') {
            document.getElementById('connection-status').innerText = 'DISCONNECTED';
            document.getElementById('connection-status').style.color = 'var(--accent-red)';
            alert(data.message);
            return;
        }

        document.getElementById('connection-status').innerText = 'CONNECTED';
        document.getElementById('connection-status').style.color = 'var(--accent-green)';

        // 1. Render Account & Strategy Info Banners
        if (data.account_info) {
            document.getElementById('header-account').innerText = `ACC: ${data.account_info.login} (${data.account_info.name})`;
            document.getElementById('account-server').innerText = `Server: ${data.account_info.server}`;
        }
        
        if (data.active_config && Object.keys(data.active_config).length > 0) {
            document.getElementById('trade-method').innerText = data.active_config.strategy_name;
            document.getElementById('trade-timeframe').innerText = `TF: ${data.active_config.timeframe} / Risk: ${data.active_config.risk_percent}%`;
            
            // Populate AI Decision Explainer elements
            const bias = data.fundamental_bias !== undefined ? data.fundamental_bias : 0.0;
            const biasBadge = document.getElementById('explainer-bias-badge');
            const fundVal = document.getElementById('explainer-fund-val');
            const mainDir = document.getElementById('explainer-main-dir');
            const slVal = document.getElementById('explainer-sl-value');
            const tpVal = document.getElementById('explainer-tp-value');
            
            if (biasBadge) {
                const isBullish = bias > 0;
                biasBadge.innerText = `BIAS FUNDAMENTAL: ${bias > 0 ? '+' : ''}${bias.toFixed(3)} (${isBullish ? 'BULLISH' : 'BEARISH'})`;
                biasBadge.style.background = isBullish ? 'rgba(0, 255, 65, 0.15)' : 'rgba(255, 59, 48, 0.15)';
                biasBadge.style.color = isBullish ? 'var(--accent-green)' : 'var(--accent-red)';
                biasBadge.style.border = `1px solid ${isBullish ? 'var(--accent-green)' : 'var(--accent-red)'}`;
            }
            
            if (fundVal) {
                fundVal.innerText = `${bias > 0 ? 'Bullish' : 'Bearish'} (${(bias * 100).toFixed(0)}%)`;
                fundVal.style.color = bias > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            }
            
            if (mainDir) {
                mainDir.innerText = bias > 0 ? 'BUY (LONG)' : 'SELL (SHORT)';
                mainDir.style.color = bias > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            }
            
            if (slVal) {
                const slDist = data.active_config.sl_dist || data.active_config.stop_atr || 1.2;
                slVal.innerText = `${slDist} * ATR`;
            }
            
            if (tpVal) {
                const tpDist = data.active_config.tp_dist || data.active_config.rr || 1.5;
                tpVal.innerText = `SL * ${tpDist} R`;
            }

            // Dynamically update Fundamental & Technical weight labels based on ML weights
            const fundLabel = document.getElementById('explainer-fund-label');
            const techLabel = document.getElementById('explainer-tech-label');
            if (data.ml_weights && Object.keys(data.ml_weights).length > 0) {
                const w = data.ml_weights;
                const fSum = (w.macro || 0.166) + (w.sentiment || 0.166) + (w.flow || 0.166) + (w.regime || 0.166);
                const fPct = Math.round(fSum * 100);
                const tPct = 100 - fPct; // Ensure they sum to 100%
                if (fundLabel) fundLabel.innerText = `■ Fundamental (${fPct}% Bobot)`;
                if (techLabel) techLabel.innerText = `■ Teknikal (${tPct}% Bobot)`;
            } else {
                if (fundLabel) fundLabel.innerText = '■ Fundamental (80% Bobot)';
                if (techLabel) techLabel.innerText = '■ Teknikal (20% Bobot)';
            }
        } else {
            document.getElementById('trade-method').innerText = 'No Strategy Chosen';
            document.getElementById('trade-timeframe').innerText = 'Go to Backtest page to select and deploy';
            
            // Reset Explainer elements
            const biasBadge = document.getElementById('explainer-bias-badge');
            if (biasBadge) {
                biasBadge.innerText = 'NO ACTIVE STRATEGY';
                biasBadge.style.background = 'rgba(255,255,255,0.05)';
                biasBadge.style.color = 'var(--text-muted)';
                biasBadge.style.border = '1px solid var(--border-color)';
            }
            document.getElementById('explainer-fund-val').innerText = '-';
            document.getElementById('explainer-main-dir').innerText = '-';
            document.getElementById('explainer-sl-value').innerText = '-';
            document.getElementById('explainer-tp-value').innerText = '-';
            const fLbl = document.getElementById('explainer-fund-label');
            const tLbl = document.getElementById('explainer-tech-label');
            if (fLbl) fLbl.innerText = '■ Fundamental (80% Bobot)';
            if (tLbl) tLbl.innerText = '■ Teknikal (20% Bobot)';
        }

        // Render Live AI Activity Logs
        const logsContainer = document.getElementById('ai-logs-container');
        if (logsContainer && data.ai_live_logs) {
            let logHtml = '';
            data.ai_live_logs.forEach(log => {
                logHtml += `
                    <div class="trade-log-${log.type || 'info'}">
                        <span style="color: rgba(255,255,255,0.25);">[${log.t}]</span> ${log.msg}
                    </div>
                `;
            });
            logsContainer.innerHTML = logHtml;
            // Auto scroll to bottom
            logsContainer.scrollTop = logsContainer.scrollHeight;
        }

        // Collect all unique symbols currently being traded (Urutan Pair)
        const activeSymbols = new Set(data.positions.map(p => p.symbol));
        const historySymbols = new Set(data.history.map(h => h.symbol).filter(s => s));
        const combinedSymbols = [...new Set([...activeSymbols, ...historySymbols])];
        document.getElementById('traded-pairs').innerText = combinedSymbols.length > 0 ? combinedSymbols.join(', ') : 'XAUUSD';

        // 2. Render Trade Tab Table
        const tradeTbody = document.getElementById('trade-tbody');
        if (data.positions.length === 0) {
            tradeTbody.innerHTML = `<tr><td colspan="10" class="empty-state">Tidak ada transaksi aktif saat ini.</td></tr>`;
        } else {
            let trHtml = '';
            data.positions.forEach(p => {
                const profitClass = p.profit >= 0 ? 'mt5-profit-green' : 'mt5-profit-red';
                const formattedProfit = p.profit >= 0 ? `+${p.profit.toFixed(2)}` : p.profit.toFixed(2);
                const typeClass = p.type.toLowerCase() === 'buy' ? 'mt5-buy' : 'mt5-sell';
                
                trHtml += `
                    <tr>
                        <td style="font-weight:bold;"><span style="color:${p.type.toLowerCase() === 'buy' ? 'var(--mt5-blue)' : 'var(--mt5-red)'}; font-size: 0.8rem; margin-right:4px;">⚃</span>${p.symbol}</td>
                        <td>${p.ticket}</td>
                        <td>${p.time}</td>
                        <td class="${typeClass}">${p.type.toLowerCase()}</td>
                        <td>${p.volume.toFixed(2)}</td>
                        <td>${p.price.toFixed(2)}</td>
                        <td style="cursor: pointer; text-decoration: underline; color: #0000ff;" onclick="openEditModal(${p.ticket}, '${p.symbol}', '${p.type}', ${p.volume}, ${p.price}, ${p.sl}, ${p.tp})">${p.sl.toFixed(2)}</td>
                        <td style="cursor: pointer; text-decoration: underline; color: #0000ff;" onclick="openEditModal(${p.ticket}, '${p.symbol}', '${p.type}', ${p.volume}, ${p.price}, ${p.sl}, ${p.tp})">${p.tp.toFixed(2)}</td>
                        <td>${p.price_current.toFixed(2)}</td>
                        <td class="${profitClass}" style="text-align:right; font-weight:bold;">
                            <div style="display:flex; justify-content:flex-end; align-items:center; gap:8px;">
                                <span>${formattedProfit}</span>
                                <button onclick="openEditModal(${p.ticket}, '${p.symbol}', '${p.type}', ${p.volume}, ${p.price}, ${p.sl}, ${p.tp})" style="background:none; border:none; color:#555; cursor:pointer; font-size:0.75rem;">⚙</button>
                                <button onclick="closePosition(${p.ticket})" style="background:none; border:none; color:var(--accent-red); font-weight:bold; cursor:pointer; font-size:0.75rem; padding:0 4px;">✖</button>
                            </div>
                        </td>
                    </tr>
                `;
            });
            tradeTbody.innerHTML = trHtml;
        }

        // 3. Render History Tab Table
        const historyTbody = document.getElementById('history-tbody');
        if (data.history.length === 0) {
            historyTbody.innerHTML = `<tr><td colspan="12" class="empty-state">Belum ada riwayat transaksi.</td></tr>`;
        } else {
            let hHtml = '';
            data.history.forEach(h => {
                if (h.type === 'balance') {
                    // Balance deposit row matches Screenshot 1 style
                    hHtml += `
                        <tr style="background-color: #f9f9f9; font-weight:bold;">
                            <td>${h.time}</td>
                            <td></td>
                            <td>${h.ticket}</td>
                            <td style="color:#000;">balance</td>
                            <td></td>
                            <td></td>
                            <td></td>
                            <td></td>
                            <td></td>
                            <td></td>
                            <td class="mt5-profit-green">${h.profit.toFixed(2)}</td>
                            <td style="color:var(--text-muted); font-size:0.65rem; text-align:right; padding-right:15px;">${h.comment}</td>
                        </tr>
                    `;
                } else {
                    const profitClass = h.profit >= 0 ? 'mt5-profit-green' : 'mt5-profit-red';
                    const formattedProfit = h.profit >= 0 ? `+${h.profit.toFixed(2)}` : h.profit.toFixed(2);
                    const typeClass = h.type.toLowerCase() === 'buy' ? 'mt5-buy' : 'mt5-sell';
                    
                    // Simple change calculate
                    const pctChange = (h.profit / 10000.0) * 100.0;
                    const formattedChange = pctChange >= 0 ? `+${pctChange.toFixed(3)}%` : `${pctChange.toFixed(3)}%`;

                    hHtml += `
                        <tr>
                            <td>${h.time}</td>
                            <td>${h.symbol}</td>
                            <td>${h.ticket}</td>
                            <td class="${typeClass}">${h.type.toLowerCase()}</td>
                            <td>${h.volume.toFixed(2)}</td>
                            <td>${h.price.toFixed(2)}</td>
                            <td>${h.sl.toFixed(2)}</td>
                            <td>${h.tp.toFixed(2)}</td>
                            <td>${h.close_time}</td>
                            <td>${h.close_price.toFixed(2)}</td>
                            <td class="${profitClass}">${formattedProfit}</td>
                            <td class="${h.profit >= 0 ? 'mt5-profit-green' : 'mt5-profit-red'}" style="text-align:right; padding-right:15px;">${formattedChange}</td>
                        </tr>
                    `;
                }
            });
            historyTbody.innerHTML = hHtml;
        }

        // Update news tab badge count
        if (data.news) {
            document.getElementById('news-count-badge').innerText = data.news.length;
        }

        // Render News Tab Table
        const newsTbody = document.getElementById('news-tbody');
        if (data.news && data.news.length > 0) {
            let nHtml = '';
            data.news.forEach(n => {
                nHtml += `
                    <tr>
                        <td style="font-weight:bold; color:#555;">[${n.time || 'INFO'}]</td>
                        <td style="color:#000; white-space: normal; line-height: 1.4;">${n.title}</td>
                    </tr>
                `;
            });
            newsTbody.innerHTML = nHtml;
        } else {
            newsTbody.innerHTML = `<tr><td colspan="2" class="empty-state">Tidak ada berita fundamental saat ini.</td></tr>`;
        }

        // Render Calendar Tab Table
        const calendarTbody = document.getElementById('calendar-tbody');
        if (calendarTbody && data.calendar) {
            if (data.calendar.length > 0) {
                let cHtml = '';
                data.calendar.forEach(c => {
                    const countryBadge = `<span style="background: rgba(108,92,231,0.15); color: #a29bfe; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.65rem;">${c.country}</span>`;
                    cHtml += `
                        <tr>
                            <td style="color:var(--text-muted); font-weight: 500;">${c.time}</td>
                            <td>${countryBadge}</td>
                            <td style="color:#000; font-weight:500; white-space: normal; line-height: 1.4;">${c.event}</td>
                            <td style="font-weight:bold; color:var(--mt5-blue);">${c.actual || '-'}</td>
                            <td style="color:#444;">${c.forecast || '-'}</td>
                            <td style="color:#666; padding-right:15px;">${c.previous || '-'}</td>
                        </tr>
                    `;
                });
                calendarTbody.innerHTML = cHtml;
            } else {
                calendarTbody.innerHTML = `<tr><td colspan="6" class="empty-state">Tidak ada event kalender ekonomi hari ini.</td></tr>`;
            }
        }

        // 4. Update Status Summary Row at Bottom
        const summaryRow = document.getElementById('terminal-summary');
        const summaryLeft = document.getElementById('summary-left-txt');
        const summaryRight = document.getElementById('summary-right-profit');

        if (activeTab === 'trade') {
            if (data.account_info) {
                const balance = data.account_info.balance;
                const equity = data.account_info.equity;
                const margin = data.account_info.margin;
                const freeMargin = data.account_info.margin_free;
                const marginLevel = data.account_info.margin_level;
                
                summaryLeft.innerHTML = `• Balance: <strong>${balance.toFixed(2)} USD</strong> &nbsp;&nbsp; Equity: <strong>${equity.toFixed(2)}</strong> &nbsp;&nbsp; Margin: <strong>${margin.toFixed(2)}</strong> &nbsp;&nbsp; Free Margin: <strong>${freeMargin.toFixed(2)}</strong> &nbsp;&nbsp; Margin Level: <strong>${marginLevel.toFixed(2)} %</strong>`;
                
                const totalProfit = data.positions.reduce((sum, p) => sum + p.profit, 0);
                summaryRight.innerText = totalProfit >= 0 ? `+${totalProfit.toFixed(2)}` : totalProfit.toFixed(2);
                summaryRight.className = totalProfit >= 0 ? 'mt5-profit-green' : 'mt5-profit-red';
            }
        } else if (activeTab === 'history') {
            if (data.account_info) {
                const balance = data.account_info.balance;
                
                // Group totals from history deals
                const totalProfit = data.history.filter(h => h.type !== 'balance').reduce((sum, h) => sum + h.profit, 0);
                const totalDeposit = data.history.filter(h => h.type === 'balance' && h.profit >= 0).reduce((sum, h) => sum + h.profit, 0);
                const totalWithdrawal = data.history.filter(h => h.type === 'balance' && h.profit < 0).reduce((sum, h) => sum + h.profit, 0);

                summaryLeft.innerHTML = `• Profit: <strong>${totalProfit.toFixed(2)}</strong> &nbsp;&nbsp; Credit: <strong>0.00</strong> &nbsp;&nbsp; Deposit: <strong>${totalDeposit.toFixed(2)}</strong> &nbsp;&nbsp; Withdrawal: <strong>${totalWithdrawal.toFixed(2)}</strong> &nbsp;&nbsp; Balance: <strong>${balance.toFixed(2)}</strong>`;
                
                summaryRight.innerText = totalProfit >= 0 ? `+${totalProfit.toFixed(2)}` : totalProfit.toFixed(2);
                summaryRight.className = totalProfit >= 0 ? 'mt5-profit-green' : 'mt5-profit-red';
            }
        } else if (activeTab === 'news') {
            summaryLeft.innerHTML = `• Berita Aktif: <strong>${data.news ? data.news.length : 0} Headline Fundamental (Live Yahoo Finance)</strong>`;
            summaryRight.innerText = 'OK';
            summaryRight.className = 'mt5-profit-green';
        } else if (activeTab === 'calendar') {
            summaryLeft.innerHTML = `• Kalender Ekonomi Hari Ini: <strong>${data.calendar ? data.calendar.length : 0} Event Terjadwal (Live Yahoo Finance)</strong>`;
            summaryRight.innerText = 'LIVE';
            summaryRight.className = 'mt5-profit-green';
        } else {
            summaryLeft.innerText = '';
            summaryRight.innerText = '';
        }
    } catch (err) {
        console.error('Error fetching trade status:', err);
    }
}
async function fetchLiveTicks() {
    try {
        const response = await fetch('/api/live_ticks?t=' + Date.now());
        const data = await response.json();
        if (data.ticks) {
            renderTicker(data.ticks);
        }
    } catch (err) {
        console.error('Error fetching live ticks:', err);
    }
}

// Initial pull and periodic loop
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchLiveTicks();
    setInterval(fetchLiveTicks, 1000);  // Tick updates every 1 second (super fast & lightweight)
    updateInterval = setInterval(fetchStatus, 10000); // Full status updates every 10 seconds
});

// 5. Update Live Ticker Bar
function renderTicker(ticks) {
    if (!ticks) return;
    for (const [symbol, t] of Object.entries(ticks)) {
        // IDs format match: ticker-bid-XAUUSD, ticker-ask-XAUUSD, ticker-chg-XAUUSD
        const domSymbol = symbol.replace(" WTI OIL", "-WTI-OIL").replace(" OIL", "-OIL").replace(" ", "-");
        
        const bidEl = document.getElementById(`ticker-bid-${domSymbol}`);
        const askEl = document.getElementById(`ticker-ask-${domSymbol}`);
        const chgEl = document.getElementById(`ticker-chg-${domSymbol}`);
        const lowEl = document.getElementById(`ticker-low-${domSymbol}`);
        const highEl = document.getElementById(`ticker-high-${domSymbol}`);
        const volEl = document.getElementById(`ticker-vol-${domSymbol}`);
        
        if (bidEl) bidEl.innerText = t.bid.toFixed(symbol.includes("JPY") ? 3 : (symbol.includes("EUR") || symbol.includes("GBP") ? 5 : 2));
        if (askEl) askEl.innerText = t.ask.toFixed(symbol.includes("JPY") ? 3 : (symbol.includes("EUR") || symbol.includes("GBP") ? 5 : 2));
        if (lowEl) lowEl.innerText = t.low.toFixed(symbol.includes("JPY") ? 3 : (symbol.includes("EUR") || symbol.includes("GBP") ? 5 : 2));
        if (highEl) highEl.innerText = t.high.toFixed(symbol.includes("JPY") ? 3 : (symbol.includes("EUR") || symbol.includes("GBP") ? 5 : 2));
        if (volEl) volEl.innerText = t.volume ? t.volume.toLocaleString() : '...';
        
        if (chgEl) {
            const formattedChg = t.change >= 0 ? `+${t.change.toFixed(2)}%` : `${t.change.toFixed(2)}%`;
            chgEl.innerText = formattedChg;
            chgEl.className = `ticker-change ${t.change >= 0 ? 'text-green' : 'text-red'}`;
        }
    }
    
    // Dynamic price updates for active order popup
    if (activeOrderSymbol && ticks[activeOrderSymbol]) {
        const t = ticks[activeOrderSymbol];
        const priceEl = document.getElementById('order-current-price');
        if (priceEl) {
            const priceVal = activeOrderType === 'buy' ? t.ask : t.bid;
            priceEl.innerText = priceVal.toFixed(activeOrderSymbol.includes("JPY") ? 3 : (activeOrderSymbol.includes("EUR") || activeOrderSymbol.includes("GBP") ? 5 : 2));
        }
    }
}



// 6. Close and Edit Handlers
async function closePosition(ticket) {
    if (!confirm(`Apakah Anda yakin ingin menutup (CLOSE) transaksi #${ticket}?`)) {
        return;
    }
    try {
        const res = await fetch('/api/trade/close_position', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket })
        });
        const result = await res.json();
        if (result.status === 'success') {
            alert(result.message);
            fetchStatus();
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch(err) {
        alert(`Request failed: ${err}`);
    }
}

let activeEditTicket = null;

function openEditModal(ticket, symbol, type, volume, openPrice, sl, tp) {
    activeEditTicket = ticket;
    document.getElementById('modal-ticket-id').innerText = `#${ticket}`;
    document.getElementById('modal-symbol').innerText = symbol;
    document.getElementById('modal-type').innerText = type.toLowerCase();
    document.getElementById('modal-volume').innerText = volume.toFixed(2);
    document.getElementById('modal-open-price').innerText = openPrice.toFixed(2);
    
    document.getElementById('modal-sl-input').value = sl;
    document.getElementById('modal-tp-input').value = tp;
    
    document.getElementById('edit-modal').style.display = 'flex';
}

function closeEditModal() {
    document.getElementById('edit-modal').style.display = 'none';
    activeEditTicket = null;
}

async function submitModification() {
    if (!activeEditTicket) return;
    const sl = parseFloat(document.getElementById('modal-sl-input').value);
    const tp = parseFloat(document.getElementById('modal-tp-input').value);
    
    try {
        const res = await fetch('/api/trade/modify_position', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticket: activeEditTicket, sl, tp })
        });
        const result = await res.json();
        if (result.status === 'success') {
            alert(result.message);
            closeEditModal();
            fetchStatus();
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch(err) {
        alert(`Request failed: ${err}`);
    }
}

// 7. Order Placement Modal Logic
let activeOrderSymbol = null;
let activeOrderType = null;

function openOrderModal(symbol, type) {
    activeOrderSymbol = symbol;
    activeOrderType = type;
    
    document.getElementById('order-modal-title').innerText = `New Order - ${symbol}`;
    document.getElementById('order-symbol').innerText = symbol;
    
    const typeEl = document.getElementById('order-type');
    typeEl.innerText = type.toUpperCase();
    typeEl.style.color = type === 'buy' ? 'var(--accent-green)' : 'var(--accent-red)';
    
    // Fetch latest price from ticker UI
    const domSymbol = symbol.replace(" WTI OIL", "-WTI-OIL").replace(" OIL", "-OIL").replace(" ", "-");
    const priceId = type === 'buy' ? `ticker-ask-${domSymbol}` : `ticker-bid-${domSymbol}`;
    const priceEl = document.getElementById(priceId);
    const currentPrice = priceEl ? priceEl.innerText : '...';
    document.getElementById('order-current-price').innerText = currentPrice;
    
    // Reset values
    document.getElementById('order-volume-input').value = 0.01;
    document.getElementById('order-sl-input').value = '';
    document.getElementById('order-tp-input').value = '';
    
    document.getElementById('order-modal').style.display = 'flex';
}

function closeOrderModal() {
    document.getElementById('order-modal').style.display = 'none';
    activeOrderSymbol = null;
    activeOrderType = null;
}

async function submitOrder() {
    if (!activeOrderSymbol || !activeOrderType) return;
    const volume = parseFloat(document.getElementById('order-volume-input').value);
    const sl = parseFloat(document.getElementById('order-sl-input').value) || null;
    const tp = parseFloat(document.getElementById('order-tp-input').value) || null;
    
    try {
        const btn = document.getElementById('order-submit-btn');
        btn.disabled = true;
        btn.innerText = "Placing...";
        
        const res = await fetch('/api/trade/place_order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: activeOrderSymbol, type: activeOrderType, volume, sl, tp })
        });
        
        const result = await res.json();
        btn.disabled = false;
        btn.innerText = "Place Order";
        
        if (result.status === 'success') {
            alert(result.message);
            closeOrderModal();
            fetchStatus();
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch(err) {
        alert(`Request failed: ${err}`);
        document.getElementById('order-submit-btn').disabled = false;
        document.getElementById('order-submit-btn').innerText = "Place Order";
    }
}
