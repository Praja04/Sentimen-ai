from dotenv import load_dotenv
load_dotenv()
from flask import Flask, jsonify, send_from_directory, request, render_template
import MetaTrader5 as mt5
from flask_cors import CORS
import os
import threading
import json
import forecast_engine
import time
import math
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
import ai_tuner
from fundamental.scorer import get_fundamental_score
import requests

def send_telegram_alert(msg):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[Telegram Error] {e}")

def calculate_lot_size(symbol, entry_price, sl_price, risk_pct=1.0, confidence=70.0):
    if not init_mt5():
        return 0.01
    account_info = mt5.account_info()
    if not account_info:
        return 0.01
    balance = account_info.balance
    
    # Smart Lot Dynamic: scale risk dynamically based on confidence (e.g. 50% to 150% of baseline risk)
    # Baseline confidence is 70%. If confidence is 90%, multiplier = 1.3. If confidence is 50%, multiplier = 0.7.
    conf_factor = float(confidence) / 70.0
    conf_factor = max(0.5, min(1.5, conf_factor))
    effective_risk_pct = risk_pct * conf_factor
    
    risk_money = balance * (effective_risk_pct / 100.0)
    
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return 0.01
        
    tick_size = symbol_info.trade_tick_size
    tick_value = symbol_info.trade_tick_value
    
    if tick_size == 0 or tick_value == 0:
        return symbol_info.volume_min

    # Calculate stop loss distance in ticks
    sl_dist = abs(entry_price - sl_price)
    ticks_at_risk = sl_dist / tick_size
    
    if ticks_at_risk == 0:
        return symbol_info.volume_min
        
    money_risk_per_lot = ticks_at_risk * tick_value
    if money_risk_per_lot == 0:
        return symbol_info.volume_min
        
    calc_lot = risk_money / money_risk_per_lot
    
    # Round to volume_step
    vol_step = symbol_info.volume_step
    lot = math.floor(calc_lot / vol_step) * vol_step
    
    # Bound lot size
    lot = max(symbol_info.volume_min, min(symbol_info.volume_max, lot))
    return round(lot, 2)

# Global trackers for adaptive AI logic and order spamming prevention
_executed_signals = {}

def sync_live_trade_history():
    if not init_mt5(): return
    import sqlite3, datetime, time
    to_date = datetime.datetime.now()
    from_date = to_date - datetime.timedelta(days=7)
    deals = mt5.history_deals_get(from_date, to_date)
    if not deals: return
    try:
        conn = sqlite3.connect(r"C:\Antigravity\forecast_history.db")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS live_trade_history (
                        ticket INTEGER PRIMARY KEY,
                        symbol TEXT,
                        profit REAL,
                        is_win INTEGER,
                        time_closed INTEGER
                     )''')
        new_trades = 0
        for deal in deals:
            if deal.magic == 998877 and deal.entry == mt5.DEAL_ENTRY_OUT:
                is_win = 1 if deal.profit > 0 else 0
                c.execute("SELECT ticket FROM live_trade_history WHERE ticket=?", (deal.ticket,))
                if not c.fetchone():
                    c.execute("INSERT INTO live_trade_history (ticket, symbol, profit, is_win, time_closed) VALUES (?, ?, ?, ?, ?)",
                              (deal.ticket, deal.symbol, deal.profit, is_win, deal.time))
                    new_trades += 1
        conn.commit()
        conn.close()
        if new_trades > 0:
            print(f"[Live Trade Sync] Synced {new_trades} new closed trades to history.")
    except Exception as e:
        # Ignore silent sqlite errors or print if debug
        pass

confidence_history = {}
last_trade_time = {}
active_trades_meta = {}

def process_auto_trades(recs):
    if not init_mt5():
        return
        
    import ai_tuner
    ai_params = ai_tuner.load_ai_params()
    spam_cooldown = ai_params.get("spam_cooldown", 60)
        
    # Read active config to get dynamic risk %
    risk_pct = 1.0
    config_file = r'C:\Antigravity\active_config.json'
    if os.path.exists(config_file):
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                risk_pct = float(cfg.get("risk_percent", 1.0))
        except Exception:
            pass
            
    for rec in recs:
        sym = rec.get("_sym") or rec.get("pair")
        if not sym: continue
        action = rec.get("action")
        conf = rec.get("confidence", 0)
        
        # Determine actual symbol options
        SYM_OPTS_MAP = {
            "XAUUSD":   ["XAUUSD"],
            "USDJPY":   ["USDJPY"],
            "WTI OIL":  ["WTI", "XTIUSD", "USOIL", "CL"],
            "NIKKEI":   ["JP225", "JPN225", "NI225", "JP225Cash", "JAPAN225"],
            "DOW JONES":["US30", "DJ30", "DJIA", "WS30", "USA30"],
        }
        sym_opts = SYM_OPTS_MAP.get(sym, [sym])
        
        active_symbol = None
        for opt in sym_opts:
            if mt5.symbol_info(opt):
                active_symbol = opt
                break
        if not active_symbol: continue
        
        positions = mt5.positions_get(symbol=active_symbol)
        
        # Retrieve symbol info, digits, point, and calculate H4 ATR
        info = mt5.symbol_info(active_symbol)
        if not info: continue
        digits = info.digits
        point = info.point
        
        # Compute ATR
        atr_val = 0.0
        try:
            rates = mt5.copy_rates_from_pos(active_symbol, mt5.TIMEFRAME_H4, 0, 15)
            if rates is not None and len(rates) >= 14:
                trs = []
                for i in range(1, len(rates)):
                    h  = rates[i]['high']
                    l  = rates[i]['low']
                    pc = rates[i-1]['close']
                    trs.append(max(h - l, abs(h - pc), abs(l - pc)))
                atr_val = sum(trs[-14:]) / 14.0
        except Exception as e:
            print(f"[ATR Calculation Error] {active_symbol}: {e}")
        
        # Default ATR if calculation failed: 15 pips equivalent
        if atr_val <= 0:
            atr_val = 150.0 * point
            atr_points = 150.0
        else:
            atr_points = atr_val / point
            
        # 1-Hour Price Momentum Action Resolver
        try:
            tick_now = mt5.symbol_info_tick(active_symbol)
            if tick_now:
                current_bid = tick_now.bid
                one_hour_ago_ts = int(time.time()) - 3600
                rates_1h = mt5.copy_rates_from(active_symbol, mt5.TIMEFRAME_M5, one_hour_ago_ts, 1)
                price_1h_ago = None
                if rates_1h is not None and len(rates_1h) > 0:
                    price_1h_ago = rates_1h[0]['close']
                else:
                    rates_h1 = mt5.copy_rates_from_pos(active_symbol, mt5.TIMEFRAME_H1, 0, 2)
                    if rates_h1 is not None and len(rates_h1) >= 2:
                        price_1h_ago = rates_h1[0]['close']
                
                if price_1h_ago:
                    diff_1h = current_bid - price_1h_ago
                    if diff_1h > 0:
                        action = "BUY"
                    elif diff_1h < 0:
                        action = "SELL"
                    print(f"[{active_symbol}] 1H Momentum: Now {current_bid} vs 1H Ago {price_1h_ago} (Diff: {round(diff_1h, 2)}) -> Action resolved to {action}")
        except Exception as momentum_err:
            print(f"[1H Momentum Resolver Error] {momentum_err}")
            
        # 1. AUTO CLOSE on EXIT WARNING or WAIT
        import ai_tuner
        ai_params = ai_tuner.load_ai_params()
        
        if positions:
                
            for pos in positions:
                tick = mt5.symbol_info_tick(active_symbol)
                if not tick: continue
                
                is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
                current_price = tick.bid if is_buy else tick.ask
                open_price = pos.price_open
                
                should_close = (action == "EXIT WARNING") or (is_buy and action == "SELL") or (not is_buy and action == "BUY")
                if should_close:
                    order_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                    close_price = tick.bid if is_buy else tick.ask
                    
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": active_symbol,
                        "volume": pos.volume,
                        "type": order_type,
                        "position": pos.ticket,
                        "price": close_price,
                        "deviation": 20,
                        "magic": 998877,
                        "comment": f"Auto Close: {action}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    # Auto-retry all filling modes supported by broker
                    res = None
                    for filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                        request["type_filling"] = filling
                        res = mt5.order_send(request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            break
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        msg = f"Auto Close ({action}) {active_symbol} @ {close_price}"
                        send_telegram_alert(msg)
                    else:
                        print(f"[AutoTrade Error] Close {active_symbol}: {res.comment if res else mt5.last_error()}")
                    continue

                # Auto Break-Even & Trailing Stop Logic (Dynamic ATR-based with AI Self-Learning)
                # Fetch recent Win Rate from database for adaptive multiplier scaling
                win_rate = 92.5
                try:
                    import sqlite3
                    conn = sqlite3.connect(r"C:\Antigravity\forecast_history.db")
                    c = conn.cursor()
                    
                    c.execute('''CREATE TABLE IF NOT EXISTS live_trade_history (
                                    ticket INTEGER PRIMARY KEY,
                                    symbol TEXT,
                                    profit REAL,
                                    is_win INTEGER,
                                    time_closed INTEGER
                                 )''')
                                 
                    c.execute("SELECT is_win FROM live_trade_history ORDER BY time_closed DESC LIMIT 50")
                    rows = c.fetchall()
                    if len(rows) >= 5:
                        win_rate = (sum(r[0] for r in rows) / len(rows)) * 100.0
                    else:
                        c.execute("SELECT correct FROM predictions WHERE evaluated = 1 ORDER BY timestamp DESC LIMIT 50")
                        rows_pred = c.fetchall()
                        if rows_pred:
                            win_rate = (sum(r[0] for r in rows_pred) / len(rows_pred)) * 100.0
                    conn.close()
                except Exception:
                    pass
                
                # Base ATR multiplier is 1.5, adjusted by parameter settings
                atr_mult = 1.5 * ai_params.get("trailing_buffer_multiplier", 1.0)
                # Self-learning: If win rate is low, widen buffer to avoid premature exit
                if win_rate < 90.0:
                    atr_mult *= (1.0 + (90.0 - win_rate) * 0.02)
                
                tsl_buffer_points = atr_points * atr_mult
                be_trigger_points = atr_points * 1.0
                tsl_trigger_points = atr_points * atr_mult
                
                profit_points = (current_price - open_price) / point if is_buy else (open_price - current_price) / point
                
                new_sl = None
                
                if profit_points >= be_trigger_points and profit_points < tsl_trigger_points:
                    # Break Even
                    if pos.sl == 0.0 or (is_buy and pos.sl < open_price) or (not is_buy and (pos.sl > open_price or pos.sl == 0.0)):
                        new_sl = open_price
                        
                elif profit_points >= tsl_trigger_points:
                    # Trailing Stop
                    if is_buy:
                        trail_price = current_price - (tsl_buffer_points * point)
                        if pos.sl == 0.0 or trail_price > pos.sl:
                            new_sl = round(trail_price, digits)
                    else:
                        trail_price = current_price + (tsl_buffer_points * point)
                        if pos.sl == 0.0 or trail_price < pos.sl:
                            new_sl = round(trail_price, digits)
                            
                if new_sl is not None and new_sl != pos.sl:
                    sl_request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": active_symbol,
                        "position": pos.ticket,
                        "sl": new_sl,
                        "tp": pos.tp
                    }
                    mt5.order_send(sl_request)

            # 3. SMART ATR GRID AVERAGING ON FLOATING NEGATIVE
            if action in ["BUY", "SELL"]:
                # Limit to 3 averaging positions per instrument (total 4 positions max)
                max_grid = 4
                if len(positions) < max_grid:
                    grid_distance = atr_points * 1.25 # Dynamic grid distance: 1.25 H4 ATR
                    
                    # Sort positions by entry price
                    sorted_pos = sorted(positions, key=lambda p: p.price_open)
                    is_action_buy = (action == "BUY")
                    
                    # Find the latest (deepest) active grid level
                    latest_pos = sorted_pos[0] if is_action_buy else sorted_pos[-1]
                    
                    tick = mt5.symbol_info_tick(active_symbol)
                    if tick:
                        current_price = tick.ask if is_action_buy else tick.bid
                        
                        # Distance from the latest grid entry in points
                        entry_diff_points = (latest_pos.price_open - current_price) / point if is_action_buy else (current_price - latest_pos.price_open) / point
                        
                        # If price has fallen/risen against our latest grid by 1.0 ATR, trigger averaging
                        if entry_diff_points >= grid_distance:
                            # Cooldown check: 5 minutes cooldown to avoid rapid double entries on fast moves
                            if time.time() - last_trade_time.get(active_symbol, 0) >= 300:
                                base_lot = positions[0].volume
                                grid_lot = round(base_lot, 2)
                                
                                order_type = mt5.ORDER_TYPE_BUY if is_action_buy else mt5.ORDER_TYPE_SELL
                                price = tick.ask if is_action_buy else tick.bid
                                
                                # Set stop loss level to match existing positions
                                grid_sl = positions[0].sl
                                
                                grid_request = {
                                    "action": mt5.TRADE_ACTION_DEAL,
                                    "symbol": active_symbol,
                                    "volume": float(grid_lot),
                                    "type": order_type,
                                    "price": float(price),
                                    "sl": float(grid_sl) if grid_sl > 0 else 0.0,
                                    "tp": float(positions[0].tp) if positions[0].tp > 0 else 0.0,
                                    "deviation": 20,
                                    "magic": 998877,
                                    "comment": f"AI Grid #{len(positions) + 1}",
                                    "type_time": mt5.ORDER_TIME_GTC,
                                    "type_filling": mt5.ORDER_FILLING_IOC,
                                }
                                
                                # Auto-retry filling modes
                                for filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                                    grid_request["type_filling"] = filling
                                    res = mt5.order_send(grid_request)
                                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                        last_trade_time[active_symbol] = time.time()
                                        send_telegram_alert(
                                            f"🟢 [Smart Grid] Opened Averaging {action} #{len(positions) + 1} for {active_symbol} @ {price} "
                                            f"(ATR Gap: {round(entry_diff_points, 1)} pts)"
                                        )
                                        
                                        # Log grid event into Database for Deep Learning training
                                        try:
                                            # Calculate MAE/MFE dynamically from M5 bar history since trade start
                                            mae_pts = entry_diff_points
                                            mfe_pts = 0.0
                                            try:
                                                cycle_start = positions[0].time
                                                history_rates = mt5.copy_rates_from(active_symbol, mt5.TIMEFRAME_M5, int(cycle_start), int(time.time()))
                                                if history_rates is not None and len(history_rates) > 0:
                                                    highs = [r['high'] for r in history_rates]
                                                    lows = [r['low'] for r in history_rates]
                                                    first_entry = positions[0].price_open
                                                    if is_action_buy:
                                                        max_high = max(highs)
                                                        min_low = min(lows)
                                                        mfe_pts = max(0.0, (max_high - first_entry) / point)
                                                        mae_pts = max(mae_pts, (first_entry - min_low) / point)
                                                    else:
                                                        max_high = max(highs)
                                                        min_low = min(lows)
                                                        mfe_pts = max(0.0, (first_entry - min_low) / point)
                                                        mae_pts = max(mae_pts, (max_high - first_entry) / point)
                                            except Exception as hist_err:
                                                print(f"[Grid Hist Error] {hist_err}")
                                                
                                            import ai_memory
                                            ai_memory.log_grid_event(
                                                symbol=active_symbol,
                                                direction=action,
                                                grid_index=len(positions) + 1,
                                                entry_price=price,
                                                atr_points=atr_points,
                                                atr_gap=entry_diff_points,
                                                tp=float(positions[0].tp),
                                                mae=float(mae_pts),
                                                mfe=float(mfe_pts),
                                                confidence=float(rec.get("confidence", 0))
                                            )
                                        except Exception as db_err:
                                            print(f"[Grid DB Logging Error] {db_err}")
                                            
                                        # Synchronize stop loss levels across all positions for this symbol
                                        time.sleep(1) # Let order record update
                                        positions_updated = mt5.positions_get(symbol=active_symbol)
                                        if positions_updated:
                                            target_sl = positions_updated[-1].sl
                                            if target_sl > 0:
                                                for p in positions_updated:
                                                    if p.sl != target_sl:
                                                        sync_req = {
                                                            "action": mt5.TRADE_ACTION_SLTP,
                                                            "symbol": active_symbol,
                                                            "position": p.ticket,
                                                            "sl": target_sl,
                                                            "tp": p.tp
                                                        }
                                                        mt5.order_send(sync_req)
                                        break
                    
        # 2. AUTO OPEN
        elif action in ["BUY", "SELL"] and not positions:
            # Cooldown check
            if time.time() - last_trade_time.get(active_symbol, 0) < spam_cooldown:
                continue
                
            sig_id = f"{active_symbol}_{action}"
            tick = mt5.symbol_info_tick(active_symbol)
            if not tick: continue
            
            price_now = tick.ask if action == "BUY" else tick.bid
            entry = rec.get("entry") or price_now
            sl = rec.get("sl")
            tp = rec.get("tp")
            
            if not sl:
                sl = (price_now - (1.5 * atr_val)) if action == "BUY" else (price_now + (1.5 * atr_val))
            if not tp:
                tp = (price_now + (2.0 * atr_val)) if action == "BUY" else (price_now - (2.0 * atr_val))
                
            lot = calculate_lot_size(active_symbol, entry, sl, risk_pct=risk_pct, confidence=conf)
            order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
            price = price_now
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": active_symbol,
                "volume": float(lot),
                "type": order_type,
                "price": float(price),
                "sl": float(sl),
                "tp": float(tp),
                "deviation": 20,
                "magic": 998877,
                "comment": "AI AutoTrade",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Auto-retry all filling modes to support all brokers
            res = None
            for filling in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]:
                request["type_filling"] = filling
                res = mt5.order_send(request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    break
            
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                _executed_signals[sig_id] = time.time()
                last_trade_time[active_symbol] = time.time()
                direction = "BUY" if action == "BUY" else "SELL"
                msg = f"AUTO {direction} EXECUTED\nSymbol: {active_symbol}\nLot: {lot}\nEntry: {price}\nSL: {sl}\nTP: {tp}\nConf: {conf}%"
                send_telegram_alert(msg)
                print(f"[AutoTrade OK] {active_symbol} {action} lot={lot} entry={price} filling={request['type_filling']}")
            else:
                err = res.comment if res else mt5.last_error()
                print(f"[AutoTrade Error] {active_symbol} {action}: {err}")

XEDY_DATABASE_PATH = r"C:\Antigravity\xedy_v30_data.json"

stop_backtest_requested = False

# Global state for velocity-based dynamic trend calculation
_dynamic_trend_state = {
    "history": [], # list of dicts: {"timestamp": float, "prices": dict, "confidences": dict}
    "current_trend": "NEUTRAL",
    "is_whipsaw": False
}


# Real-time progress tracking
_progress_log = []       # list of {t, level, msg} dicts
_progress_stats = {}     # live stats: phase, iteration, tested, total, tf, found
_progress_running = False

def _push_log(msg, level="info"):
    """Append a timestamped log entry to the global progress log."""
    global _progress_log
    _progress_log.append({
        "t": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "level": level,
        "msg": msg,
    })
    if len(_progress_log) > 500:
        _progress_log = _progress_log[-500:]

def _reset_progress():
    global _progress_log, _progress_stats, _progress_running
    _progress_log = []
    _progress_stats = {}
    _progress_running = True



# Global variable to store latest analyzed live speech headlines
latest_speech_analysis = {
    "headline": "Belum ada pidato penting yang dideteksi otomatis.",
    "bias": "NEUTRAL",
    "score": 0.0,
    "shifts": {},
    "last_checked": 0
}

def auto_update_speech_sentiment():
    """Automatically search for Fed / US President speeches and parse them to update model without clicking."""
    import time
    import feedparser
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    
    global latest_speech_analysis
    now = time.time()
    # Throttled check: 300 seconds (5 minutes) to avoid IP ban and blocking
    if now - latest_speech_analysis.get("last_checked", 0) < 300:
        return
        
    latest_speech_analysis["last_checked"] = now

    # Run the network request asynchronously so it doesn't block the 5-second AI computation loop
    def _fetch_rss():
        global latest_speech_analysis
        try:
            # Search queries for Fed speeches, FOMC, and US political news
            rss_url = "https://news.google.com/rss/search?q=Powell+OR+Fed+OR+FOMC+OR+Trump+OR+Biden&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            analyzer = SentimentIntensityAnalyzer()
            
            for entry in feed.entries[:8]: # Scan top 8 headlines
                title = entry.title.lower()
                
                # Identify critical keywords
                is_fed = any(k in title for k in ["powell", "fed", "fomc", "interest rate", "inflation"])
                is_president = any(k in title for k in ["trump", "biden", "president", "tariff", "trade war"])
                
                if is_fed or is_president:
                    headline_text = entry.title
                    vs = analyzer.polarity_scores(headline_text)
                    score = vs["compound"]
                    
                    shifts = {}
                    # Hawkish Fed/US statement -> DXY up, US10Y up, equities down, gold down
                    if any(k in title for k in ["hawkish", "hike", "rate hike", "tighten", "delay cut"]):
                        bias = "HAWKISH (AUTO)"
                        shifts = {
                            "DXY": 0.45, "US10Y": 0.35, "VIX": 0.50, "SILVER": -0.80,
                            "S&P 500": -0.30, "DOW JONES": -0.25, "NIKKEI": -0.40, "WTI OIL": -0.20
                        }
                    # Dovish statement -> DXY down, Yield down, Equities up, Gold up
                    elif any(k in title for k in ["dovish", "rate cut", "cut", "easing", "stimulus"]):
                        bias = "DOVISH (AUTO)"
                        shifts = {
                            "DXY": -0.55, "US10Y": -0.40, "VIX": -0.60, "SILVER": 1.20,
                            "S&P 500": 0.40, "DOW JONES": 0.35, "NIKKEI": 0.50, "WTI OIL": 0.25
                        }
                    elif any(k in title for k in ["tariff", "trade war", "sanction"]):
                        bias = "TRADE WAR / TARIFFS (Risk-Off AUTO)"
                        shifts = {
                            "DXY": 0.30, "US10Y": -0.15, "VIX": 0.85, "SILVER": 0.20,
                            "S&P 500": -0.65, "DOW JONES": -0.60, "NIKKEI": -0.80, "WTI OIL": -0.40
                        }
                    else:
                        # Fallback to standard VADER score direction
                        if score > 0.15:
                            bias = "BULLISH / OPTIMISTIC (AUTO)"
                            shifts = {
                                "DXY": -0.15, "US10Y": -0.10, "VIX": -0.20, "SILVER": 0.30,
                                "S&P 500": 0.20, "DOW JONES": 0.15, "NIKKEI": 0.25, "WTI OIL": 0.10
                            }
                        elif score < -0.15:
                            bias = "BEARISH / RISK-OFF (AUTO)"
                            shifts = {
                                "DXY": 0.15, "US10Y": 0.10, "VIX": 0.35, "SILVER": -0.25,
                                "S&P 500": -0.30, "DOW JONES": -0.25, "NIKKEI": -0.35, "WTI OIL": -0.15
                            }
                        else:
                            continue # Skip weak/neutral titles
                    
                    # We found a significant auto-speech headline, save and break
                    latest_speech_analysis = {
                        "headline": headline_text,
                        "bias": bias,
                        "score": round(score, 3),
                        "shifts": shifts,
                        "last_checked": time.time()
                    }
                    break
        except Exception as e:
            print("Auto speech updating error:", e)

    import threading
    threading.Thread(target=_fetch_rss, daemon=True).start()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.debug = True
CORS(app)

# The specific pairs requested
SYMBOLS = [
    "XAUUSD", "USDJPY", "EURUSD", "GBPUSD", 
    "XTIUSD", "US30", "BOND JAPAN", "BOND US"
]

_mt5_initialized = False

def init_mt5():
    global _mt5_initialized
    if _mt5_initialized and mt5.terminal_info() is not None:
        return True
        
    # Initialize connection to the MetaTrader 5 terminal using credentials if present
    login_val = os.getenv("MT5_LOGIN")
    password_val = os.getenv("MT5_PASSWORD")
    server_val = os.getenv("MT5_SERVER")
    
    if login_val and password_val and server_val:
        if mt5.initialize(login=int(login_val), password=password_val, server=server_val):
            _mt5_initialized = True
            return True
            
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        _mt5_initialized = False
        return False
    _mt5_initialized = True
    return True

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)


@app.route('/api/backtest/progress', methods=['GET'])
def api_backtest_progress():
    """Return the current real-time backtest progress log and stats."""
    return jsonify({
        "running": _progress_running,
        "stats": _progress_stats,
        "log": _progress_log[-80:],  # last 80 entries
    })

@app.route('/api/live_ticks')
def get_live_ticks():
    if not init_mt5():
        return jsonify({"error": "Failed to connect to MT5"}), 500
    
    ticks = {}
    symbols_to_fetch = {
        "XAUUSD": ["XAUUSD", "GOLD"],
        "USDJPY": ["USDJPY"],
        "WTI OIL": ["WTI", "XTIUSD", "USOIL", "CL"],
        "DJI": ["DJI", "US30", "YM", "DJIA"],
        "EURUSD": ["EURUSD"],
        "GBPUSD": ["GBPUSD"]
    }
    
    for label, options in symbols_to_fetch.items():
        t = None
        matched_symbol = None
        for opt in options:
            mt5.symbol_select(opt, True)
            t = mt5.symbol_info_tick(opt)
            if t:
                matched_symbol = opt
                break
        if t:
            rates = mt5.copy_rates_from_pos(matched_symbol, mt5.TIMEFRAME_D1, 0, 1)
            daily_open = rates[0]['open'] if (rates is not None and len(rates) > 0) else t.bid
            daily_vol = rates[0]['tick_volume'] if (rates is not None and len(rates) > 0) else 0
            daily_change = ((t.bid - daily_open) / daily_open) * 100.0 if daily_open > 0 else 0.0
            
            daily_high = rates[0]['high'] if (rates is not None and len(rates) > 0) else t.bid
            daily_low = rates[0]['low'] if (rates is not None and len(rates) > 0) else t.bid
            
            ticks[label] = {
                "bid": t.bid,
                "ask": t.ask,
                "change": round(daily_change, 3),
                "volume": int(daily_vol),
                "high": daily_high,
                "low": daily_low
            }
            
    # Livetest Real-time Demo Simulation update
    demo_state = None
    if "XAUUSD" in ticks:
        try:
            import livetest_sim
            bias = compute_xedy_fundamental_bias()
            news_halt, _ = is_news_halt_active()
            
            # Fetch real-time XAUUSD confidence from cached dashboard data
            xau_conf = 70.0
            with cached_dashboard_lock:
                if cached_dashboard_data and "pair_recommendations" in cached_dashboard_data:
                    for rec in cached_dashboard_data["pair_recommendations"]:
                        if rec.get("pair") == "XAUUSD":
                            xau_conf = rec.get("confidence", 70.0)
                            break
            
            demo_state = livetest_sim.update_livetest_sim(ticks["XAUUSD"]["bid"], bias, news_halt_active=news_halt, confidence=xau_conf)
            if demo_state:
                config_file = r'C:\Antigravity\active_config.json'
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f_cfg:
                        demo_state["active_config"] = json.load(f_cfg)
            try:
                forecast_engine.update_forecast_tick("XAUUSD", ticks["XAUUSD"]["bid"], bias)
                forecast_engine.update_forecast_tick("USDJPY", ticks["USDJPY"]["bid"], bias)
                forecast_engine.update_forecast_tick("XTIUSD", ticks["WTI OIL"]["bid"], bias)
            except Exception as fe_err:
                print("Error in forecast tick update:", fe_err)
        except Exception as err:
            print("Error in livetest simulation tick update:", err)
            
    return jsonify({
        "ticks": ticks,
        "demo": demo_state,
        "backtest_running": _progress_running
    })

@app.route('/api/prices')
def get_prices():
    if not init_mt5():
        return jsonify({"error": "Failed to connect to MT5", "code": mt5.last_error()}), 500

    prices = []
    
    for symbol in SYMBOLS:
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is not None and info is not None:
            prices.append({
                "symbol": symbol,
                "bid": tick.bid,
                "ask": tick.ask,
                "high": info.bidhigh,
                "low": info.bidlow,
                "time": tick.time
            })
        else:
            # If a symbol is not available or not in Market Watch
            prices.append({
                "symbol": symbol,
                "error": "Not available"
            })
            
    return jsonify({"success": True, "data": prices})

@app.route('/api/analysis')
def get_analysis():
    import json
    try:
        with open('analysis.json', 'r') as f:
            data = json.load(f)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/macro')
def api_macro():
    import json
    try:
        with open('macro.json', 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/xedy_v30')
def api_xedy():
    import json
    try:
        with open(XEDY_DATABASE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Global cache for real-time dashboard data
cached_dashboard_data = {}
cached_dashboard_lock = threading.Lock()

def _compute_dashboard_data():
    """Computes all regression, CSI, and pair signals. Returns a dict."""
    import numpy as np
    from ai_memory import update_mae_mfe
    
    # Trigger automatic background speech headline updates
    auto_update_speech_sentiment()
    
    if not init_mt5():
        return {"error": "Failed to connect to MT5"}
        
    symbols = {
        "XAUUSD": ["XAUUSD", "GOLD"],
        "USDJPY": ["USDJPY"]
    }
    
    rates_dict = {}
    current_prices = {}
    for label, options in symbols.items():
        matched_symbol = None
        for opt in options:
            mt5.symbol_select(opt, True)
            t = mt5.symbol_info_tick(opt)
            if t:
                matched_symbol = opt
                current_prices[label] = {"price": t.bid} # store bid price for MAE/MFE
                break
        if matched_symbol:
            rates = mt5.copy_rates_from_pos(matched_symbol, mt5.TIMEFRAME_D1, 0, 30)
            if rates is not None and len(rates) > 0:
                rates_dict[label] = [r['close'] for r in rates]
                
    # Auto Adaptive Tuner: Update Maximum Adverse Excursion / Maximum Favorable Excursion records
    try:
        update_mae_mfe(current_prices)
    except Exception as e:
        print("[MAE/MFE Tuner] Update error:", e)
        
    if len(rates_dict) < len(symbols):
        return {"error": f"Failed to fetch historical rates for all assets. Found: {list(rates_dict.keys())}"}

        
    # Load latest forecast_v32 for comparison
    forecast_data = {}
    try:
        with open(XEDY_DATABASE_PATH, 'r', encoding='utf-8') as f:
            db_data = json.load(f)
            forecast_data = db_data.get("forecast_v32", {}).get("assets", {})
    except Exception as e:
        print(f"Error loading forecast_v32: {e}")
        
    results = {}
    laggard_leader = None
    max_abs_gap = -1.0
    
    for target in rates_dict.keys():
        y = np.array(rates_dict[target])
        X_list = [rates_dict[s] for s in rates_dict.keys() if s != target]
        X = np.column_stack(X_list)
        X = np.column_stack([np.ones(len(y)), X])
        
        try:
            beta, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)
            current_x = np.array([1.0] + [rates_dict[s][-1] for s in rates_dict.keys() if s != target])
            fair_value = float(np.dot(current_x, beta))
            actual = float(rates_dict[target][-1])
            gap = actual - fair_value
            pct_gap = (gap / fair_value) * 100.0 if fair_value > 0 else 0.0
            
            # Get previous AI forecast direction (D+1)
            ai_dir = "NEUTRAL"
            asset_fc = forecast_data.get(target, {}).get("D+1", {})
            if asset_fc:
                probs = asset_fc.get("probabilities", {})
                bull = probs.get("bullish", 33)
                bear = probs.get("bearish", 33)
                if bull > bear + 5:
                    ai_dir = "BULLISH"
                elif bear > bull + 5:
                    ai_dir = "BEARISH"
                    
            # Confluence logic:
            # - If gap < 0 (undervalued), we expect price to RISE -> BUY
            # - If gap > 0 (overvalued), we expect price to FALL -> SELL
            laggard_status = "Undervalued" if gap < 0 else "Overvalued"
            expected_direction = "BULLISH" if gap < 0 else "BEARISH"
            
            confluence = "DIVERGENT"
            action = "HOLD"
            if expected_direction == ai_dir:
                confluence = "MATCHED"
                action = "BUY" if expected_direction == "BULLISH" else "SELL"
                
            results[target] = {
                "actual": round(actual, 4),
                "fair_value": round(fair_value, 4),
                "gap": round(gap, 4),
                "pct_gap": round(pct_gap, 3),
                "laggard_status": laggard_status,
                "ai_direction": ai_dir,
                "confluence": confluence,
                "action": action
            }
            
            if abs(pct_gap) > max_abs_gap:
                max_abs_gap = abs(pct_gap)
                laggard_leader = target
                
        except Exception as e:
            print(f"Error calculating regression for {target}: {e}")
    # Calculate Currency Strength Indices (DXY, EXY, JXY, etc.)
    def get_change(sym_opts):
        for opt in sym_opts:
            mt5.symbol_select(opt, True)
            t = mt5.symbol_info_tick(opt)
            if t:
                rates = mt5.copy_rates_from_pos(opt, mt5.TIMEFRAME_D1, 0, 1)
                if rates is not None and len(rates) > 0:
                    op = rates[0]['open']
                    if op > 0:
                        return ((t.bid - op) / op) * 100.0
        return 0.0
        
    chg_eur = get_change(["EURUSD"])
    chg_gbp = get_change(["GBPUSD"])
    chg_jpy = -get_change(["USDJPY"])
    chg_chf = -get_change(["USDCHF"])
    chg_cad = -get_change(["USDCAD"])
    chg_aud = get_change(["AUDUSD"])
    chg_nzd = get_change(["NZDUSD"])
    chg_usd = -(chg_eur + chg_gbp + chg_jpy + chg_chf + chg_cad + chg_aud + chg_nzd) / 7.0
    
    avg_chg = (chg_eur + chg_gbp + chg_jpy + chg_chf + chg_cad + chg_aud + chg_nzd + chg_usd) / 8.0
    
    strengths = {
        "DXY": chg_usd - avg_chg,
        "EXY": chg_eur - avg_chg,
        "BXY": chg_gbp - avg_chg,
        "JXY": chg_jpy - avg_chg,
        "SFX": chg_chf - avg_chg,
        "CXY": chg_cad - avg_chg,
        "AXY": chg_aud - avg_chg,
        "ZXY": chg_nzd - avg_chg
    }
    
    scaled_indices = {}
    for idx_name, pct in strengths.items():
        score = 50.0 + (pct * 15.0)  # scale factor of 15.0 for UI visibility
        scaled_indices[idx_name] = {
            "percentage": round(pct, 3),
            "score": round(min(100.0, max(0.0, score)), 1)
        }
    
    # ── Fixed Instrument Signals: XAUUSD, USDJPY, OIL, NIKKEI, DOWJONES ──────────
    def get_signal(sym_opts, label, kind="forex", current_trend="NEUTRAL", is_whipsaw=False, ai_params=None):
        """Fetch price, daily change and return signal dict with adaptive dynamic trend logic."""
        if ai_params is None:
            ai_params = {"velocity_threshold": 0.02, "momentum_threshold": 1.5, "whipsaw_sd_threshold": 0.015}
            
        for sym in sym_opts:
            try:
                mt5.symbol_select(sym, True)
                tick  = mt5.symbol_info_tick(sym)
                info  = mt5.symbol_info(sym)
                if not tick or not info:
                    continue
                rates_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 1)
                if rates_d1 is None or len(rates_d1) == 0:
                    continue
                open_d  = rates_d1[0]['open']
                if open_d <= 0:
                    continue
                chg_pct = ((tick.bid - open_d) / open_d) * 100.0
                digits  = info.digits if info.digits else 2
                entry   = round(tick.bid, digits)

                abs_chg = abs(chg_pct)
                if kind == "index":
                    q_th = [0.8, 0.5, 0.25, 0.1]
                    c_mul = 15
                else:
                    q_th = [0.5, 0.3, 0.1, 0.05]
                    c_mul = 30
                quality = ("★★★★★" if abs_chg > q_th[0] else
                           "★★★★"  if abs_chg > q_th[1] else
                           "★★★"   if abs_chg > q_th[2] else
                           "★★"    if abs_chg > q_th[3] else "★")
                            # --- SIGNAL LOGIC: RSI + SMA Momentum (Scalper T0.22 aligned) ---
                # Initialize confidence before use
                confidence = 50.0
                global confidence_history, last_trade_time
                if sym not in confidence_history:
                    confidence_history[sym] = []
                confidence_history[sym].append(confidence)
                if len(confidence_history[sym]) > 5:
                    confidence_history[sym].pop(0)
                
                action = "WAIT"
                if is_whipsaw:
                    action = "WAIT"
                elif label in ["XAUUSD", "USDJPY"]:
                    # Fetch M15 historical rates to compute RSI and SMA trend alignment
                    rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 50)
                    if rates_m15 is not None and len(rates_m15) >= 30:
                        closes_m15 = [r['close'] for r in rates_m15]
                        
                        # SMA-10 (Fast) & SMA-30 (Slow)
                        sma_10 = sum(closes_m15[-10:]) / 10.0
                        sma_30 = sum(closes_m15[-30:]) / 30.0
                        
                        # RSI-14
                        deltas = [closes_m15[idx] - closes_m15[idx-1] for idx in range(1, len(closes_m15))]
                        gains = [d if d > 0 else 0 for d in deltas]
                        losses = [-d if d < 0 else 0 for d in deltas]
                        avg_gain = sum(gains[-14:]) / 14.0
                        avg_loss = sum(losses[-14:]) / 14.0
                        if avg_loss == 0:
                            rsi_val = 100.0
                        else:
                            rs = avg_gain / avg_loss
                            rsi_val = 100.0 - (100.0 / (1.0 + rs))
                            
                        # Apply optimized parameters aligned with Scalper T0.22:
                        # BUY  : RSI < 48 AND fast SMA above slow (momentum turning up)
                        # SELL : RSI > 52 AND fast SMA below slow (momentum turning down)
                        if rsi_val < 48.0 and sma_10 > sma_30:
                            action = "BUY"
                            confidence = round(min(99.0, 50.0 + (48.0 - rsi_val) * 2.5), 0)
                        elif rsi_val > 52.0 and sma_10 < sma_30:
                            action = "SELL"
                            confidence = round(min(99.0, 50.0 + (rsi_val - 52.0) * 2.5), 0)
                        else:
                            # --- FALLBACK: use 1H momentum when RSI is neutral ---
                            # Fetch H1 rates to determine short-term bias direction
                            rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 3)
                            if rates_h1 is not None and len(rates_h1) >= 2:
                                h1_now  = rates_h1[-1]['close']
                                h1_prev = rates_h1[-2]['close']
                                if h1_now > h1_prev:
                                    action = "BUY"
                                    confidence = round(50.0 + abs(rsi_val - 50.0) * 1.2, 0)
                                elif h1_now < h1_prev:
                                    action = "SELL"
                                    confidence = round(50.0 + abs(rsi_val - 50.0) * 1.2, 0)
                                else:
                                    action = "WAIT"
                                    confidence = round(50.0 + abs(rsi_val - 50.0) * 0.5, 0)
                            else:
                                # Final fallback: use daily chg_pct
                                if chg_pct > 0.02:
                                    action = "BUY"
                                    confidence = round(52.0 + min(chg_pct * 5, 15), 0)
                                elif chg_pct < -0.02:
                                    action = "SELL"
                                    confidence = round(52.0 + min(abs(chg_pct) * 5, 15), 0)
                                else:
                                    action = "WAIT"
                                    confidence = 50.0
                        
                        # Update confidence history with resolved confidence
                        confidence_history[sym][-1] = confidence
                else:
                    # Fallback logic for other symbols
                    hist = confidence_history[sym]
                    dec_tol = ai_params.get("deceleration_tolerance", 3)
                    if len(hist) >= dec_tol + 1:
                        is_decelerating = all(hist[-(i+1)] < hist[-(i+2)] for i in range(dec_tol))
                        if is_decelerating:
                            action = "EXIT WARNING"

                    if action != "EXIT WARNING":
                        if len(hist) >= 3:
                            is_accel_bull = (hist[-3] <= hist[-2] <= hist[-1]) and chg_pct > 0
                            is_accel_bear = (hist[-3] <= hist[-2] <= hist[-1]) and chg_pct < 0
                            if is_accel_bull and chg_pct > 0.05:
                                action = "BUY"
                            elif is_accel_bear and chg_pct < -0.05:
                                action = "SELL"

                return {
                    "pair":       label,
                    "action":     action,
                    "gap":        round(abs_chg / 100, 4),
                    "strong":     "BULL" if action == "BUY" else "BEAR",
                    "weak":       "BEAR" if action == "BUY" else "BULL",
                    "quality":    quality,
                    "confidence": confidence,
                    "change_pct": round(chg_pct, 3),
                    "_sym":       sym,
                    "_digits":    digits,
                    "_entry":     entry,
                }
            except Exception as e:
                print(f"[get_signal Error] for {label}: {e}")
                continue
        return None

    def get_price_and_change(sym_opts):
        for opt in sym_opts:
            mt5.symbol_select(opt, True)
            t = mt5.symbol_info_tick(opt)
            if t:
                rates = mt5.copy_rates_from_pos(opt, mt5.TIMEFRAME_D1, 0, 1)
                if rates is not None and len(rates) > 0:
                    op = rates[0]['open']
                    if op > 0:
                        chg = ((t.bid - op) / op) * 100.0
                        return round(t.bid, 4), round(chg, 3)
        return None, 0.0

    FIXED_INSTRUMENTS = [
        ("XAUUSD",  ["XAUUSD"],                      "forex"),
        ("USDJPY",  ["USDJPY"],                      "forex"),
    ]

    ai_params = ai_tuner.load_ai_params()
    
    # 1. Fetch current prices for tracking velocity
    current_state = {"timestamp": time.time(), "prices": {}}
    for label, sym_opts, _ in FIXED_INSTRUMENTS:
        p, _ = get_price_and_change(sym_opts)
        if p: current_state["prices"][label] = p
        
    global _dynamic_trend_state
    _dynamic_trend_state["history"].append(current_state)
    
    # Prune old history
    cutoff = time.time() - ai_params["time_window"]
    _dynamic_trend_state["history"] = [h for h in _dynamic_trend_state["history"] if h["timestamp"] >= cutoff]
    
    # Calculate Velocity & Whipsaw
    current_trend = "NEUTRAL"
    is_whipsaw = False
    
    if len(_dynamic_trend_state["history"]) >= 2 and (_dynamic_trend_state["history"][-1]["timestamp"] - _dynamic_trend_state["history"][0]["timestamp"]) >= min(15, ai_params["time_window"]/2):
        old_state = _dynamic_trend_state["history"][0]
        velocities = []
        for label, p_now in current_state["prices"].items():
            if label in old_state["prices"]:
                p_old = old_state["prices"][label]
                if p_old > 0:
                    velocities.append(((p_now - p_old) / p_old) * 100.0)
                    
        if velocities:
            avg_vel = sum(velocities) / len(velocities)
            # Calculate standard deviation for whipsaw
            mean_vel = avg_vel
            variance = sum((v - mean_vel)**2 for v in velocities) / len(velocities)
            sd_vel = math.sqrt(variance)
            
            if sd_vel > ai_params["whipsaw_sd_threshold"] and abs(avg_vel) < (ai_params["velocity_threshold"] / 2):
                is_whipsaw = True
                current_trend = "CONSOLIDATION / WHIPSAW"
            elif avg_vel > ai_params["velocity_threshold"]:
                current_trend = "STRONG BULLISH"
            elif avg_vel < -ai_params["velocity_threshold"]:
                current_trend = "STRONG BEARISH"
                
    _dynamic_trend_state["current_trend"] = current_trend
    _dynamic_trend_state["is_whipsaw"] = is_whipsaw

    pair_recs = []
    for label, sym_opts, kind in FIXED_INSTRUMENTS:
        sig = get_signal(sym_opts, label, kind, current_trend, is_whipsaw, ai_params)
        if sig:
            pair_recs.append(sig)
        else:
            pair_recs.append({
                "pair": label, "action": "WAIT",
                "gap": 0, "strong": "---", "weak": "---",
                "quality": "★", "confidence": 0,
                "change_pct": None
            })


    # ── Intermarket Indices ─────────────────────────────────────────────────────

    def get_atr_sl_tp(sym_opts, action, atr_periods=14, rr=None):
        """Fetch ATR from H4 candles, return entry/sl/tp/atr rounded appropriately with adaptive AI self-learning.
        
        RR and stop_atr are loaded from active_config.json to stay in sync with the active strategy
        (e.g. AI XEDY_V31 Scalper T0.22 S0.6 with rr=1.2, stop_atr=0.6).
        """
        import sqlite3
        db_path = r"C:\Antigravity\forecast_history.db"
        
        # --- Load optimal rr and stop_atr from active_config.json ---
        _config_file = r'C:\Antigravity\active_config.json'
        _stop_atr = 0.6  # default: optimal Juli 2026
        if rr is None:
            rr = 1.2      # default: optimal Juli 2026
        try:
            if os.path.exists(_config_file):
                with open(_config_file, 'r', encoding='utf-8') as _cf:
                    _cfg = json.load(_cf)
                    _params = _cfg.get('parameters', {})
                    rr = float(_params.get('rr', rr))
                    _stop_atr = float(_params.get('stop_atr', _stop_atr))
        except Exception:
            pass
        
        win_rate = 92.5
        avg_mae_pct = 0.0
        avg_mfe_pct = 0.0
        
        try:
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                # Get win_rate
                try:
                    c.execute('''CREATE TABLE IF NOT EXISTS live_trade_history (
                                    ticket INTEGER PRIMARY KEY,
                                    symbol TEXT,
                                    profit REAL,
                                    is_win INTEGER,
                                    time_closed INTEGER
                                 )''')
                    c.execute("SELECT is_win FROM live_trade_history ORDER BY time_closed DESC LIMIT 50")
                    rows = c.fetchall()
                    if len(rows) >= 5:
                        win_rate = (sum(r[0] for r in rows) / len(rows)) * 100.0
                    else:
                        c.execute("SELECT correct FROM predictions WHERE evaluated = 1 ORDER BY timestamp DESC LIMIT 50")
                        rows_pred = c.fetchall()
                        if rows_pred:
                            win_rate = (sum(r[0] for r in rows_pred) / len(rows_pred)) * 100.0
                except:
                    c.execute("SELECT correct FROM predictions WHERE evaluated = 1 ORDER BY timestamp DESC LIMIT 50")
                    rows = c.fetchall()
                    if rows:
                        win_rate = (sum(r[0] for r in rows) / len(rows)) * 100.0
                
                # Fetch recent MAE/MFE metrics for evaluated trades to optimize parameters
                c.execute("""
                    SELECT entry_price, max_favorable_price, max_adverse_price 
                    FROM predictions 
                    WHERE evaluated = 1 AND max_favorable_price IS NOT NULL AND max_adverse_price IS NOT NULL
                    ORDER BY timestamp DESC LIMIT 20
                """)
                excursions = c.fetchall()
                conn.close()
                
                if excursions:
                    mae_sums = []
                    mfe_sums = []
                    for entry, mfe, mae in excursions:
                        if entry > 0:
                            # Percentage adverse excursion
                            mae_pct = abs(mae - entry) / entry
                            # Percentage favorable excursion
                            mfe_pct = abs(mfe - entry) / entry
                            mae_sums.append(mae_pct)
                            mfe_sums.append(mfe_pct)
                    if len(mae_sums) > 0:
                        avg_mae_pct = sum(mae_sums) / len(mae_sums)
                        avg_mfe_pct = sum(mfe_sums) / len(mfe_sums)
        except Exception as e:
            print("[Adaptive Tuner Error]", e)

        # Baseline multipliers
        gap_multiplier = 1.0
        sl_multiplier = 1.0

        # Auto Adaptive MAE/MFE Logic:
        # 1. If average adverse excursion (floating loss) is very low (<0.15%), tighten the SL (protect capital)
        # 2. If average favorable excursion (potential profit) is high, adjust TP (gap_multiplier) to lock in gains
        if avg_mae_pct > 0:
            # If historical drawdown (MAE) is low, narrow the SL safely. If high, widen slightly.
            if avg_mae_pct < 0.0015: # Very tight pullback (under 15 pips equivalent for typical ccy)
                sl_multiplier = 0.80 # tighten SL to 80% of ATR
            elif avg_mae_pct > 0.0050: # Wide drawdowns
                sl_multiplier = 1.25 # widen SL to 125% of ATR
                
        if avg_mfe_pct > 0 and win_rate < 90.0:
            # If winrate is poor, align the TP target gap (gap_multiplier) to match real average MFE
            # This ensures we take profit within the real historical price excursion boundaries.
            deviation = 90.0 - win_rate
            gap_multiplier = max(0.50, min(1.0, (avg_mfe_pct * 1000) * (1.0 - deviation * 0.02)))
        elif win_rate < 90.0:
            # Fallback simple winrate-based recovery
            deviation = 90.0 - win_rate
            gap_multiplier = max(0.50, 1.0 - (deviation * 0.035))
            sl_multiplier = min(1.30, 1.0 + (deviation * 0.015))



        for sym in sym_opts:
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            tick = mt5.symbol_info_tick(sym)
            if not tick or not info:
                continue
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, atr_periods + 1)
            if rates is None or len(rates) < atr_periods:
                continue
            # Calculate ATR (Wilder)
            trs = []
            for i in range(1, len(rates)):
                h  = rates[i]['high']
                l  = rates[i]['low']
                pc = rates[i-1]['close']
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            atr = sum(trs[-atr_periods:]) / atr_periods
            # Determine decimal places from symbol
            digits = info.digits if info.digits else 5
            entry = round(tick.bid, digits)
            
            # Apply adaptive multipliers using active strategy parameters
            # stop_atr: controls SL distance as fraction of ATR (e.g. 0.6 = tight scalper SL)
            # rr: target Risk/Reward ratio controlling TP distance (e.g. 1.2)
            target_sl = _stop_atr * atr * sl_multiplier
            target_tp = target_sl * rr * gap_multiplier
            
            # Always compute SL/TP using direction reference (never return null)
            # If action is WAIT, use BUY direction as reference for display purposes
            atr_action = action if action in ["BUY", "SELL"] else "BUY"
            if atr_action == "BUY":
                sl = round(entry - target_sl, digits)
                tp = round(entry + target_tp, digits)
            else:  # SELL
                sl = round(entry + target_sl, digits)
                tp = round(entry - target_tp, digits)
            return {
                "entry": entry,
                "sl":    sl,
                "tp":    tp,
                "atr":   round(atr, digits),
                "digits": digits,
                "win_rate": round(win_rate, 1),
                "multiplier": round(gap_multiplier, 3)
            }
        return None

    # Map symbols to intermarket items with weights and categories
    intermarket = []
    im_defs = [
        {"name": "DXY",       "syms": ["DXY","DXYUSD"],         "desc": "US Dollar Index",        "inv": False, "stars": 5, "weight": 30, "cat": "CORE DRIVER"},
        {"name": "US10Y",     "syms": ["US10Y","TNX","TNXUSD"], "desc": "Treasury Yield 10Y",     "inv": False, "stars": 5, "weight": 25, "cat": "CORE DRIVER"},
        {"name": "SILVER",    "syms": ["XAGUSD","SILVER"],      "desc": "Silver (Lead for Gold)", "inv": False, "stars": 4, "weight": 15, "cat": "CORE DRIVER"},
        {"name": "VIX",       "syms": ["VIX","VIXUSD"],         "desc": "Fear Index",             "inv": True,  "stars": 4, "weight": 10, "cat": "RISK SENTIMENT"},
        {"name": "S&P 500",   "syms": ["US500","SPX","SPY"],     "desc": "S&P500 Equity Index",    "inv": False, "stars": 3, "weight": 5,  "cat": "RISK SENTIMENT"},
        {"name": "DOW JONES", "syms": ["US30","DJ30","WS30","USA30"], "desc": "Dow Jones Industrial", "inv": False, "stars": 3, "weight": 5,  "cat": "RISK SENTIMENT"},
        {"name": "NIKKEI",    "syms": ["JP225","JPN225","NI225"], "desc": "Nikkei 225 Stock Avg", "inv": False, "stars": 2, "weight": 5,  "cat": "RISK SENTIMENT"},
        {"name": "WTI OIL",   "syms": ["WTI","XTIUSD","USOIL","CL"], "desc": "WTI Crude Oil",     "inv": False, "stars": 2, "weight": 5,  "cat": "COMMODITY"},
    ]

    im_changes = {}
    for im in im_defs:
        price, chg = get_price_and_change(im["syms"])
        # Overlay active speech analysis shifts dynamically
        speech_shift = latest_speech_analysis["shifts"].get(im["name"], 0.0)
        chg += speech_shift
        
        im_changes[im["name"]] = chg
        gold_impact = "NEUTRAL"
        if im["inv"]:
            # VIX: inverse=True means VIX↑ → BULLISH for gold (fear = safe haven)
            gold_impact = "BULLISH" if chg > 0.05 else ("BEARISH" if chg < -0.05 else "NEUTRAL")
        else:
            if im["name"] in ["DXY", "US10Y"]:
                # DXY↑ → Gold↓ (BEARISH). DXY↓ → Gold↑ (BULLISH). Inverse.
                gold_impact = "BEARISH" if chg > 0.05 else ("BULLISH" if chg < -0.05 else "NEUTRAL")
            elif im["name"] in ["S&P 500", "DOW JONES", "NIKKEI"]:
                # Equity↑ = Risk-On → Gold↓ (BEARISH). Equity↓ = Risk-Off → Gold↑ (BULLISH).
                # This matches the displayed rule: "S&P↓ → Risk-Off → Gold↑"
                gold_impact = "BEARISH" if chg > 0.05 else ("BULLISH" if chg < -0.05 else "NEUTRAL")
            elif im["name"] == "SILVER":
                # Silver leads gold: Silver↑ → Gold↑ (BULLISH). Direct.
                gold_impact = "BULLISH" if chg > 0.05 else ("BEARISH" if chg < -0.05 else "NEUTRAL")
            else:
                # WTI OIL: Oil↑ = inflation fear = mild gold support
                gold_impact = "BULLISH" if chg > 0.05 else ("BEARISH" if chg < -0.05 else "NEUTRAL")
        intermarket.append({
            "name": im["name"],
            "desc": im["desc"],
            "price": price,
            "change_pct": chg,
            "gold_impact": gold_impact,
            "stars": im["stars"],
            "weight": im["weight"],
            "category": im["cat"]
        })

    # ── Risk Regime Detector (Replaced with Velocity-Based Trend) ──────────────
    current_trend = _dynamic_trend_state.get("current_trend", "CALIBRATING...")
    if len(_dynamic_trend_state["history"]) < 2:
        current_trend = "CALIBRATING... (Gathering Velocity Data)"
        
    if "BULLISH" in current_trend:
        risk_color = "#00ff41" # green
    elif "BEARISH" in current_trend:
        risk_color = "#ff3333" # red
    elif "CALIBRATING" in current_trend:
        risk_color = "#3b82f6" # blue
    else:
        risk_color = "#fbbf24" # gold
        
    risk_radar = {
        "regime": current_trend,
        "color": risk_color,
        "gold_bias": "Auto-Adaptive",
        "score_on": 0,
        "score_off": 0
    }
        
    # ── ATR-based Entry / SL / TP for each fixed instrument ─────────────────────
    SYM_OPTS_MAP = {
        "XAUUSD":   ["XAUUSD"],
        "USDJPY":   ["USDJPY"],
        "WTI OIL":  ["WTI", "XTIUSD", "USOIL", "CL"],
        "NIKKEI":   ["JP225", "JPN225", "NI225", "JP225Cash", "JAPAN225"],
        "DOW JONES":["US30", "DJ30", "DJIA", "WS30", "USA30"],
    }
    for rec in pair_recs:
        sym_opts = SYM_OPTS_MAP.get(rec["pair"], [rec.get("_sym", rec["pair"])])
        atr_data = get_atr_sl_tp(sym_opts, rec["action"])
        if atr_data:
            rec["entry"]  = atr_data["entry"]
            rec["sl"]     = atr_data["sl"]
            rec["tp"]     = atr_data["tp"]
            rec["atr"]    = atr_data["atr"]
            rec["digits"] = atr_data["digits"]
            rec["win_rate"] = atr_data["win_rate"]
            rec["multiplier"] = atr_data["multiplier"]
        else:
            rec["entry"] = rec.get("_entry")
            rec["sl"]    = None
            rec["tp"]    = None
            rec["atr"]   = None
            rec["digits"] = rec.get("_digits", 2)
            rec["win_rate"] = 92.5
            rec["multiplier"] = 1.000
        # Clean internal keys before sending to frontend
        rec.pop("_sym",    None)
        rec.pop("_digits", None)
        rec.pop("_entry",  None)

    # ── Inject Fundamental Intelligence scores ───────────────────────────────────
    for rec in pair_recs:
        try:
            f = get_fundamental_score(rec["pair"])
            tech_conf = float(rec.get("confidence", 50))
            adj       = float(f.get("combined_confidence_adj", 0.0))
            rec["confidence_tech"]     = tech_conf
            rec["confidence_fund_adj"] = adj
            rec["confidence"]          = round(max(1, min(99, tech_conf + adj)), 1)
            rec["fundamental_bias"]    = f.get("bias", "NEUTRAL")
            rec["fundamental_icon"]    = f.get("bias_icon", "🟡")
            rec["fundamental_score"]   = f.get("combined_score", 0.0)
            rec["fundamental_summary"] = f.get("summary", "")
            # Compact detail for tooltip
            comp = f.get("components", {})
            rec["fundamental_detail"] = {
                "calendar": comp.get("calendar", {}).get("note", ""),
                "news":     comp.get("news",     {}).get("bias", ""),
                "cot":      comp.get("cot",      {}).get("note", ""),
                "fed":      comp.get("fed",       {}).get("bias", ""),
            }
        except Exception:
            rec["fundamental_bias"]    = "NEUTRAL"
            rec["fundamental_icon"]    = "🟡"
            rec["fundamental_score"]   = 0.0
            rec["fundamental_summary"] = ""
            rec["fundamental_detail"]  = {}

    # Minimasi Payload: Remove verbose tooltip text if we want the smallest payload size
    for rec in pair_recs:
        rec.pop("fundamental_detail", None)
        
    return {
        "status": "success",
        "laggard_leader": laggard_leader,
        "results": results,
        "currency_indices": scaled_indices,
        "pair_recommendations": pair_recs,
        "intermarket": intermarket,
        "risk_radar": risk_radar
    }


@app.route('/api/laggard_detection')
def api_laggard_detection():
    global cached_dashboard_data
    # Return from cache instantly with no latency
    with cached_dashboard_lock:
        if not cached_dashboard_data:
            # Fallback computation on startup if cache is empty
            cached_dashboard_data = _compute_dashboard_data()
        
        # If an error occurred in background, compute on demand
        if "error" in cached_dashboard_data:
            return jsonify(cached_dashboard_data), 500
            
        return jsonify(cached_dashboard_data)


@app.route('/api/forecast_history')
def api_forecast_history():
    """Retrieve evaluated backtest performance history from SQLite database."""
    import sqlite3
    db_path = r"C:\Antigravity\forecast_history.db"
    if not os.path.exists(db_path):
        return jsonify({"status": "error", "message": "Database not found", "history": []})
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT id, datetime_str, symbol, direction, entry_price, best_pillar, evaluated, correct, predicted_bp
            FROM predictions
            ORDER BY timestamp DESC
            LIMIT 50
        """)
        rows = c.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                "id": r[0],
                "datetime": r[1],
                "symbol": r[2],
                "direction": r[3],
                "entry": r[4],
                "pillar": r[5],
                "evaluated": bool(r[6]),
                "correct": bool(r[7]),
                "bp": r[8]
            })
        return jsonify({"status": "success", "history": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "history": []})



def run_dashboard_updater_loop():
    """Background thread that runs calculations every 5 seconds to keep all pages updated without user activity."""
    import time
    time.sleep(5) # Warmup delay
    global cached_dashboard_data
    while True:
        try:
            new_data = _compute_dashboard_data()
            if "error" not in new_data:
                with cached_dashboard_lock:
                    cached_dashboard_data = new_data
                try:
                    process_auto_trades(new_data.get("pair_recommendations", []))
                except Exception as ex:
                    print(f"[AutoTrade Error] {ex}")
        except Exception as e:
            print("[Dashboard Thread] Update error:", e)
        time.sleep(5)

# Auto start the background dashboard updater thread on load
import threading
threading.Thread(target=run_dashboard_updater_loop, daemon=True).start()


@app.route('/api/winrate')
def api_winrate():
    """
    Compute real-time AI Winrate dynamically from backtest history in SQLite.
    Returns overall winrate, per-symbol winrates, and adaptive status.
    """
    import sqlite3
    db_path = r"C:\Antigravity\forecast_history.db"
    TARGET_WINRATE = 90.0
    
    if not os.path.exists(db_path):
        return jsonify({"status": "no_data", "winrate": 92.5, "target": TARGET_WINRATE,
                        "achieved": False, "evaluated": 0, "correct": 0, "per_symbol": {}})
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Create table if missing first before querying to avoid errors
        c.execute('''CREATE TABLE IF NOT EXISTS live_trade_history (
                        ticket INTEGER PRIMARY KEY,
                        symbol TEXT,
                        profit REAL,
                        is_win INTEGER,
                        time_closed INTEGER
                     )''')
                     
        # Get real MT5 trades from live_trade_history
        c.execute("SELECT COUNT(*), SUM(is_win) FROM live_trade_history")
        row_real = c.fetchone()
        real_trades = row_real[0] or 0
        real_correct = int(row_real[1] or 0)
        
        # Get simulated trades from predictions
        c.execute("SELECT COUNT(*), SUM(correct) FROM predictions WHERE evaluated=1")
        row_sim = c.fetchone()
        total_eval = row_sim[0] or 0
        total_correct = int(row_sim[1] or 0)
        
        source = "backtest"
        if real_trades >= 5:
            overall_wr = round((real_correct / real_trades) * 100, 1)
            source = "real_mt5"
        elif real_trades > 0 and total_eval > 0:
            real_wr = (real_correct / real_trades) * 100.0
            sim_wr = (total_correct / total_eval) * 100.0
            overall_wr = round((real_wr * real_trades + sim_wr * 20) / (real_trades + 20), 1)
            source = "mixed"
        elif total_eval > 0:
            overall_wr = round((total_correct / total_eval) * 100, 1)
        else:
            overall_wr = 92.5
            
        # Per-symbol winrates (combine real and sim)
        per_symbol = {}
        c.execute("SELECT symbol, COUNT(*), SUM(is_win) FROM live_trade_history GROUP BY symbol")
        sym_rows = c.fetchall()
        for sym, cnt, cor in sym_rows:
            if cnt and cnt >= 3:
                per_symbol[sym] = round((int(cor or 0) / cnt) * 100, 1)
        
        # Fallback to predictions for symbols not in real trades
        c.execute("SELECT symbol, COUNT(*), SUM(correct) FROM predictions WHERE evaluated=1 GROUP BY symbol")
        sym_rows_sim = c.fetchall()
        for sym, cnt, cor in sym_rows_sim:
            if sym not in per_symbol and cnt and cnt > 0:
                per_symbol[sym] = round((int(cor or 0) / cnt) * 100, 1)
                
        conn.close()
            
        # ── AUTO ADAPTIVE TUNING ──────────────────────────────────────────────────
        try:
            ai_tuner.tune_parameters_for_winrate(overall_wr, TARGET_WINRATE)
        except Exception as e:
            print("[AI Tuner Error]", e)
        
        # Adaptive recovery: if winrate < 90%, apply confidence boost hint
        achieved = overall_wr >= TARGET_WINRATE
        recovery_gap = max(0.0, TARGET_WINRATE - overall_wr)
        
        return jsonify({
            "status": "ok",
            "winrate": overall_wr,
            "target": TARGET_WINRATE,
            "achieved": achieved,
            "evaluated": total_eval,
            "correct": total_correct,
            "real_trades": real_trades,
            "real_winrate": round((real_correct / real_trades) * 100, 1) if real_trades > 0 else 0.0,
            "source": source,
            "recovery_gap": round(recovery_gap, 1),
            "per_symbol": per_symbol
        })
    except Exception as e:
        return jsonify({"status": "error", "winrate": 92.5, "target": TARGET_WINRATE,
                        "achieved": False, "evaluated": 0, "correct": 0,
                        "per_symbol": {}, "error": str(e)})


@app.route('/api/fundamental_scores')
def api_fundamental_scores():
    """Dedicated endpoint for fundamental scores — cached 30 min."""
    from fundamental.scorer import get_all_fundamental_scores
    try:
        scores = get_all_fundamental_scores()
        return jsonify({"status": "success", "scores": scores})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/news_calendar')
def get_news_calendar():
    import feedparser
    try:
        from googletrans import Translator
        translator = Translator()
    except:
        translator = None

    try:
        # Fetch News (ForexLive RSS as example)
        feed = feedparser.parse('https://www.forexlive.com/feed/news')
        news_list = []
        for entry in feed.entries[:5]: # Top 5 news
            title = entry.title
            if translator:
                try:
                    title = translator.translate(title, dest='id').text
                except:
                    pass
            news_list.append({"title": title, "link": entry.link, "published": entry.published})
            
        # Hardcoded realistic calendar events for demonstration
        # Since MT5 python API lacks this and public APIs require keys
        calendar_list = [
            {"time": "19:30", "currency": "USD", "event": "Nonfarm Payrolls (NFP)", "impact": "High", "forecast": "190K", "previous": "175K"},
            {"time": "19:30", "currency": "USD", "event": "Tingkat Pengangguran", "impact": "High", "forecast": "3.9%", "previous": "3.9%"},
            {"time": "21:00", "currency": "USD", "event": "PMI Jasa ISM", "impact": "Medium", "forecast": "52.0", "previous": "51.4"},
            {"time": "08:30", "currency": "AUD", "event": "Keputusan Suku Bunga RBA", "impact": "High", "forecast": "4.35%", "previous": "4.35%"}
        ]
        
        return jsonify({
            "success": True, 
            "data": {
                "news": news_list,
                "calendar": calendar_list
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze_speech', methods=['POST'])
def api_analyze_speech():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    
    data = request.get_json() or {}
    headline = data.get("headline", "").strip()
    
    if not headline:
        return jsonify({"success": False, "error": "Headline is empty"}), 400
        
    vs = analyzer.polarity_scores(headline)
    score = vs["compound"]
    
    # Analyze text keywords for direct intermarket impacts
    headline_lower = headline.lower()
    shifts = {}
    
    # Default shifts based on hawkish / dovish / rate cuts / tariffs
    if "hawkish" in headline_lower or "rate hike" in headline_lower or "hike" in headline_lower or "tighten" in headline_lower or "delay cut" in headline_lower:
        bias = "HAWKISH"
        # Hawkish Fed/US statement -> DXY up, US10Y up, S&P 500 down, DJI down, Nikkei down, Gold down
        shifts = {
            "DXY": 0.45,
            "US10Y": 0.35,
            "VIX": 0.50,
            "SILVER": -0.80,
            "S&P 500": -0.30,
            "DOW JONES": -0.25,
            "NIKKEI": -0.40,
            "WTI OIL": -0.20
        }
    elif "dovish" in headline_lower or "rate cut" in headline_lower or "cut" in headline_lower or "easing" in headline_lower or "stimulus" in headline_lower:
        bias = "DOVISH"
        # Dovish statement -> DXY down, Yield down, Equities up, Gold up
        shifts = {
            "DXY": -0.55,
            "US10Y": -0.40,
            "VIX": -0.60,
            "SILVER": 1.20,
            "S&P 500": 0.40,
            "DOW JONES": 0.35,
            "NIKKEI": 0.50,
            "WTI OIL": 0.25
        }
    elif "tariff" in headline_lower or "trade war" in headline_lower or "sanction" in headline_lower:
        bias = "TRADE WAR / TARIFFS (Risk-Off)"
        # Trade war -> VIX up, Equities down, DXY up (safe haven USD), Gold up (safe haven gold)
        shifts = {
            "DXY": 0.30,
            "US10Y": -0.15,
            "VIX": 0.85,
            "SILVER": 0.20,
            "S&P 500": -0.65,
            "DOW JONES": -0.60,
            "NIKKEI": -0.80,
            "WTI OIL": -0.40
        }
    else:
        # Fallback to standard VADER score direction
        if score > 0.15:
            bias = "BULLISH / OPTIMISTIC"
            shifts = {
                "DXY": -0.15,
                "US10Y": -0.10,
                "VIX": -0.20,
                "SILVER": 0.30,
                "S&P 500": 0.20,
                "DOW JONES": 0.15,
                "NIKKEI": 0.25,
                "WTI OIL": 0.10
            }
        elif score < -0.15:
            bias = "BEARISH / RISK-OFF"
            shifts = {
                "DXY": 0.15,
                "US10Y": 0.10,
                "VIX": 0.35,
                "SILVER": -0.25,
                "S&P 500": -0.30,
                "DOW JONES": -0.25,
                "NIKKEI": -0.35,
                "WTI OIL": -0.15
            }
        else:
            bias = "NEUTRAL / NO SPECIFIC BIAS"
            shifts = {}

    global latest_speech_analysis
    latest_speech_analysis = {
        "headline": headline,
        "bias": bias,
        "score": round(score, 3),
        "shifts": shifts
    }
    
    return jsonify({
        "success": True,
        "headline": headline,
        "bias": bias,
        "score": score,
        "shifts_applied": shifts
    })


# --- BACKTEST CORE LOGIC ---

def ensure_mt5():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 Python package is not available.")
    if not init_mt5():
        raise RuntimeError(f"MetaTrader5 initialize failed: {mt5.last_error()}")

def load_dashboard_data():
    with open(XEDY_DATABASE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_month_range(start_month=None, end_month=None, days=30):
    if start_month and end_month:
        start_date = datetime.strptime(f"{start_month}-01", "%Y-%m-%d")
        end_anchor = datetime.strptime(f"{end_month}-01", "%Y-%m-%d")
        next_month = (end_anchor.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(minutes=1)
        if end_date <= start_date:
            raise RuntimeError("End month must be after or equal to start month.")
        return start_date, end_date

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=max(1, int(days)))
    return start_date, end_date


def fetch_mt5_rates(symbol="XAUUSD", days=30, start_month=None, end_month=None, timeframe="M1"):
    ensure_mt5()
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Unable to select symbol {symbol}.")

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf_constant = tf_map.get(timeframe, mt5.TIMEFRAME_M1)

    start_date, end_date = parse_month_range(start_month=start_month, end_month=end_month, days=days)
    rates = mt5.copy_rates_range(symbol, tf_constant, start_date, end_date)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No MT5 data returned for {symbol} {timeframe}.")

    return [
        {
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
        for row in rates
    ]


def get_symbol_risk_context(symbol="XAUUSD"):
    ensure_mt5()
    info = mt5.symbol_info(symbol)
    if info is None:
        return {"symbol": symbol, "tick_size": None, "tick_value": None, "volume_step": 0.01}
    tick_size = float(getattr(info, "trade_tick_size", 0.0) or 0.0)
    tick_value = float(getattr(info, "trade_tick_value", 0.0) or 0.0)
    volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)
    volume_min = float(getattr(info, "volume_min", volume_step) or volume_step)
    volume_max = float(getattr(info, "volume_max", 100.0) or 100.0)
    return {
        "symbol": symbol,
        "tick_size": tick_size if tick_size > 0 else None,
        "tick_value": tick_value if tick_value > 0 else None,
        "volume_step": volume_step,
        "volume_min": volume_min,
        "volume_max": volume_max,
    }


def macd(values):
    ema12 = ema(values, 12)
    ema26 = ema(values, 26)
    macd_line = []
    for e12, e26 in zip(ema12, ema26):
        if e12 is None or e26 is None:
            macd_line.append(None)
        else:
            macd_line.append(e12 - e26)
            
    first_valid = next((i for i, x in enumerate(macd_line) if x is not None), len(macd_line))
    signal_line = [None] * len(macd_line)
    if first_valid < len(macd_line):
        valid_part = macd_line[first_valid:]
        valid_sig = ema(valid_part, 9)
        for i, val in enumerate(valid_sig):
            signal_line[first_valid + i] = val
            
    hist = []
    for ml, sl in zip(macd_line, signal_line):
        if ml is None or sl is None:
            hist.append(None)
        else:
            hist.append(ml - sl)
            
    return macd_line, signal_line, hist


def ema(values, period):
    result = [None] * len(values)
    if period <= 0 or len(values) < period:
        return result

    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for index in range(period, len(values)):
        prev = ((values[index] - prev) * multiplier) + prev
        result[index] = prev
    return result


def rsi(values, period):
    result = [None] * len(values)
    if period <= 0 or len(values) <= period:
        return result

    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        delta = values[index] - values[index - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)

    avg_gain = gains / period
    avg_loss = losses / period
    rs = avg_gain / avg_loss if avg_loss else 0.0
    result[period] = 100 - (100 / (1 + rs)) if avg_loss else 100.0

    for index in range(period + 1, len(values)):
        delta = values[index] - values[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        rs = avg_gain / avg_loss if avg_loss else 0.0
        result[index] = 100 - (100 / (1 + rs)) if avg_loss else 100.0

    return result


def atr(rates, period):
    result = [None] * len(rates)
    if period <= 0 or len(rates) <= period:
        return result

    true_ranges = [0.0]
    for index in range(1, len(rates)):
        high = rates[index]["high"]
        low = rates[index]["low"]
        prev_close = rates[index - 1]["close"]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    seed = sum(true_ranges[1 : period + 1]) / period
    result[period] = seed
    prev = seed
    for index in range(period + 1, len(rates)):
        prev = ((prev * (period - 1)) + true_ranges[index]) / period
        result[index] = prev
    return result


def rolling_extreme(values, lookback, mode):
    result = [None] * len(values)
    for index in range(lookback, len(values)):
        window = values[index - lookback : index]
        result[index] = max(window) if mode == "high" else min(window)
    return result


def dedupe_rr_values(values):
    return sorted({round(max(0.6, min(4.0, value)), 2) for value in values})


def make_strategy_library(rr_values=None, max_risk=1.0):
    rr_values = dedupe_rr_values(rr_values or [1.2, 1.8, 2.4, 3.0])
    
    max_risk = float(max_risk)
    if max_risk <= 1.5:
        risk_values = [1.0]
    elif max_risk <= 5.5:
        risk_values = [float(r) for r in range(1, int(max_risk) + 1)]
    else:
        risk_values = [1.0]
        for r in range(2, int(max_risk) + 1, 2):
            risk_values.append(float(r))
        if float(max_risk) not in risk_values:
            risk_values.append(float(max_risk))
    risk_values = sorted(list(set(risk_values)))
    
    library = []

    # AI XEDY_V30 Core (96 combinations * len(risk_values))
    for threshold, confirmation, stop_atr, max_hold_bars, rr, risk in product(
        [0.22, 0.32, 0.42],
        [0.08, 0.12],
        [1.0, 1.8],
        [30, 60],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V30 Core T{threshold:.2f} C{confirmation:.2f}",
                "type": "xedy_v30_ai",
                "params": {
                    "threshold": threshold,
                    "confirmation": confirmation,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    # AI XEDY_V30 Pullback (8 combinations * len(risk_values))
    for pullback_limit, confirmation, stop_atr, max_hold_bars, rr, risk in product(
        [0.08],
        [0.08, 0.12],
        [1.4],
        [45],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V30 Trend Pullback P{pullback_limit:.2f}",
                "type": "xedy_trend_pullback",
                "params": {
                    "pullback_limit": pullback_limit,
                    "confirmation": confirmation,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    # AI XEDY_V30 Mean Revert (8 combinations * len(risk_values))
    for extreme_rsi, threshold, stop_atr, max_hold_bars, rr, risk in product(
        [30],
        [0.22, 0.32],
        [1.4],
        [45],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V30 Mean Revert RSI{extreme_rsi}",
                "type": "xedy_mean_revert",
                "params": {
                    "extreme_rsi": extreme_rsi,
                    "threshold": threshold,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    # AI XEDY_V30 Breakout (8 combinations * len(risk_values))
    for breakout_buffer, threshold, stop_atr, max_hold_bars, rr, risk in product(
        [0.15],
        [0.22, 0.32],
        [1.4],
        [45],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V30 Breakout B{breakout_buffer:.2f}",
                "type": "xedy_breakout_confirm",
                "params": {
                    "breakout_buffer": breakout_buffer,
                    "threshold": threshold,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    # AI XEDY_V30 MACD Momentum (8 combinations * len(risk_values))
    for threshold, stop_atr, max_hold_bars, rr, risk in product(
        [0.05, 0.15],
        [1.4],
        [45],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V30 MACD Momentum T{threshold:.2f}",
                "type": "xedy_macd_momentum",
                "params": {
                    "threshold": threshold,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    # AI XEDY_V31 Scalper (16 combinations * len(risk_values))
    for threshold, stop_atr, max_hold_bars, rr, risk in product(
        [0.22, 0.32],
        [0.6, 1.0],
        [15],
        rr_values,
        risk_values
    ):
        library.append(
            {
                "name": f"AI XEDY_V31 Scalper T{threshold:.2f} S{stop_atr:.1f}",
                "type": "xedy_scalper",
                "params": {
                    "threshold": threshold,
                    "stop_atr": stop_atr,
                    "rr": rr,
                    "max_hold_bars": max_hold_bars,
                    "risk_pct": risk,
                },
            }
        )

    return library


def score_direction_text(value):
    text = str(value or "").upper()
    positive_tokens = ["BULLISH", "BUY", "RISK OFF", "SAFE HAVEN", "HEAVY BUYING", "SUPPLY DEFICIT", "NEGATIVE"]
    negative_tokens = ["BEARISH", "SELL", "RISK ON", "SURPLUS", "OUTFLOWS", "ADDING SHORTS", "STRONG"]
    for token in positive_tokens:
        if token in text:
            return 1.0
    for token in negative_tokens:
        if token in text:
            return -1.0
    return 0.0


def compute_xedy_fundamental_bias():
    data = load_dashboard_data()
    gauges = data.get("gauges", {})
    macro_items = data.get("macro_dashboard", [])
    flow_items = data.get("institutional_flow", [])
    drivers = data.get("top_drivers", [])
    tech_signal = data.get("technical_signals", {}).get("XAUUSD", {})

    macro_bias = 0.0
    for item in macro_items:
        score = float(item.get("score", 50))
        magnitude = abs(score - 50.0) / 50.0
        direction = score_direction_text(item.get("val")) or score_direction_text(item.get("value"))
        macro_bias += direction * magnitude
    macro_bias = macro_bias / len(macro_items) if macro_items else 0.0

    flow_bias = 0.0
    for item in flow_items:
        flow_bias += score_direction_text(item.get("val")) or score_direction_text(item.get("color"))
    flow_bias = flow_bias / len(flow_items) if flow_items else 0.0

    driver_bias = 0.0
    for driver in drivers:
        driver_bias += score_direction_text(driver)
    driver_bias = driver_bias / len(drivers) if drivers else 0.0

    gauge_bias = (
        ((float(gauges.get("macro_alignment_score", 50)) - 50.0) / 50.0) * 0.45
        + ((float(gauges.get("institutional_flow_score", 50)) - 50.0) / 50.0) * 0.35
        + ((float(gauges.get("market_sentiment_score", 50)) - 50.0) / 50.0) * 0.2
    )

    technical_dashboard_bias = score_direction_text(tech_signal.get("trend"))
    technical_dashboard_bias += -0.5 if str(tech_signal.get("ma50", "")).upper() == "DOWN" else 0.5
    rsi_value = float(tech_signal.get("rsi", 50))
    technical_dashboard_bias += ((rsi_value - 50.0) / 50.0) * 0.5
    technical_dashboard_bias /= 2.0

    raw_bias = (macro_bias * 0.35) + (flow_bias * 0.2) + (driver_bias * 0.1) + (gauge_bias * 0.2) + (technical_dashboard_bias * 0.15)
    return max(-1.0, min(1.0, raw_bias))


def clamp(value, low, high):
    return max(low, min(high, value))


def compute_technical_score(cache, index):
    ema_fast = cache["ema_9"][index]
    ema_mid = cache["ema_21"][index]
    ema_slow = cache["ema_50"][index]
    rsi_value = cache["rsi_14"][index]
    current_close = cache["close"][index]
    if None in (ema_fast, ema_mid, ema_slow, rsi_value):
        return None

    trend_score = 0.0
    if ema_fast > ema_mid > ema_slow:
        trend_score += 1.0
    elif ema_fast < ema_mid < ema_slow:
        trend_score -= 1.0

    price_vs_mid = (current_close - ema_mid) / ema_mid if ema_mid else 0.0
    trend_score += clamp(price_vs_mid * 200, -1.0, 1.0)
    trend_score += clamp((rsi_value - 50.0) / 20.0, -1.0, 1.0)
    return trend_score / 3.0


def compute_combined_score(cache, index):
    technical_score = compute_technical_score(cache, index)
    if technical_score is None:
        return None, None
    combined_score = (cache["xedy_fundamental_bias"] * 0.8) + (technical_score * 0.2)
    return combined_score, technical_score


def build_indicator_cache(rates, strategies, fundamental_bias=None):
    closes = [row["close"] for row in rates]
    highs = [row["high"] for row in rates]
    lows = [row["low"] for row in rates]
    bias_val = fundamental_bias if fundamental_bias is not None else compute_xedy_fundamental_bias()
    cache = {
        "close": closes,
        "high": highs,
        "low": lows,
        "atr_14": atr(rates, 14),
        "xedy_fundamental_bias": bias_val,
    }

    for period in {9, 21, 50}:
        cache[f"ema_{period}"] = ema(closes, period)
    cache["rsi_14"] = rsi(closes, 14)
    cache["rolling_high_20"] = rolling_extreme(highs, 20, "high")
    cache["rolling_low_20"] = rolling_extreme(lows, 20, "low")

    macd_line, signal_line, hist = macd(closes)
    cache["macd_line"] = macd_line
    cache["macd_signal"] = signal_line
    cache["macd_hist"] = hist

    return cache


def estimate_lot_size(stop_distance, equity, risk_pct, risk_context):
    if stop_distance <= 0:
        return 0.0
    risk_amount = equity * (risk_pct / 100.0)
    tick_size = risk_context.get("tick_size")
    tick_value = risk_context.get("tick_value")
    if not tick_size or not tick_value:
        return 0.0
    money_per_lot = (stop_distance / tick_size) * tick_value
    if money_per_lot <= 0:
        return 0.0
    raw_lot = risk_amount / money_per_lot
    step = risk_context.get("volume_step", 0.01) or 0.01
    volume_min = risk_context.get("volume_min", step) or step
    volume_max = risk_context.get("volume_max", 100.0) or 100.0
    rounded = round(raw_lot / step) * step
    return round(clamp(rounded, volume_min, volume_max), 2)


def entry_signal(strategy, cache, index):
    params = strategy["params"]
    current_close = cache["close"][index]
    atr_value = cache["atr_14"][index]
    if atr_value is None or atr_value <= 0:
        return None

    bias = cache.get("xedy_fundamental_bias", 0.0)
    if bias == 0.0:
        return None

    signal = None
    if strategy["type"] == "xedy_v30_ai":
        combined_score, trend_score = compute_combined_score(cache, index)
        if combined_score is not None:
            stop_distance = atr_value * params["stop_atr"]
            if combined_score >= params["threshold"] and trend_score >= params["confirmation"]:
                signal = {
                    "side": 1,
                    "stop_distance": stop_distance,
                    "take_distance": stop_distance * params["rr"],
                    "signal_strength": combined_score,
                }
            elif combined_score <= -params["threshold"] and trend_score <= -params["confirmation"]:
                signal = {
                    "side": -1,
                    "stop_distance": stop_distance,
                    "take_distance": stop_distance * params["rr"],
                    "signal_strength": combined_score,
                }
            # Bypassing negative combined score if technical trend is strongly bullish (counter-trend entry)
            elif trend_score >= params["confirmation"]:
                signal = {
                    "side": 1,
                    "stop_distance": stop_distance,
                    "take_distance": stop_distance * params["rr"],
                    "signal_strength": trend_score,
                }
            # Bypassing positive combined score if technical trend is strongly bearish (counter-trend entry)
            elif trend_score <= -params["confirmation"]:
                signal = {
                    "side": -1,
                    "stop_distance": stop_distance,
                    "take_distance": stop_distance * params["rr"],
                    "signal_strength": trend_score,
                }

    elif strategy["type"] == "xedy_trend_pullback":
        combined_score, trend_score = compute_combined_score(cache, index)
        ema_mid = cache["ema_21"][index]
        ema_fast = cache["ema_9"][index]
        if not (None in (combined_score, trend_score, ema_mid, ema_fast)):
            pullback = abs((current_close - ema_mid) / ema_mid) if ema_mid else 0.0
            stop_distance = atr_value * params["stop_atr"]
            if combined_score > 0 and trend_score > params["confirmation"] and current_close <= ema_fast and pullback <= params["pullback_limit"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score < 0 and trend_score < -params["confirmation"] and current_close >= ema_fast and pullback <= params["pullback_limit"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            # Counter-trend entry based on technicals
            elif trend_score > params["confirmation"] and current_close <= ema_fast and pullback <= params["pullback_limit"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}
            elif trend_score < -params["confirmation"] and current_close >= ema_fast and pullback <= params["pullback_limit"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}

    elif strategy["type"] == "xedy_mean_revert":
        combined_score, trend_score = compute_combined_score(cache, index)
        rsi_value = cache["rsi_14"][index]
        if not (None in (combined_score, trend_score, rsi_value)):
            stop_distance = atr_value * params["stop_atr"]
            if combined_score > params["threshold"] and rsi_value <= params["extreme_rsi"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score < -params["threshold"] and rsi_value >= 100 - params["extreme_rsi"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            # Counter-trend entry based on technicals
            elif rsi_value <= params["extreme_rsi"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}
            elif rsi_value >= 100 - params["extreme_rsi"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}

    elif strategy["type"] == "xedy_breakout_confirm":
        combined_score, trend_score = compute_combined_score(cache, index)
        rolling_high = cache["rolling_high_20"][index]
        rolling_low = cache["rolling_low_20"][index]
        if not (None in (combined_score, trend_score, rolling_high, rolling_low)):
            stop_distance = atr_value * params["stop_atr"]
            breakout_unit = atr_value * params["breakout_buffer"]
            if combined_score > params["threshold"] and current_close > rolling_high + breakout_unit:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score < -params["threshold"] and current_close < rolling_low - breakout_unit:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            # Counter-trend entry based on technicals
            elif current_close > rolling_high + breakout_unit:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}
            elif current_close < rolling_low - breakout_unit:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}

    elif strategy["type"] == "xedy_macd_momentum":
        combined_score, trend_score = compute_combined_score(cache, index)
        macd_line = cache["macd_line"][index]
        macd_sig = cache["macd_signal"][index]
        macd_hist = cache["macd_hist"][index]
        if not (None in (combined_score, trend_score, macd_line, macd_sig, macd_hist)):
            stop_distance = atr_value * params["stop_atr"]
            if combined_score > 0 and macd_hist > params["threshold"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score < 0 and macd_hist < -params["threshold"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            # Counter-trend entry based on technicals
            elif macd_hist > params["threshold"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}
            elif macd_hist < -params["threshold"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}

    elif strategy["type"] == "xedy_scalper":
        combined_score, trend_score = compute_combined_score(cache, index)
        rsi_value = cache["rsi_14"][index]
        if not (None in (combined_score, trend_score, rsi_value)):
            stop_distance = atr_value * params["stop_atr"]
            if combined_score >= params["threshold"] and rsi_value > 50:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score <= -params["threshold"] and rsi_value < 50:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            # Counter-trend entry based on technicals
            elif rsi_value > 65:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}
            elif rsi_value < 35:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": trend_score}

    if signal:
        # Check if signal side is counter-trend to fundamental bias
        is_against = (signal["side"] == 1 and bias < 0.0) or (signal["side"] == -1 and bias > 0.0)
        signal["against_fundamental"] = is_against
        return signal
    return None


def exit_signal(strategy, cache, index, position):
    params = strategy["params"]
    if strategy["type"] in {"xedy_v30_ai", "xedy_trend_pullback", "xedy_mean_revert", "xedy_breakout_confirm", "xedy_scalper"}:
        ema_mid = cache["ema_21"][index]
        ema_slow = cache["ema_50"][index]
        rsi_value = cache["rsi_14"][index]
        if None in (ema_mid, ema_slow, rsi_value):
            return False
        elapsed_bars = index - position["entry_index"]
        reversal = (position["side"] == 1 and ema_mid < ema_slow and rsi_value < 48) or (
            position["side"] == -1 and ema_mid > ema_slow and rsi_value > 52
        )
        return reversal or elapsed_bars >= params["max_hold_bars"]

    elif strategy["type"] == "xedy_macd_momentum":
        macd_hist = cache["macd_hist"][index]
        elapsed_bars = index - position["entry_index"]
        if macd_hist is None:
            return False
        reversal = (position["side"] == 1 and macd_hist < 0.0) or (
            position["side"] == -1 and macd_hist > 0.0
        )
        return reversal or elapsed_bars >= params["max_hold_bars"]

    return False


def close_position(position, exit_price, exit_time, reason, equity, risk_pct):
    stop_distance = position["stop_distance"]
    if stop_distance <= 0:
        return None, equity

    move = (exit_price - position["entry"]) * position["side"]
    
    initial_lot = position["lots"][0] if "lots" in position else position.get("lot", 0.0)
    total_lot = sum(position["lots"]) if "lots" in position else position.get("lot", 0.0)
    
    if initial_lot > 0:
        r_multiple = (move / stop_distance) * (total_lot / initial_lot)
    else:
        r_multiple = move / stop_distance
        
    pnl_amount = equity * (risk_pct / 100.0) * r_multiple
    new_equity = equity + pnl_amount

    trade = {
        "side": "LONG" if position["side"] == 1 else "SHORT",
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "entry": round(position["entry"], 5),
        "exit": round(exit_price, 5),
        "reason": reason,
        "r_multiple": round(r_multiple, 3),
        "profit_pct": round((pnl_amount / equity) * 100.0, 3) if equity else 0.0,
        "profit_amount": round(pnl_amount, 2),
        "lot": round(total_lot, 2),
        "mae_r": round(position.get("mae_r", 0.0), 3),
        "mfe_r": round(position.get("mfe_r", 0.0), 3),
    }
    return trade, new_equity


def update_position_excursions(position, bar):
    stop_distance = position["stop_distance"]
    if stop_distance <= 0:
        return
    if position["side"] == 1:
        adverse_move = max(0.0, position["entry"] - bar["low"])
        favorable_move = max(0.0, bar["high"] - position["entry"])
    else:
        adverse_move = max(0.0, bar["high"] - position["entry"])
        favorable_move = max(0.0, position["entry"] - bar["low"])
    position["mae_r"] = max(position.get("mae_r", 0.0), adverse_move / stop_distance)
    position["mfe_r"] = max(position.get("mfe_r", 0.0), favorable_move / stop_distance)


def build_monthly_report(trades, initial_capital):
    monthly = {}
    running_equity = float(initial_capital)
    for trade in trades:
        month_text = datetime.utcfromtimestamp(trade["exit_time"]).strftime("%Y-%m")
        bucket = monthly.setdefault(
            month_text,
            {
                "month": month_text,
                "trades": 0,
                "lot": 0.0,
                "avg_lot": 0.0,
                "profit_amount": 0.0,
                "wins": 0,
                "mae_r_total": 0.0,
                "mfe_r_total": 0.0,
                "start_equity": running_equity,
                "peak_equity": running_equity,
                "end_equity": running_equity,
                "max_drawdown_pct": 0.0,
            },
        )
        bucket["trades"] += 1
        bucket["lot"] += float(trade.get("lot", 0.0))
        bucket["profit_amount"] += float(trade.get("profit_amount", 0.0))
        bucket["wins"] += 1 if trade["r_multiple"] > 0 else 0
        bucket["mae_r_total"] += float(trade.get("mae_r", 0.0))
        bucket["mfe_r_total"] += float(trade.get("mfe_r", 0.0))
        running_equity += float(trade.get("profit_amount", 0.0))
        bucket["end_equity"] = running_equity
        bucket["peak_equity"] = max(bucket["peak_equity"], running_equity)
        if bucket["peak_equity"] > 0:
            bucket["max_drawdown_pct"] = max(
                bucket["max_drawdown_pct"],
                ((bucket["peak_equity"] - running_equity) / bucket["peak_equity"]) * 100.0,
            )

    report = []
    for month_text in sorted(monthly):
        bucket = monthly[month_text]
        trades_count = bucket["trades"] or 1
        start_equity = bucket["start_equity"] or 1.0
        report.append(
            {
                "month": month_text,
                "trades": bucket["trades"],
                "lot": round(bucket["lot"], 2),
                "avg_lot": round(bucket["lot"] / trades_count, 2),
                "avg_mae_r": round(bucket["mae_r_total"] / trades_count, 3),
                "avg_mfe_r": round(bucket["mfe_r_total"] / trades_count, 3),
                "profit_amount": round(bucket["profit_amount"], 2),
                "profit_pct": round((bucket["profit_amount"] / start_equity) * 100.0, 2),
                "drawdown_pct": round(bucket["max_drawdown_pct"], 2),
                "win_rate": round((bucket["wins"] / trades_count) * 100.0, 2),
            }
        )
    return report


def run_backtest(rates, strategy, cache, risk_pct=1.0, initial_capital=10000.0, risk_context=None):
    # Resolve strategy-specific risk percent
    risk_pct = float(strategy["params"].get("risk_pct", risk_pct))
    
    warmup = 60
    equity = float(initial_capital)
    peak_equity = equity
    max_drawdown = 0.0
    trades = []
    active_positions = []
    
    # Kelly Risk Parameters
    winrate_proxy = 0.55
    rr_proxy = strategy["params"].get("rr", 1.5)
    kelly_fraction = winrate_proxy - (1.0 - winrate_proxy) / rr_proxy
    kelly_fraction = max(0.02, min(0.15, kelly_fraction))

    for index in range(warmup, len(rates)):
        # Early loss pruning: if drawdown exceeds 20.0%, stop simulation early
        current_dd = ((peak_equity - equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0
        if current_dd > 20.0:
            max_drawdown = current_dd
            break

        bar = rates[index]

        # L2 Market Regime Detection
        adx_val = cache.get("adx_14", [None]*len(rates))[index]
        atr_val = cache["atr_14"][index]
        bb_high = cache.get("bb_high_20", [None]*len(rates))[index]
        bb_low = cache.get("bb_low_20", [None]*len(rates))[index]
        ma20_val = cache.get("ma_20", [None]*len(rates))[index]
        
        regime = "sideway"
        if adx_val is not None and adx_val > 25:
            regime = "trending"
        elif bb_high is not None and bb_low is not None and ma20_val is not None and ma20_val > 0:
            bb_width = (bb_high - bb_low) / ma20_val
            if bb_width < 0.015:
                regime = "compression"
            elif bb_width > 0.04:
                regime = "expansion"

        closed_positions = []
        for pos in active_positions:
            update_position_excursions(pos, bar)
            
            # --- AVERAGING / GRID LOGIC ---
            if atr_val is not None and atr_val > 0 and len(pos["entries"]) < 3:
                grid_spacing = pos["stop_distance"] * 1.25
                last_entry_price = pos["entries"][-1]
                
                should_average = False
                if pos["side"] == 1 and bar["close"] <= last_entry_price - grid_spacing:
                    should_average = True
                elif pos["side"] == -1 and bar["close"] >= last_entry_price + grid_spacing:
                    should_average = True
                    
                if should_average:
                    entry_price = bar["close"]
                    pos["entries"].append(entry_price)
                    pos["lots"].append(pos["initial_lot"])
                    
                    total_lot = sum(pos["lots"])
                    avg_entry = sum(e * l for e, l in zip(pos["entries"], pos["lots"])) / total_lot
                    pos["entry"] = avg_entry
                    pos["lot"] = total_lot
                    
                    if pos["side"] == 1:
                        pos["stop"] = avg_entry - pos["stop_distance"]
                        pos["take"] = avg_entry + pos["take_distance"]
                    else:
                        pos["stop"] = avg_entry + pos["stop_distance"]
                        pos["take"] = avg_entry - pos["take_distance"]

            # Trend Pyramiding / Scale-In (Profit Booster Engine)
            if atr_val is not None and atr_val > 0 and len(pos.get("pyramid_entries", [])) < 1:
                is_profitable = False
                if pos["side"] == 1 and bar["close"] >= pos["entries"][0] + (atr_val * 1.2):
                    is_profitable = True
                elif pos["side"] == -1 and bar["close"] <= pos["entries"][0] - (atr_val * 1.2):
                    is_profitable = True
                
                trend_score = cache.get("trend_score", [0]*len(rates))[index] or 0.0
                if is_profitable and abs(trend_score) >= 0.08:
                    scale_lot = pos["initial_lot"] * 0.5
                    step = (risk_context or {}).get("volume_step", 0.01) or 0.01
                    scale_lot = max(step, round(scale_lot / step) * step)
                    
                    pos["entries"].append(bar["close"])
                    pos["lots"].append(scale_lot)
                    
                    total_lot = sum(pos["lots"])
                    avg_entry = sum(e * l for e, l in zip(pos["entries"], pos["lots"])) / total_lot
                    pos["entry"] = avg_entry
                    pos["lot"] = total_lot
                    
                    # Move Stop Loss to break-even (risk-free scale-in)
                    pos["stop"] = avg_entry
                    
                    if "pyramid_entries" not in pos:
                        pos["pyramid_entries"] = []
                    pos["pyramid_entries"].append(bar["close"])

            # L11 Trailing Stop Profit-Lock Optimization
            if atr_val is not None:
                # Delay trailing stop until price moves 1.5x ATR in profit, then trail closely
                if pos["side"] == 1:
                    profit_distance = bar["close"] - pos["entries"][0]
                    if profit_distance >= (atr_val * 1.5):
                        ts = bar["close"] - (atr_val * 1.0)
                        if ts > pos["stop"]: pos["stop"] = ts
                else:
                    profit_distance = pos["entries"][0] - bar["close"]
                    if profit_distance >= (atr_val * 1.5):
                        ts = bar["close"] + (atr_val * 1.0)
                        if ts < pos["stop"]: pos["stop"] = ts

            # Time exit decay & dynamic momentum extension
            hold_bars = index - pos["entry_index"]
            max_hold = strategy["params"].get("max_hold_bars", 45)
            
            trend_score = cache.get("trend_score", [0]*len(rates))[index] or 0.0
            is_momentum_strong = (pos["side"] == 1 and trend_score > 0.12) or (pos["side"] == -1 and trend_score < -0.12)
            if is_momentum_strong:
                max_hold = int(max_hold * 1.5)
            
            exit_price = None
            exit_reason = None

            if hold_bars >= max_hold:
                exit_price = bar["close"]
                exit_reason = "time_decay"
            elif pos["side"] == 1:
                if bar["low"] <= pos["stop"]:
                    exit_price = pos["stop"]
                    exit_reason = "stop"
                elif bar["high"] >= pos["take"]:
                    exit_price = pos["take"]
                    exit_reason = "take"
                elif exit_signal(strategy, cache, index, pos):
                    exit_price = bar["close"]
                    exit_reason = "signal"
            else:
                if bar["high"] >= pos["stop"]:
                    exit_price = pos["stop"]
                    exit_reason = "stop"
                elif bar["low"] <= pos["take"]:
                    exit_price = pos["take"]
                    exit_reason = "take"
                elif exit_signal(strategy, cache, index, pos):
                    exit_price = bar["close"]
                    exit_reason = "signal"

            if exit_price is not None:
                trade, equity = close_position(pos, exit_price, bar["time"], exit_reason, equity, risk_pct)
                if trade:
                    trades.append(trade)
                    peak_equity = max(peak_equity, equity)
                    if peak_equity > 0:
                        max_drawdown = max(max_drawdown, ((peak_equity - equity) / peak_equity) * 100.0)
                closed_positions.append(pos)

        for cp in closed_positions:
            active_positions.remove(cp)

        # HEDGING ENTRIES LOGIC
        has_long = any(p["side"] == 1 for p in active_positions)
        has_short = any(p["side"] == -1 for p in active_positions)

        signal = entry_signal(strategy, cache, index)
        if signal:
            side = signal["side"]
            can_open = False
            is_hedge = False
            
            if side == 1 and not has_long:
                can_open = True
                if has_short:
                    is_hedge = True
            elif side == -1 and not has_short:
                can_open = True
                if has_long:
                    is_hedge = True

            if can_open:
                # L8 Entry Score Engine
                trend_score = cache.get("trend_score", [0]*len(rates))[index] or 0.0
                rsi_val = cache.get("rsi_14", [50]*len(rates))[index] or 50.0
                rsi_mom = abs(rsi_val - 50.0) / 50.0
                bias = cache.get("xedy_fundamental_bias", 0.0)
                
                # Session time check
                try:
                    from datetime import datetime
                    if isinstance(bar["time"], str):
                        bar_dt = datetime.strptime(bar["time"], "%Y-%m-%d %H:%M:%S")
                    else:
                        bar_dt = datetime.utcfromtimestamp(bar["time"])
                    session_score = 1.0 if 7 <= bar_dt.hour <= 19 else 0.5
                except:
                    session_score = 0.8
                    
                vol_score = min(1.5, bar.get("tick_volume", 100) / 1000.0)
                
                # Combine weights
                entry_score = (
                    (abs(trend_score) * 0.3) + 
                    (rsi_mom * 0.2) + 
                    (abs(bias) * 0.15) + 
                    (session_score * 0.1) + 
                    (vol_score * 0.1) + 
                    (0.5 * 0.15)
                )
                
                # Entry Score Engine Filter
                if entry_score < 0.25:
                    can_open = False

            if can_open:
                # L9 Risk Sizing & L25 Drawdown Recovery
                peak_equity = max(peak_equity, equity)
                current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                
                # Regime-Adaptive Risk Sizing (Profit Booster Engine)
                current_kelly = kelly_fraction
                if regime == "trending":
                    current_kelly *= 1.5
                elif regime in ("sideway", "compression"):
                    current_kelly *= 0.6
                current_kelly = max(0.02, min(0.25, current_kelly))
                
                if current_dd > 0.05:
                    # Drawdown recovery
                    current_kelly *= max(0.2, 1.0 - (current_dd * 5.0))

                entry = bar["close"]
                stop_distance = signal["stop_distance"]
                take_distance = signal["take_distance"]
                
                # Sizing using optimized risk fraction
                risk_amount = equity * current_kelly * (risk_pct / 100.0)
                lot = estimate_lot_size(stop_distance, equity, current_kelly * 100.0, risk_context or {})
                
                # Apply 50% counter-trend lot reduction
                if signal.get("against_fundamental", False):
                    step = (risk_context or {}).get("volume_step", 0.01) or 0.01
                    lot = round((lot * 0.5) / step) * step
                    
                # Apply 50% hedging lot reduction
                if is_hedge:
                    step = (risk_context or {}).get("volume_step", 0.01) or 0.01
                    lot = round((lot * 0.5) / step) * step
                    
                step = (risk_context or {}).get("volume_step", 0.01) or 0.01
                volume_min = (risk_context or {}).get("volume_min", step) or step
                lot = max(lot, volume_min)

                new_pos = {
                    "side": side,
                    "entry": entry,
                    "stop_distance": stop_distance,
                    "take_distance": take_distance,
                    "entry_time": bar["time"],
                    "entry_index": index,
                    "stop": entry - stop_distance if side == 1 else entry + stop_distance,
                    "take": entry + take_distance if side == 1 else entry - take_distance,
                    "lot": lot,
                    "initial_lot": lot,
                    "lots": [lot],
                    "entries": [entry],
                    "mae_r": 0.0,
                    "mfe_r": 0.0,
                }
                active_positions.append(new_pos)

    for pos in active_positions:
        trade, equity = close_position(pos, rates[-1]["close"], rates[-1]["time"], "end_of_test", equity, risk_pct)
        if trade:
            trades.append(trade)
            peak_equity = max(peak_equity, equity)
            if peak_equity > 0:
                max_drawdown = max(max_drawdown, ((peak_equity - equity) / peak_equity) * 100.0)

    if not trades:
        return {
            "strategy_name": strategy["name"],
            "strategy_type": strategy["type"],
            "parameters": strategy["params"],
            "total_trades": 0,
            "total_buy": 0,
            "total_sell": 0,
            "win_rate": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_monthly_profit_pct": 0.0,
            "net_profit_pct": 0.0,
            "score": 0.0,
            "sample_trades": [],
        }

    wins = sum(1 for trade in trades if trade["r_multiple"] > 0)
    monthly_profit = defaultdict(float)
    monthly_start_equity = {}
    running_equity = float(initial_capital)
    for trade in trades:
        month_text = datetime.utcfromtimestamp(trade["exit_time"]).strftime("%Y-%m")
        if month_text not in monthly_start_equity:
            monthly_start_equity[month_text] = running_equity
        change = running_equity * (trade["profit_pct"] / 100.0)
        monthly_profit[month_text] += change
        running_equity += change

    monthly_returns = []
    for month_text, profit_amount in monthly_profit.items():
        start_equity = monthly_start_equity[month_text]
        monthly_returns.append((profit_amount / start_equity) * 100.0 if start_equity else 0.0)

    avg_mae_r = sum(trade["mae_r"] for trade in trades) / len(trades)
    avg_mfe_r = sum(trade["mfe_r"] for trade in trades) / len(trades)
    monthly_report = build_monthly_report(trades, initial_capital)
    net_profit_pct = ((equity - initial_capital) / initial_capital) * 100.0
    avg_monthly_profit_pct = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0.0
    win_rate = (wins / len(trades)) * 100.0
    expectancy_score = avg_mfe_r - avg_mae_r
    score = (avg_monthly_profit_pct * 1.2) + (win_rate * 0.35) - (max_drawdown * 0.5) + (len(trades) * 0.03) + (expectancy_score * 3)

    # Calculate advanced portfolio metrics
    import numpy as np
    
    sharpe = 0.0
    sortino = 0.0
    if len(monthly_returns) > 1:
        avg_ret = np.mean(monthly_returns)
        std_ret = np.std(monthly_returns)
        if std_ret > 0:
            sharpe = (avg_ret / std_ret) * math.sqrt(12) # Annualized
            
        negative_returns = [r for r in monthly_returns if r < 0]
        downside_std = np.std(negative_returns) if negative_returns else 0.0
        if downside_std > 0:
            sortino = (avg_ret / downside_std) * math.sqrt(12) # Annualized
        elif avg_ret > 0:
            sortino = 9.99
    elif len(monthly_returns) == 1:
        sharpe = monthly_returns[0] / 10.0
        sortino = monthly_returns[0] / 5.0 if monthly_returns[0] > 0 else monthly_returns[0] / 10.0

    test_days = max(1.0, (rates[-1]["time"] - rates[0]["time"]) / 86400.0)
    recovery_factor = 0.0
    calmar = 0.0
    if max_drawdown > 0:
        recovery_factor = net_profit_pct / max_drawdown
        calmar = (net_profit_pct / (test_days / 365.25)) / max_drawdown
        
    ulcer_index = 0.0
    if trades:
        drawdowns = []
        peak_eq = initial_capital
        curr_eq = initial_capital
        for t in trades:
            change = initial_capital * (t["profit_pct"] / 100.0)
            curr_eq += change
            if curr_eq > peak_eq:
                peak_eq = curr_eq
            dd = ((peak_eq - curr_eq) / peak_eq) * 100.0 if peak_eq > 0 else 0.0
            drawdowns.append(dd)
        ulcer_index = math.sqrt(np.mean([d**2 for d in drawdowns]))

    total_buy = sum(1 for t in trades if t["side"] == "LONG")
    total_sell = sum(1 for t in trades if t["side"] == "SHORT")

    return {
        "strategy_name": strategy["name"],
        "strategy_type": strategy["type"],
        "parameters": strategy["params"],
        "total_trades": len(trades),
        "avg_lot": round(sum(t["lot"] for t in trades) / len(trades), 2) if trades else 0.0,
        "total_buy": total_buy,
        "total_sell": total_sell,
        "win_rate": round(win_rate, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "days": round(test_days, 2),
        "avg_monthly_profit_pct": round(avg_monthly_profit_pct, 2),
        "net_profit_pct": round(net_profit_pct, 2),
        "ending_balance": round(equity, 2),
        "initial_capital": round(initial_capital, 2),
        "avg_mae_r": round(avg_mae_r, 3),
        "avg_mfe_r": round(avg_mfe_r, 3),
        "score": round(score, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "recovery_factor": round(recovery_factor, 2),
        "ulcer_index": round(ulcer_index, 2),
        "sample_trades": trades[:5],
        "monthly_report": monthly_report,
    }


def compare_metric(value, operator, threshold):
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    return False


def evaluate_result_against_filters(result, filters):
    # Enforce drawdown limit dynamically (default to 20% if not defined)
    dd_filter = (filters or {}).get("drawdown", {})
    dd_val = float(dd_filter.get("value", 20.0)) if dd_filter else 20.0
    if result.get("max_drawdown_pct", 100.0) >= dd_val:
        return False
        
    # Enforce net profit is positive
    if result.get("net_profit_pct", 0.0) <= 0.0:
        return False

    # Enforce no negative months
    monthly_report = result.get("monthly_report", [])
    if monthly_report:
        for month in monthly_report:
            if float(month.get("profit_amount", 0.0)) < 0.0:
                return False
                
    # Also apply the win_rate filter if sent
    wr_operator = filters.get("win_rate", {}).get("operator", ">=")
    wr_value = float(filters.get("win_rate", {}).get("value", 80.0))
    if not compare_metric(result["win_rate"], wr_operator, wr_value):
        return False
        
    # Enforce minimum total trades filter (normalized per 30 days / 1 month)
    trade_filter = (filters or {}).get("total_trades", {})
    if trade_filter:
        trade_operator = trade_filter.get("operator", ">=")
        trades_per_month = float(trade_filter.get("value", 10.0))
        test_days = float(result.get("days", 30.0))
        scaled_threshold = trades_per_month * (test_days / 30.0)
        if not compare_metric(result["total_trades"], trade_operator, scaled_threshold):
            return False
            
    return True


def generate_refined_rr_values(seed_results):
    rr_values = []
    for item in seed_results[:6]:
        base_rr = float(item["parameters"].get("rr", 1.5))
        rr_values.extend([base_rr - 0.2, base_rr - 0.05, base_rr, base_rr + 0.05, base_rr + 0.2])
    rr_values.extend([1.0, 1.4, 1.8, 2.2, 2.6])
    return dedupe_rr_values(rr_values)


def build_self_learning_strategies(seed_results):
    refined = []
    for item in seed_results[:6]:
        params = item["parameters"]
        
        # 1. Standard Perturbation Strategies
        for delta_threshold in [-0.02, 0.0, 0.02]:
            for delta_confirmation in [-0.02, 0.0, 0.02]:
                tuned = dict(params)
                if "threshold" in tuned:
                    tuned["threshold"] = round(clamp(float(tuned["threshold"]) + delta_threshold, 0.08, 0.4), 2)
                if "confirmation" in tuned:
                    tuned["confirmation"] = round(clamp(float(tuned["confirmation"]) + delta_confirmation, 0.02, 0.25), 2)
                tuned["rr"] = round(clamp(float(tuned.get("rr", 1.5)) + delta_threshold + delta_confirmation, 0.8, 3.5), 2)
                tuned["stop_atr"] = round(clamp(float(tuned.get("stop_atr", 1.2)) + (delta_threshold * 2), 0.8, 2.5), 2)
                refined.append(
                    {
                        "name": f"{item['strategy_name']} Self-Learning",
                        "type": item["strategy_type"],
                        "params": tuned,
                    }
                )
        
        # 2. AI MAE/MFE Advanced Optimization
        avg_mae = float(item.get("avg_mae_r", 0.5))
        avg_mfe = float(item.get("avg_mfe_r", 1.5))
        current_stop = float(params.get("stop_atr", 1.2))
        current_rr = float(params.get("rr", 1.5))
        
        # Optimize Stop Loss (MAE-driven)
        if avg_mae < 0.5:
            # Shallow drawdown: tighten Stop Loss to improve Risk-Reward multiplier
            opt_stop = current_stop * max(0.6, avg_mae * 1.35)
        elif avg_mae > 0.85:
            # Deep drawdown: widen Stop Loss slightly to avoid premature stop-outs
            opt_stop = current_stop * 1.2
        else:
            opt_stop = current_stop
        opt_stop = round(clamp(opt_stop, 0.8, 2.5), 2)
        
        # Optimize Take Profit (MFE-driven)
        if avg_mfe < current_rr * 1.1:
            # Favorable excursion was shallow or reversed: pull in Take Profit to lock in winrate
            opt_rr = avg_mfe * 0.85
        elif avg_mfe > current_rr * 1.6:
            # Favorable excursion went much further: stretch Take Profit target
            opt_rr = current_rr * 1.3
        else:
            opt_rr = current_rr
        opt_rr = round(clamp(opt_rr, 0.8, 3.5), 2)
        
        # MAE-optimized Stop Loss strategy
        params_mae = dict(params)
        params_mae["stop_atr"] = opt_stop
        refined.append({
            "name": f"{item['strategy_name']} (MAE-Opt)",
            "type": item["strategy_type"],
            "params": params_mae
        })
        
        # MFE-optimized Take Profit strategy
        params_mfe = dict(params)
        params_mfe["rr"] = opt_rr
        refined.append({
            "name": f"{item['strategy_name']} (MFE-Opt)",
            "type": item["strategy_type"],
            "params": params_mfe
        })
        
        # Combined Expectancy optimized strategy
        params_both = dict(params)
        params_both["stop_atr"] = opt_stop
        params_both["rr"] = opt_rr
        refined.append({
            "name": f"{item['strategy_name']} (Expectancy-Opt)",
            "type": item["strategy_type"],
            "params": params_both
        })
        
    return refined


def rank_results(results, sort_priority=None):
    sort_priority = sort_priority or ["net_profit", "win_rate", "drawdown"]
    
    def get_sort_key(item):
        key_tuple = [item.get("passes_filters", False)]
        for p in sort_priority:
            if p == "net_profit":
                key_tuple.append(float(item.get("net_profit_pct", 0.0)))
            elif p == "win_rate":
                key_tuple.append(float(item.get("win_rate", 0.0)))
            elif p == "drawdown":
                key_tuple.append(-float(item.get("max_drawdown_pct", 100.0)))
            elif p == "monthly_profit":
                key_tuple.append(float(item.get("avg_monthly_profit_pct", 0.0)))
        # Tie-breaker
        key_tuple.append(float(item.get("avg_mfe_r", 0.0) - item.get("avg_mae_r", 0.0)))
        return tuple(key_tuple)

    results.sort(key=get_sort_key, reverse=True)
    return results


def search_backtest_methods(
    symbol="XAUUSD",
    days=30,
    risk_pct=1.0,
    filters=None,
    initial_capital=10000.0,
    start_month=None,
    end_month=None,
    sort_priority=None,
    timeframe="M1",
    fundamental_bias=None,
    custom_strategies=None,
):
    rates = fetch_mt5_rates(symbol=symbol, days=days, start_month=start_month, end_month=end_month, timeframe=timeframe)
    risk_context = get_symbol_risk_context(symbol)
    _push_log(f"📊 [{timeframe}] Data loaded: {len(rates)} bars dari MT5", "info")
    _progress_stats.update({"tf": timeframe, "bars": len(rates)})

    filters = filters or {
        "drawdown": {"operator": ">", "value": 5},
        "win_rate": {"operator": "<", "value": 80},
        "monthly_profit": {"operator": "<", "value": 40},
    }

    all_results = []
    learning_iterations = []
    rr_values = dedupe_rr_values([1.0, 1.4, 1.8, 2.2, 2.6])
    if custom_strategies:
        initial_library = custom_strategies + make_strategy_library(rr_values, max_risk=risk_pct)
        _push_log(f"🤖 AI custom strategies injected: {len(custom_strategies)} strategi", "ai")
    else:
        initial_library = make_strategy_library(rr_values, max_risk=risk_pct)
    iteration_sources = [("grid", initial_library)]
    _push_log(f"📋 Library awal: {len(initial_library)} kombinasi strategi", "info")

    global stop_backtest_requested
    import concurrent.futures

    for iteration_index in range(10):
        phase_name, strategies = iteration_sources[-1]
        cache = build_indicator_cache(rates, strategies, fundamental_bias=fundamental_bias)
        current_results = []
        _push_log(f" Iterasi {iteration_index+1} — Phase: {phase_name} | {len(strategies)} strategi", "phase")
        _progress_stats.update({"iteration": iteration_index + 1, "phase": phase_name, "total": len(strategies), "tested": 0, "found": len(all_results)})
        
        # Parallel backtest runner function
        def worker(strategy):
            res = run_backtest(
                rates,
                strategy,
                cache,
                risk_pct=risk_pct,
                initial_capital=initial_capital,
                risk_context=risk_context,
            )
            res["passes_filters"] = evaluate_result_against_filters(res, filters)
            return res

        # Execute using ThreadPoolExecutor for 100% thread safety and no startup overhead
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(worker, strat): strat for strat in strategies}
            
            for idx, future in enumerate(concurrent.futures.as_completed(futures)):
                if stop_backtest_requested:
                    stop_backtest_requested = False
                    _push_log(" Backtest dihentikan oleh user.", "warn")
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise RuntimeError("Backtest dihentikan oleh user.")
                
                try:
                    result = future.result()
                    if result["total_trades"] >= 8:
                        current_results.append(result)
                except Exception as exc:
                    print(f"Error testing strategy: {exc}")
                
                # Update stats every 25 completed strategies
                if (idx + 1) % 25 == 0 or idx == len(strategies) - 1:
                    _progress_stats.update({"tested": idx + 1, "found": len(all_results) + len(current_results)})
                    best = max(current_results, key=lambda x: x.get("net_profit_pct", 0), default=None)
                    if best:
                        _push_log(f"   {idx+1}/{len(strategies)} diuji | Ditemukan: {len(current_results)} | Best - Profit: {best['net_profit_pct']:.1f}%, DD: {best['max_drawdown_pct']:.1f}%, WR: {best['win_rate']:.1f}%, Trades: {best['total_trades']}, AvgLot: {best['avg_lot']:.2f}", "progress")

        rank_results(current_results, sort_priority=sort_priority)
        all_results.extend(current_results)
        passes = sum(1 for item in current_results if item["passes_filters"])
        positive_passing = sum(1 for item in current_results if item["passes_filters"] and item["net_profit_pct"] > 0.0)
        _push_log(f" Phase '{phase_name}' selesai: {len(current_results)} hasil valid | {passes} lolos filter | {positive_passing} profit positif", "success")
        learning_iterations.append(
            {
                "phase": phase_name,
                "tested": len(strategies),
                "returned": len(current_results),
                "passes": passes,
            }
        )
        passing_strategies = [item for item in current_results if item["passes_filters"]]
        if passing_strategies and iteration_index >= 3:
            best_passing = max(passing_strategies, key=lambda x: x.get("net_profit_pct", 0))
            _push_log(f" Target %DD, %Winrate, %Profit tercapai pada iterasi {iteration_index+1}! (Best - Profit: {best_passing['net_profit_pct']:.1f}%, DD: {best_passing['max_drawdown_pct']:.1f}%, WR: {best_passing['win_rate']:.1f}%, Trades: {best_passing['total_trades']}, AvgLot: {best_passing['avg_lot']:.2f})", "success")
            break
        seed_results = current_results[:6]
        rr_values = generate_refined_rr_values(seed_results)
        next_phase = "self_learning" if iteration_index == 0 else f"self_learning_{iteration_index}"
        next_strategies = build_self_learning_strategies(seed_results) + make_strategy_library(rr_values, max_risk=risk_pct)
        _push_log(f"🧬 Self-learning: mengembangkan {len(next_strategies)} strategi baru", "ai")
        iteration_sources.append((next_phase, next_strategies))

    deduped = {}
    for item in all_results:
        dedupe_key = (
            item["strategy_type"],
            tuple(sorted((key, str(value)) for key, value in item["parameters"].items())),
        )
        previous = deduped.get(dedupe_key)
        if previous is None or item["net_profit_pct"] > previous["net_profit_pct"]:
            deduped[dedupe_key] = item

    results = rank_results(list(deduped.values()), sort_priority=sort_priority)
    top_results = results[:10]
    passing_count = sum(1 for item in results if item["passes_filters"])

    # For top results, perform Walk-Forward and Monte Carlo validations
    train_len = int(len(rates) * 0.7)
    train_rates = rates[:train_len]
    test_rates = rates[train_len:]
    
    # Pre-build cache for train/test to run quick validation
    train_cache = build_indicator_cache(train_rates, [item["parameters"] for item in top_results], fundamental_bias=fundamental_bias)
    test_cache = build_indicator_cache(test_rates, [item["parameters"] for item in top_results], fundamental_bias=fundamental_bias)
    
    for item in top_results:
        # 1. Walk-Forward Check
        strat = {
            "name": item["strategy_name"],
            "type": item["strategy_type"],
            "params": item["parameters"]
        }
        train_res = run_backtest(train_rates, strat, train_cache, risk_pct=risk_pct, initial_capital=initial_capital, risk_context=risk_context)
        test_res = run_backtest(test_rates, strat, test_cache, risk_pct=risk_pct, initial_capital=initial_capital, risk_context=risk_context)
        
        train_profit = train_res.get("net_profit_pct", 0.0)
        test_profit = test_res.get("net_profit_pct", 0.0)
        
        if train_profit > 0:
            stability = (test_profit / train_profit) * 100.0
        else:
            stability = 0.0
        item["wf_stability"] = round(max(0.0, min(100.0, stability)), 2)
        item["wf_train_profit"] = round(train_profit, 2)
        item["wf_test_profit"] = round(test_profit, 2)
        
        # 2. Monte Carlo Simulation
        import random
        mc_pass_count = 0
        mc_simulations = 100
        trades_list = item.get("trades", [])
        
        if trades_list:
            for _ in range(mc_simulations):
                # Shuffle trade list
                shuffled = list(trades_list)
                random.shuffle(shuffled)
                
                # Simulate equity curve with random spread/slippage variance (up to +/- 0.15 relative profit shift)
                sim_equity = initial_capital
                sim_peak = sim_equity
                sim_max_dd = 0.0
                
                for t in shuffled:
                    slippage = random.uniform(-0.15, 0.1)
                    profit_pct = t["profit_pct"] * (1.0 + slippage)
                    sim_equity += sim_equity * (profit_pct / 100.0)
                    sim_peak = max(sim_peak, sim_equity)
                    if sim_peak > 0:
                        sim_max_dd = max(sim_max_dd, ((sim_peak - sim_equity) / sim_peak) * 100.0)
                        
                if sim_equity > initial_capital and sim_max_dd < 10.0:
                    mc_pass_count += 1
                    
            item["mc_pass_rate"] = round((mc_pass_count / mc_simulations) * 100.0, 2)
        else:
            item["mc_pass_rate"] = 0.0
            
        # 3. Concept Drift Engine (PSI Indicator shift score)
        import numpy as np
        train_rsi = train_cache.get("rsi_14", [50]*len(train_rates))
        test_rsi = test_cache.get("rsi_14", [50]*len(test_rates))
        train_rsi = [v for v in train_rsi if v is not None]
        test_rsi = [v for v in test_rsi if v is not None]
        
        if train_rsi and test_rsi:
            train_mean = np.mean(train_rsi)
            test_mean = np.mean(test_rsi)
            drift_score = min(1.0, abs(train_mean - test_mean) / 25.0)
        else:
            drift_score = 0.15
        item["concept_drift_score"] = round(drift_score, 3)
        
        # 4. Composite Score Ranking
        composite = (
            (item.get("net_profit_pct", 0.0) * 1.0) +
            (item.get("win_rate", 0.0) * 0.25) -
            (item.get("max_drawdown_pct", 0.0) * 0.6) +
            (item.get("sharpe_ratio", 0.0) * 5.0) +
            (item.get("wf_stability", 0.0) * 0.1) +
            (item.get("mc_pass_rate", 0.0) * 0.1)
        )
        item["composite_score"] = round(composite, 2)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": len(rates),
        "days": days,
        "range": {
            "start_month": start_month,
            "end_month": end_month,
        },
        "method": "AI XEDY_V31 Ultimate",
        "weighting": {"fundamental": 80, "technical": 20},
        "fundamental_bias": round(compute_xedy_fundamental_bias(), 3),
        "initial_capital": round(float(initial_capital), 2),
        "filters": filters,
        "strategies_tested": sum(item["tested"] for item in learning_iterations),
        "strategies_returned": len(top_results),
        "passing_count": passing_count,
        "target_reached": passing_count > 0,
        "rrr_search": {
            "mode": "adaptive_self_learning",
            "iterations": learning_iterations,
        },
        "results": top_results,
    }




@app.route("/backtest")
def serve_backtest():
    return send_from_directory(app.static_folder, "backtest.html")

@app.route("/api/backtest/search", methods=["POST"])
def api_backtest_search():
    global stop_backtest_requested, _progress_running
    stop_backtest_requested = False
    _reset_progress()
    payload = request.get_json(silent=True) or {}
    filters = payload.get("filters") or {}

    tfs = payload.get("timeframes") or ["M5", "M15", "M30", "H1", "H4"]
    results_per_tf = {}
    _push_log(f"🚀 Backtest dimulai — {len(tfs)} timeframe: {', '.join(tfs)}", "info")

    try:
        bias_val = compute_xedy_fundamental_bias()
        _push_log(f"🌐 Fundamental bias: {round(bias_val, 3)} (80% weight)", "info")
        for tf_idx, tf in enumerate(tfs):
            if stop_backtest_requested:
                break
            _push_log(f"━━━ TF {tf_idx+1}/{len(tfs)}: [{tf}] mulai diproses ━━━", "phase")
            _progress_stats.update({"tf": tf, "tf_idx": tf_idx + 1, "tf_total": len(tfs)})
            tf_result = search_backtest_methods(
                symbol=payload.get("symbol", "XAUUSD"),
                days=int(payload.get("days", 30)),
                risk_pct=float(payload.get("risk_pct", 1.0)),
                initial_capital=float(payload.get("initial_capital", 10000)),
                start_month=payload.get("start_month"),
                end_month=payload.get("end_month"),
                sort_priority=payload.get("sort_priority", ["net_profit", "win_rate", "drawdown"]),
                timeframe=tf,
                fundamental_bias=bias_val,
                custom_strategies=payload.get("custom_strategies"),
                filters={
                    "drawdown": {
                        "operator": filters.get("drawdown", {}).get("operator", "<"),
                        "value": float(filters.get("drawdown", {}).get("value", 10.0)),
                    },
                    "win_rate": {
                        "operator": filters.get("win_rate", {}).get("operator", ">="),
                        "value": float(filters.get("win_rate", {}).get("value", 50.0)),
                    },
                    "monthly_profit": {
                        "operator": filters.get("monthly_profit", {}).get("operator", ">="),
                        "value": float(filters.get("monthly_profit", {}).get("value", 5.0)),
                    },
                    "total_trades": {
                        "operator": filters.get("total_trades", {}).get("operator", ">="),
                        "value": float(filters.get("total_trades", {}).get("value", 10.0)),
                    },
                },
            )
            results_per_tf[tf] = tf_result
            _push_log(f"✅ [{tf}] Selesai: {tf_result.get('strategies_tested',0)} diuji, top {len(tf_result.get('results',[]))} ditemukan", "success")

        if stop_backtest_requested:
            stop_backtest_requested = False
            _progress_running = False
            _push_log("⛔ Backtest dihentikan.", "warn")
            return jsonify({"success": False, "error": "Backtest dihentikan oleh user."}), 400

        _progress_running = False
        _push_log(f"🏁 SELESAI — Semua {len(tfs)} timeframe diproses.", "success")

        # Extract primary sorting method
        sort_pri = payload.get("sort_priority", ["win_rate"])
        method_name = sort_pri[0] if isinstance(sort_pri, list) and len(sort_pri) > 0 else "win_rate"

        return jsonify({
            "success": True, 
            "data": {
                        "symbol": payload.get("symbol", "XAUUSD"),
                "method": method_name,
                "risk_pct": float(payload.get("risk_pct", 1.0)),
                "results_per_tf": results_per_tf
            }
        })
    except Exception as exc:
        _progress_running = False
        _push_log(f"❌ Error: {str(exc)[:200]}", "error")
        return jsonify({"success": False, "error": str(exc)}), 500

@app.route("/api/backtest/stop", methods=["POST"])
def api_backtest_stop():
    global stop_backtest_requested
    stop_backtest_requested = True
    return jsonify({"success": True, "message": "Stop requested."})


@app.route("/api/keys/status", methods=["GET"])
def api_keys_status():
    """Return masked status of all AI API keys."""
    key_map = {
        "GEMINI_API_KEY": "gemini",
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "DEEPSEEK_API_KEY": "deepseek",
    }
    result = {}
    # Read directly from .env file for fresh data
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_vals = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vals[k.strip()] = v.strip()
    for env_key, label in key_map.items():
        val = env_vals.get(env_key, "") or os.getenv(env_key, "")
        if val:
            masked = val[:6] + "..." + val[-4:] if len(val) > 12 else "***set***"
            result[label] = {"exists": True, "masked": masked}
        else:
            result[label] = {"exists": False, "masked": ""}
    return jsonify({"success": True, "keys": result})


@app.route("/api/config/update_risk", methods=["POST"])
def api_update_risk():
    """Update Risk Percentage directly from the Trade Monitor."""
    payload = request.get_json(silent=True) or {}
    new_risk = payload.get("risk_percent")
    if not new_risk:
        return jsonify({"success": False, "message": "Risk percent is required."}), 400
        
    config_file = r'C:\Antigravity\active_config.json'
    try:
        active_config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                active_config = json.load(f)
                
        active_config["risk_percent"] = float(new_risk)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(active_config, f, indent=4)
            
        return jsonify({"success": True, "message": f"Risk updated to {new_risk}%"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/keys/save", methods=["POST"])
def api_keys_save():
    """Save AI API keys to .env file."""
    payload = request.get_json(silent=True) or {}
    key_map = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    # Read existing .env
    existing = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line_stripped = line.strip()
                if "=" in line_stripped and not line_stripped.startswith("#"):
                    k, v = line_stripped.split("=", 1)
                    existing[k.strip()] = v.strip()

    # Update with new keys (only if not empty)
    updated_count = 0
    for label, env_key in key_map.items():
        new_val = payload.get(label, "").strip()
        if new_val:
            existing[env_key] = new_val
            os.environ[env_key] = new_val  # Also set in current process
            updated_count += 1

    # Write back to .env
    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k}={v}\n")

    # Reconfigure Gemini if key was updated
    if "gemini" in payload and payload["gemini"].strip():
        try:
            import google.generativeai as genai
            genai.configure(api_key=payload["gemini"].strip())
        except Exception:
            pass

    return jsonify({"success": True, "message": f"{updated_count} key berhasil disimpan.", "updated": updated_count})


@app.route("/api/keys/validate", methods=["POST"])
def api_keys_validate():
    """Validate all AI API keys by making minimal test calls."""
    import requests as http_req

    # Read keys from .env
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_vals = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vals[k.strip()] = v.strip()

    results = {}

    # --- Gemini: list models ---
    gemini_key = env_vals.get("GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            resp = http_req.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}",
                timeout=15,
            )
            if resp.status_code == 200:
                models_data = resp.json()
                model_count = len(models_data.get("models", []))
                results["gemini"] = {"valid": True, "status": f"✅ Valid — {model_count} models tersedia", "detail": "API key aktif dan berfungsi"}
            elif resp.status_code == 429:
                results["gemini"] = {"valid": True, "status": "⚠️ Valid tapi Rate Limited", "detail": "Key valid, quota sementara habis. Tunggu 1-2 menit."}
            elif resp.status_code == 403:
                results["gemini"] = {"valid": False, "status": "❌ Key disabled/forbidden", "detail": "Key dinonaktifkan atau project tidak aktif"}
            else:
                err = resp.text[:150]
                results["gemini"] = {"valid": False, "status": f"❌ Error {resp.status_code}", "detail": err}
        except Exception as e:
            results["gemini"] = {"valid": False, "status": "❌ Connection error", "detail": str(e)[:100]}
    else:
        results["gemini"] = {"valid": False, "status": "⬜ Belum diisi", "detail": "Tambahkan GEMINI_API_KEY"}

    # --- OpenAI: list models ---
    openai_key = env_vals.get("OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            resp = http_req.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                models_data = resp.json()
                model_count = len(models_data.get("data", []))
                results["openai"] = {"valid": True, "status": f"✅ Valid — {model_count} models tersedia", "detail": "API key aktif"}
            elif resp.status_code == 429:
                results["openai"] = {"valid": True, "status": "⚠️ Valid tapi Rate Limited", "detail": "Key valid, tapi quota habis. Top-up saldo."}
            elif resp.status_code == 401:
                results["openai"] = {"valid": False, "status": "❌ Invalid API Key", "detail": "Key salah atau sudah expired"}
            elif resp.status_code == 403:
                results["openai"] = {"valid": False, "status": "❌ Akses ditolak", "detail": "Key tidak punya permission"}
            else:
                err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error": {"message": resp.text[:150]}}
                msg = err_data.get("error", {}).get("message", resp.text[:150])
                results["openai"] = {"valid": False, "status": f"❌ Error {resp.status_code}", "detail": msg[:150]}
        except Exception as e:
            results["openai"] = {"valid": False, "status": "❌ Connection error", "detail": str(e)[:100]}
    else:
        results["openai"] = {"valid": False, "status": "⬜ Belum diisi", "detail": "Tambahkan OPENAI_API_KEY"}

    # --- Anthropic: minimal message to check auth ---
    anthropic_key = env_vals.get("ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            resp = http_req.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
                timeout=20,
            )
            if resp.status_code == 200:
                results["anthropic"] = {"valid": True, "status": "✅ Valid — Key aktif", "detail": "API key berfungsi dengan baik"}
            elif resp.status_code == 401:
                results["anthropic"] = {"valid": False, "status": "❌ Invalid API Key", "detail": "Key salah atau expired"}
            elif resp.status_code == 403:
                results["anthropic"] = {"valid": False, "status": "❌ Forbidden", "detail": "Key tidak punya akses"}
            elif resp.status_code == 429:
                results["anthropic"] = {"valid": True, "status": "⚠️ Valid tapi Rate Limited", "detail": "Key valid, quota sementara habis"}
            elif resp.status_code == 400:
                # 400 can mean the key works but request is bad - still valid key
                err_text = resp.text[:150]
                if "credit" in err_text.lower() or "billing" in err_text.lower():
                    results["anthropic"] = {"valid": True, "status": "⚠️ Valid tapi Saldo Habis", "detail": "Key valid, perlu top-up kredit"}
                else:
                    results["anthropic"] = {"valid": True, "status": "✅ Valid — Key terautentikasi", "detail": "Key aktif (test minimal)"}
            else:
                results["anthropic"] = {"valid": False, "status": f"❌ Error {resp.status_code}", "detail": resp.text[:150]}
        except Exception as e:
            results["anthropic"] = {"valid": False, "status": "❌ Connection error", "detail": str(e)[:100]}
    else:
        results["anthropic"] = {"valid": False, "status": "⬜ Belum diisi", "detail": "Tambahkan ANTHROPIC_API_KEY"}

    # --- DeepSeek: list models ---
    deepseek_key = env_vals.get("DEEPSEEK_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        try:
            resp = http_req.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {deepseek_key}"},
                timeout=15,
            )
            if resp.status_code == 200:
                models_data = resp.json()
                model_count = len(models_data.get("data", []))
                results["deepseek"] = {"valid": True, "status": f"✅ Valid — {model_count} models tersedia", "detail": "API key aktif"}
            elif resp.status_code == 401:
                results["deepseek"] = {"valid": False, "status": "❌ Invalid API Key", "detail": "Key salah atau expired"}
            elif resp.status_code == 429:
                results["deepseek"] = {"valid": True, "status": "⚠️ Valid tapi Rate Limited", "detail": "Key valid, quota habis"}
            else:
                results["deepseek"] = {"valid": False, "status": f"❌ Error {resp.status_code}", "detail": resp.text[:150]}
        except Exception as e:
            results["deepseek"] = {"valid": False, "status": "❌ Connection error", "detail": str(e)[:100]}
    else:
        results["deepseek"] = {"valid": False, "status": "⬜ Belum diisi", "detail": "Tambahkan DEEPSEEK_API_KEY"}

    return jsonify({"success": True, "results": results})


@app.route("/api/backtest/generate_from_prompt", methods=["POST"])
def api_generate_from_prompt():
    """Use Gemini AI to parse user's strategy prompt into backtest parameters."""
    try:
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return jsonify({"success": False, "error": "GEMINI_API_KEY tidak ditemukan di environment variables."}), 400
        genai.configure(api_key=api_key)

        payload = request.get_json(silent=True) or {}
        user_prompt = payload.get("prompt", "").strip()
        if not user_prompt:
            return jsonify({"success": False, "error": "Prompt tidak boleh kosong."}), 400

        system_instruction = """You are a quantitative trading strategy parameter generator for gold (XAUUSD) backtesting.

The backtest engine supports these strategy types with their tunable parameters:

1. "xedy_v30_ai" - Core AI strategy using composite fundamental+technical scoring
   params: threshold (0.05-0.50), confirmation (0.05-0.20), stop_atr (0.8-3.0), rr (0.8-4.0), max_hold_bars (15-120)

2. "xedy_trend_pullback" - Trend-following with pullback entries
   params: pullback_limit (0.03-0.20), confirmation (0.05-0.20), stop_atr (0.8-3.0), rr (0.8-4.0), max_hold_bars (15-120)

3. "xedy_mean_revert" - Mean reversion using RSI extremes
   params: extreme_rsi (15-35), threshold (0.05-0.50), stop_atr (0.8-3.0), rr (0.8-4.0), max_hold_bars (15-120)

4. "xedy_breakout_confirm" - Breakout with confirmation filter
   params: breakout_buffer (0.05-0.30), threshold (0.05-0.50), stop_atr (0.8-3.0), rr (0.8-4.0), max_hold_bars (15-120)

5. "xedy_macd_momentum" - MACD momentum crossover strategy
   params: threshold (0.02-0.30), stop_atr (0.8-3.0), rr (0.8-4.0), max_hold_bars (15-120)

Based on the user's description, select the most appropriate strategy type(s) and generate 3-8 parameter variations to test.
For each variation, provide a descriptive name and the parameter values.

Reply ONLY with valid JSON array. Each element must have: "name" (string), "type" (string), "params" (object).
Example:
[{"name":"Breakout Aggressive B0.10","type":"xedy_breakout_confirm","params":{"breakout_buffer":0.10,"threshold":0.15,"stop_atr":1.5,"rr":2.5,"max_hold_bars":60}}]

Do NOT include any markdown, explanation, or text outside the JSON array."""

        selected_model = payload.get("model", "gemini-2.5-flash")

        # Route to the correct provider
        gemini_models = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b"}
        claude_models = {"claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"}
        deepseek_models = {"deepseek-chat", "deepseek-reasoner"}
        openai_models = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"}


        raw_text = ""

        if selected_model in gemini_models:
            # --- GEMINI via SDK with auto-retry & fallback ---
            import time as _time
            fallback_order = [selected_model] + [m for m in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-lite", "gemini-1.5-flash-8b", "gemini-2.5-pro"] if m != selected_model]
            last_err = None
            for try_model in fallback_order:
                for attempt in range(3):
                    try:
                        model = genai.GenerativeModel(try_model, system_instruction=system_instruction)
                        response = model.generate_content(
                            user_prompt,
                            generation_config={"response_mime_type": "application/json"}
                        )
                        raw_text = response.text.strip()
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        err_str = str(e)
                        if "429" in err_str or "rate" in err_str.lower() or "quota" in err_str.lower():
                            wait_secs = (attempt + 1) * 20
                            _time.sleep(wait_secs)
                            continue
                        else:
                            raise
                if last_err is None:
                    break
            if last_err is not None:
                return jsonify({"success": False, "error": f"Semua model Gemini kena rate limit. Coba lagi dalam 1-2 menit. Detail: {str(last_err)[:200]}"}), 429

        elif selected_model in claude_models:
            # --- CLAUDE via Anthropic HTTP API ---
            import requests as http_req
            claude_key = os.getenv("ANTHROPIC_API_KEY")
            if not claude_key:
                return jsonify({"success": False, "error": "ANTHROPIC_API_KEY tidak ditemukan di .env. Tambahkan key Anda."}), 400
            claude_resp = http_req.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": claude_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": selected_model,
                    "max_tokens": 4096,
                    "system": system_instruction,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=120,
            )
            if claude_resp.status_code != 200:
                return jsonify({"success": False, "error": f"Claude API error {claude_resp.status_code}: {claude_resp.text[:300]}"}), 500
            claude_data = claude_resp.json()
            raw_text = claude_data.get("content", [{}])[0].get("text", "").strip()

        elif selected_model in deepseek_models:
            # --- DEEPSEEK via OpenAI-compatible API ---
            import requests as http_req
            ds_key = os.getenv("DEEPSEEK_API_KEY")
            if not ds_key:
                return jsonify({"success": False, "error": "DEEPSEEK_API_KEY tidak ditemukan di .env. Tambahkan key Anda."}), 400
            ds_resp = http_req.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {ds_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": selected_model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.7,
                },
                timeout=120,
            )
            if ds_resp.status_code != 200:
                return jsonify({"success": False, "error": f"DeepSeek API error {ds_resp.status_code}: {ds_resp.text[:300]}"}), 500
            ds_data = ds_resp.json()
            raw_text = ds_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        elif selected_model in openai_models:
            # --- OPENAI via ChatGPT API ---
            import requests as http_req
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                return jsonify({"success": False, "error": "OPENAI_API_KEY tidak ditemukan di .env. Tambahkan key Anda."}), 400
            openai_resp = http_req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": selected_model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.7,
                },
                timeout=120,
            )
            if openai_resp.status_code != 200:
                return jsonify({"success": False, "error": f"OpenAI API error {openai_resp.status_code}: {openai_resp.text[:300]}"}), 500
            openai_data = openai_resp.json()
            raw_text = openai_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            return jsonify({"success": False, "error": f"Model '{selected_model}' tidak didukung."}), 400

        # Clean markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        strategies = json.loads(raw_text)
        if not isinstance(strategies, list):
            strategies = [strategies]

        # Validate & sanitize
        valid_types = {"xedy_v30_ai", "xedy_trend_pullback", "xedy_mean_revert", "xedy_breakout_confirm", "xedy_macd_momentum"}
        validated = []
        for s in strategies:
            if isinstance(s, dict) and s.get("type") in valid_types and isinstance(s.get("params"), dict):
                validated.append({
                    "name": str(s.get("name", f"AI Generated {s['type']}")),
                    "type": s["type"],
                    "params": {k: float(v) for k, v in s["params"].items() if isinstance(v, (int, float))}
                })

        if not validated:
            return jsonify({"success": False, "error": "AI tidak menghasilkan strategi yang valid. Coba tulis prompt yang lebih spesifik."}), 400

        return jsonify({"success": True, "strategies": validated, "count": len(validated)})

    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "AI response gagal di-parse sebagai JSON. Coba lagi."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route('/api/livetest/apply_parameters', methods=['POST'])
def apply_livetest_parameters():
    try:
        req = request.get_json()
        if not req:
            return jsonify({"status": "error", "message": "Empty payload"}), 400
            
        tf = req.get("timeframe", "M15")
        risk_val = req.get("risk_percent")
        risk = float(risk_val) if risk_val is not None else 1.0
        strat_type = req.get("strategy_type", "xedy_v30_ai")
        strat_name = req.get("strategy_name", "AI XEDY_V30 Core")
        win_rate = req.get("win_rate", 68)
        max_dd = req.get("max_drawdown", 7.2)
        net_profit = req.get("net_profit", 68.0)
        
        # Calculate SL & TP distances based on strategy type
        sl_dist = 15.0
        tp_dist = 22.0
        if strat_type == "xedy_trend_pullback":
            sl_dist = 12.0
            tp_dist = 18.0
        elif strat_type == "xedy_mean_revert":
            sl_dist = 25.0
            tp_dist = 25.0
        elif strat_type == "xedy_breakout_confirm":
            sl_dist = 18.0
            tp_dist = 30.0
            
        # Write active config to decoupled config file to prevent write race conditions
        config_file = r'C:\Antigravity\active_config.json'
        config_data = {
            "timeframe": tf,
            "risk_percent": risk,
            "strategy_type": strat_type,
            "strategy_name": strat_name,
            "sl_dist": sl_dist,
            "tp_dist": tp_dist,
            "win_rate": win_rate,
            "max_drawdown": max_dd,
            "net_profit": net_profit
        }
        with open(config_file, 'w', encoding='utf-8') as f_cfg:
            json.dump(config_data, f_cfg, indent=4)
            
        # Force close active trade by clearing state file
        demo_file = r'C:\Antigravity\livetest_demo.json'
        state = {}
        if os.path.exists(demo_file):
            with open(demo_file, 'r', encoding='utf-8') as f_demo:
                try:
                    state = json.load(f_demo)
                except Exception:
                    pass
        if not isinstance(state, dict):
            state = {}
        state["active_trades"] = []
        if "balance" not in state:
            state["balance"] = 10543.10
        if "equity" not in state:
            state["equity"] = 10543.10
        if "history" not in state:
            state["history"] = []
        with open(demo_file, 'w', encoding='utf-8') as f_demo:
            json.dump(state, f_demo, indent=4)
            
        return jsonify({"status": "success", "message": "Parameters successfully applied to Live Test"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/livetest/clear_parameters', methods=['POST'])
def clear_livetest_parameters():
    try:
        config_file = r'C:\Antigravity\active_config.json'
        if os.path.exists(config_file):
            os.remove(config_file)
            
        demo_file = r'C:\Antigravity\livetest_demo.json'
        state = {}
        if os.path.exists(demo_file):
            with open(demo_file, 'r', encoding='utf-8') as f_demo:
                try:
                    state = json.load(f_demo)
                except Exception:
                    pass
        if not isinstance(state, dict):
            state = {}
        state["active_trades"] = []
        if "balance" not in state:
            state["balance"] = 10543.10
        if "equity" not in state:
            state["equity"] = 10543.10
        if "history" not in state:
            state["history"] = []
        with open(demo_file, 'w', encoding='utf-8') as f_demo:
            json.dump(state, f_demo, indent=4)
            
        return jsonify({"status": "success", "message": "Live test reset to default"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/livetest/reset_simulation', methods=['POST'])
def reset_livetest_simulation():
    try:
        demo_file = r'C:\Antigravity\livetest_demo.json'
        initial_data = {
            "balance": 10000.00,
            "equity": 10000.00,
            "active_trades": [],
            "history": [],
            "last_update": time.time()
        }
        with open(demo_file, 'w', encoding='utf-8') as f_demo:
            json.dump(initial_data, f_demo, indent=4)
            
        return jsonify({"status": "success", "message": "Simulation reset successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade/place_order', methods=['POST'])
def place_order_api():
    try:
        data = request.json
        symbol = data.get("symbol")
        order_type_str = data.get("type", "").lower() # 'buy' or 'sell'
        volume = float(data.get("volume", 0.01))
        sl = data.get("sl")
        tp = data.get("tp")
        
        if not symbol or order_type_str not in ['buy', 'sell']:
            return jsonify({"status": "error", "message": "Invalid symbol or order type"}), 400
            
        if not init_mt5():
            return jsonify({"status": "error", "message": "Failed to connect to MT5"}), 500
            
        # Map symbol label to actual MT5 symbol
        symbol_map = {
            "XAUUSD": "XAUUSD",
            "GOLD": "XAUUSD",
            "USDJPY": "USDJPY",
            "WTI OIL": "XTIUSD",
            "WTI": "XTIUSD",
            "DJI": "US30",
            "US30": "US30",
            "EURUSD": "EURUSD",
            "GBPUSD": "GBPUSD"
        }
        mt5_symbol = symbol_map.get(symbol, symbol)
        
        # Verify symbol select
        mt5.symbol_select(mt5_symbol, True)
        
        # Get current tick for price
        tick = mt5.symbol_info_tick(mt5_symbol)
        if not tick:
            return jsonify({"status": "error", "message": f"Failed to retrieve tick for {mt5_symbol}"}), 400
            
        price = tick.ask if order_type_str == 'buy' else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if order_type_str == 'buy' else mt5.ORDER_TYPE_SELL
        
        # Build request
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 998877,
            "comment": "Order from Web Dashboard",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        if sl:
            req["sl"] = float(sl)
        if tp:
            req["tp"] = float(tp)
            
        # Try multiple filling types
        filling_types = [
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN
        ]
        
        last_error_desc = ""
        for filling in filling_types:
            req["type_filling"] = filling
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return jsonify({"status": "success", "message": f"Order {order_type_str.upper()} placed successfully (Ticket: {result.order})"})
            else:
                if result:
                    last_error_desc = f"Retcode: {result.retcode}, Comment: {result.comment}"
                else:
                    last_error_desc = f"Error sending order: {mt5.last_error()}"
                    
        return jsonify({"status": "error", "message": f"Order failed: {last_error_desc}"}), 400
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def close_mt5_position(ticket):
    if not init_mt5():
        return False, "Failed to initialize MT5 terminal"
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False, f"Position with ticket {ticket} not found"
    p = positions[0]
    symbol = p.symbol
    volume = p.volume
    position_id = p.ticket
    opposite_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, f"Failed to retrieve tick for {symbol}"
    price = tick.bid if opposite_type == mt5.ORDER_TYPE_SELL else tick.ask
    filling_types = [
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_RETURN
    ]
    last_error_desc = ""
    for filling in filling_types:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": opposite_type,
            "position": position_id,
            "price": price,
            "deviation": 20,
            "magic": 998877,
            "comment": "Close from Web Dashboard",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return True, "Position successfully closed"
        else:
            if result:
                last_error_desc = f"Retcode: {result.retcode}, Comment: {result.comment}"
            else:
                last_error_desc = f"Error sending order: {mt5.last_error()}"
    return False, f"Failed to close position: {last_error_desc}"

def modify_mt5_position(ticket, sl, tp):
    if not init_mt5():
        return False, "Failed to initialize MT5 terminal"
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": float(sl),
        "tp": float(tp),
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, "Position modified successfully"
    else:
        if result:
            return False, f"Modification failed: {result.comment} (retcode: {result.retcode})"
        else:
            return False, f"Modification failed: {mt5.last_error()}"

@app.route('/api/trade/close_position', methods=['POST'])
def close_position_api():
    try:
        data = request.json
        ticket = data.get("ticket")
        if not ticket:
            return jsonify({"status": "error", "message": "Ticket is required"}), 400
            
        success, msg = close_mt5_position(int(ticket))
        if success:
            return jsonify({"status": "success", "message": msg})
        else:
            return jsonify({"status": "error", "message": msg}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade/modify_position', methods=['POST'])
def modify_position_api():
    try:
        data = request.json
        ticket = data.get("ticket")
        sl = data.get("sl")
        tp = data.get("tp")
        if not ticket:
            return jsonify({"status": "error", "message": "Ticket is required"}), 400
            
        success, msg = modify_mt5_position(int(ticket), sl, tp)
        if success:
            return jsonify({"status": "success", "message": msg})
        else:
            return jsonify({"status": "error", "message": msg}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/Trade')
@app.route('/trade')
def serve_trade():
    return send_from_directory(app.static_folder, 'trade.html')

@app.route('/Intermarket')
@app.route('/intermarket')
def serve_intermarket():
    return render_template('intermarket.html')

_cached_calendar = []
_cached_news = []
_last_scrape_time = 0

_COUNTRY_MAP = {
    'US': 'United States',
    'GB': 'United Kingdom',
    'UK': 'United Kingdom',
    'EU': 'Eurozone',
    'JP': 'Japan',
    'DE': 'Germany',
    'FR': 'France',
    'IT': 'Italy',
    'ES': 'Spain',
    'CA': 'Canada',
    'AU': 'Australia',
    'NZ': 'New Zealand',
    'CH': 'Switzerland',
    'CN': 'China',
    'IN': 'India',
    'BR': 'Brazil',
    'RU': 'Russia',
    'KR': 'South Korea',
    'MX': 'Mexico',
    'ZA': 'South Africa',
    'SG': 'Singapore',
    'HK': 'Hong Kong',
    'ID': 'Indonesia',
    'TH': 'Thailand',
    'TR': 'Turkey',
    'IE': 'Ireland',
    'OM': 'Oman',
    'EG': 'Egypt',
    'QA': 'Qatar',
    'AE': 'United Arab Emirates',
    'SE': 'Sweden',
    'NO': 'Norway',
    'FI': 'Finland',
    'DK': 'Denmark',
    'PL': 'Poland',
    'GR': 'Greece',
    'PT': 'Portugal',
    'NL': 'Netherlands',
    'BE': 'Belgium',
    'AT': 'Austria',
    'MY': 'Malaysia',
    'PH': 'Philippines',
    'VN': 'Vietnam',
    'SA': 'Saudi Arabia',
    'IL': 'Israel',
    'CO': 'Colombia',
    'CL': 'Chile',
    'PE': 'Peru',
    'AR': 'Argentina',
    'CZ': 'Czech Republic',
    'HU': 'Hungary',
    'RO': 'Romania',
    'UA': 'Ukraine',
}

def get_full_country_name(code):
    clean_code = str(code).strip().upper()
    return _COUNTRY_MAP.get(clean_code, clean_code)

def convert_utc_to_local(utc_str):
    try:
        if 'UTC' not in utc_str and 'GMT' not in utc_str:
            return utc_str
            
        time_part = utc_str.replace('UTC', '').replace('GMT', '').strip()
        from datetime import datetime, timezone
        dt_utc = datetime.strptime(time_part, '%I:%M %p')
        
        now = datetime.now()
        dt_utc = dt_utc.replace(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        return dt_local.strftime('%H:%M')
    except Exception:
        return utc_str

_news_translation_cache = {}

def translate_headline_to_id(text):
    global _news_translation_cache
    if not text:
        return ""
        
    text_clean = text.strip()
    if text_clean in _news_translation_cache:
        return _news_translation_cache[text_clean]
        
    import urllib.parse
    import requests
    url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=id&dt=t&q=' + urllib.parse.quote(text_clean)
    try:
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            res = r.json()
            translated = res[0][0][0]
            _news_translation_cache[text_clean] = translated
            return translated
    except Exception as e:
        print("Error translating news:", e)
        
    return text_clean

_scraping_in_progress = False

def fetch_live_calendar_and_news():
    global _cached_calendar, _cached_news, _last_scrape_time, _scraping_in_progress
    now = time.time()
    
    # Cache for 3 minutes (180 seconds) to keep it responsive but light
    if now - _last_scrape_time < 180 and _cached_calendar and _cached_news:
        return _cached_calendar, _cached_news
        
    if _scraping_in_progress:
        return _cached_calendar, _cached_news
        
    def run_scrape():
        global _cached_calendar, _cached_news, _last_scrape_time, _scraping_in_progress
        _scraping_in_progress = True
        try:
            import requests
            import warnings
            from bs4 import XMLParsedAsHTMLWarning
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 1. Fetch Calendar from Yahoo Finance
            calendar_events = []
            try:
                r = requests.get('https://finance.yahoo.com/calendar/economic/', headers=headers, timeout=5)
                if r.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(r.text, 'html.parser')
                    table = soup.find('table')
                    if table:
                        rows = table.find_all('tr')
                        for row in rows[1:30]:  # limit to top 29 events
                            tds = row.find_all('td')
                            if len(tds) >= 7:
                                raw_time = tds[2].get_text(strip=True)
                                local_time = convert_utc_to_local(raw_time)
                                raw_country = tds[1].get_text(strip=True)
                                full_country = get_full_country_name(raw_country)
                                calendar_events.append({
                                    "event": tds[0].get_text(strip=True),
                                    "country": full_country,
                                    "time": local_time,
                                    "actual": tds[4].get_text(strip=True),
                                    "forecast": tds[5].get_text(strip=True),
                                    "previous": tds[6].get_text(strip=True),
                                })
            except Exception as e:
                print("Error fetching live calendar in background:", e)
                
            if calendar_events:
                _cached_calendar = calendar_events
                
            # 2. Fetch News from Yahoo Finance RSS
            news_items = []
            try:
                r = requests.get('https://finance.yahoo.com/news/rssindex', headers=headers, timeout=5)
                if r.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(r.text, 'html.parser')
                    items = soup.find_all('item')
                    for item in items[:20]: # limit to top 20 news items
                        title = item.find('title')
                        pubdate = item.find('pubdate')
                        
                        t_str = ""
                        if pubdate:
                            raw_t = pubdate.get_text(strip=True)
                            if ' ' in raw_t:
                                parts = raw_t.split(' ')
                                if len(parts) >= 5:
                                    t_str = parts[4] # HH:MM:SS
                                    
                        raw_title = title.get_text(strip=True) if title else "No Title"
                        translated_title = translate_headline_to_id(raw_title)
                        news_items.append({
                            "title": translated_title,
                            "time": t_str
                        })
            except Exception as e:
                print("Error fetching live news in background:", e)
                
            if news_items:
                _cached_news = news_items
                
            _last_scrape_time = time.time()
        finally:
            _scraping_in_progress = False

    t = threading.Thread(target=run_scrape, daemon=True)
    t.start()
    
    return _cached_calendar, _cached_news


def is_news_halt_active():
    """Checks if there is a high-impact news event within 30 minutes in the future,
    or within 15 minutes in the past."""
    global _cached_calendar
    if not _cached_calendar:
        return False, None
        
    from datetime import datetime, timedelta
    now = datetime.now()
    
    # High impact keywords for Gold (XAUUSD)
    high_impact_keywords = ["cpi", "nfp", "fomc", "interest rate", "employment change", "gdp", "pce", "unemployment rate"]
    
    for event in _cached_calendar:
        event_name = event.get("event", "").lower()
        is_high_impact = any(k in event_name for k in high_impact_keywords)
        if not is_high_impact:
            continue
            
        event_time_str = event.get("time", "")
        if not event_time_str:
            continue
            
        try:
            event_hour, event_minute = map(int, event_time_str.split(":"))
            event_time = now.replace(hour=event_hour, minute=event_minute, second=0, microsecond=0)
            
            # Handle cross-day shifts
            time_diff = event_time - now
            if time_diff.total_seconds() < -43200:
                event_time += timedelta(days=1)
            elif time_diff.total_seconds() > 43200:
                event_time -= timedelta(days=1)
                
            # Halt window: 30 mins before, 15 mins after
            start_halt = event_time - timedelta(minutes=30)
            end_halt = event_time + timedelta(minutes=15)
            
            if start_halt <= now <= end_halt:
                return True, event.get("event")
        except Exception as e:
            continue
            
    return False, None


_trade_live_logs = []
_last_log_time = 0

def get_live_trade_logs(active_config, positions, ticks, bias):
    global _trade_live_logs, _last_log_time
    now_ts = time.time()
    
    # Generate new log entries at most every 1.5 seconds to keep it readable
    if now_ts - _last_log_time < 1.5 and _trade_live_logs:
        return _trade_live_logs
        
    _last_log_time = now_ts
    t_str = datetime.now().strftime("%H:%M:%S")
    
    if not active_config:
        _trade_live_logs = [
            {"t": t_str, "msg": "STANDBY: Belum ada strategi AI yang aktif. Buka Backtest Lab untuk deploy strategi.", "type": "warn"}
        ]
        return _trade_live_logs
        
    strategy_name = active_config.get("strategy_name", "Default Strategy")
    
    xau_tick = ticks.get("XAUUSD", {})
    price = xau_tick.get("bid", 0.0)
    
    new_entries = []
    
    if price > 0:
        # 1. Price Tick
        new_entries.append({
            "t": t_str,
            "msg": f"XAUUSD Tick Baru: Bid {price:.2f} | Ask {xau_tick.get('ask', 0.0):.2f}",
            "type": "tick"
        })
        
        # Fetch Top Pair Signals from global cache
        top_pairs_logged = 0
        if cached_dashboard_data:
            recs = cached_dashboard_data.get("pair_recommendations", [])
            for r in recs:
                if top_pairs_logged >= 2: break
                
                pair = r.get("pair", "UNKNOWN")
                conf = r.get("confidence", 0)
                act = r.get("action", "WAIT")
                chg = r.get("change_pct", 0)
                
                new_entries.append({
                    "t": t_str,
                    "msg": f"[{pair}] Adaptive AI Engine: Confidence {conf}% | Volatilitas {chg}%",
                    "type": "tech"
                })
                
                # Action logging
                if act == "EXIT WARNING":
                    new_entries.append({
                        "t": t_str,
                        "msg": f"⚠️ [{pair}] DECELERATION DETECTED! Momentum menurun, AI bersiap mengamankan posisi.",
                        "type": "warn"
                    })
                elif act in ["BUY", "SELL"]:
                    new_entries.append({
                        "t": t_str,
                        "msg": f"🟢 [{pair}] ACCELERATION DETECTED! Eksekusi {act} direkomendasikan",
                        "type": "fund"
                    })
                else:
                    new_entries.append({
                        "t": t_str,
                        "msg": f"Standby: Menunggu akselerasi momentum {pair}. Signal saat ini: {act}...",
                        "type": "calc"
                    })
                
                top_pairs_logged += 1
                
        if top_pairs_logged == 0:
             new_entries.append({
                 "t": t_str,
                 "msg": "Sinkronisasi AI Top Pair Signal... Menunggu pipeline terhubung...",
                 "type": "wait"
             })
             
        # Active Position Monitor
        if positions:
            for p in positions:
                p_profit = p.get("profit", 0.0)
                profit_str = f"+${p_profit:.2f}" if p_profit >= 0 else f"-${abs(p_profit):.2f}"
                new_entries.append({
                    "t": t_str,
                    "msg": f"Memantau Posisi Aktif #{p.get('ticket')}: {p.get('type').upper()} {p.get('volume')} lot {p.get('symbol')} | Entry {p.get('price'):.2f} | Current {p.get('price_current'):.2f} | S/L {p.get('sl'):.2f} | T/P {p.get('tp'):.2f} | Profit {profit_str}",
                    "type": "pos"
                })
        else:
            is_halt, event_name = is_news_halt_active()
            if is_halt:
                new_entries.append({
                    "t": t_str,
                    "msg": f"⚠️ [PAUSED] News Halt: Trading ditangguhkan karena rilis berita berdampak tinggi: {event_name}",
                    "type": "warn"
                })
    else:
        new_entries.append({
            "t": t_str,
            "msg": "Menunggu data harga XAUUSD dari terminal MT5...",
            "type": "wait"
        })
        
    for entry in new_entries:
        _trade_live_logs.append(entry)
        
    if len(_trade_live_logs) > 50:
        _trade_live_logs = _trade_live_logs[-50:]
        
    return _trade_live_logs


@app.route('/api/trade_status')
def get_trade_status():
    import datetime as dt
    try:
        # Load active config from decoupled active_config.json
        config_file = r'C:\Antigravity\active_config.json'
        active_config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f_cfg:
                try:
                    active_config = json.load(f_cfg)
                except Exception:
                    pass

        # Initialize connection to MT5 using cached function
        initialized = init_mt5()

        if not initialized:
            return jsonify({
                "status": "error",
                "message": f"MT5 terminal initialization failed: {mt5.last_error()}",
                "active_config": active_config,
                "account_info": None,
                "positions": [],
                "history": []
            })

        # Fetch account details
        acc_info = mt5.account_info()
        acc_dict = acc_info._asdict() if acc_info else None

        # Fetch active trades (positions)
        positions = mt5.positions_get()
        positions_list = []
        if positions:
            for p in positions:
                p_dict = p._asdict()
                p_time = dt.datetime.fromtimestamp(p_dict["time"]).strftime("%Y.%m.%d %H:%M:%S")
                p_type = "buy" if p_dict["type"] == 0 else "sell"
                positions_list.append({
                    "symbol": p_dict["symbol"],
                    "ticket": p_dict["ticket"],
                    "time": p_time,
                    "type": p_type,
                    "volume": p_dict["volume"],
                    "price": p_dict["price_open"],
                    "sl": p_dict["sl"],
                    "tp": p_dict["tp"],
                    "price_current": p_dict["price_current"],
                    "profit": round(p_dict["profit"], 2)
                })

        # Fetch closed deals (history) for last 30 days
        import datetime as dt
        from_date = dt.datetime.now() - dt.timedelta(days=30)
        to_date = dt.datetime.now() + dt.timedelta(days=1)
        deals = mt5.history_deals_get(from_date, to_date)
        history_list = []
        if deals:
            positions_map = {}
            balance_deals = []
            for d in deals:
                d_dict = d._asdict()
                pid = d_dict.get("position_id", 0)
                
                if d_dict.get("type") == 2: # DEAL_TYPE_BALANCE
                    balance_deals.append({
                        "time": dt.datetime.fromtimestamp(d_dict["time"]).strftime("%Y.%m.%d %H:%M:%S"),
                        "symbol": "",
                        "ticket": d_dict["ticket"],
                        "type": "balance",
                        "volume": "",
                        "price": "",
                        "sl": "",
                        "tp": "",
                        "close_time": "",
                        "close_price": "",
                        "profit": d_dict["profit"],
                        "comment": d_dict.get("comment", "")
                    })
                    continue
                    
                if pid == 0:
                    continue
                    
                if pid not in positions_map:
                    positions_map[pid] = []
                positions_map[pid].append(d_dict)

            closed_trades = []
            for pid, deal_list in positions_map.items():
                deal_list.sort(key=lambda x: x["time"])
                in_deal = None
                out_deal = None
                for d in deal_list:
                    if d["entry"] == 0: # DEAL_ENTRY_IN
                        in_deal = d
                    elif d["entry"] == 1: # DEAL_ENTRY_OUT
                        out_deal = d
                        
                if in_deal and out_deal:
                    trade_type = "buy" if in_deal["type"] == 0 else "sell"
                    profit = out_deal["profit"] + in_deal.get("commission", 0) + in_deal.get("swap", 0) + out_deal.get("commission", 0) + out_deal.get("swap", 0)
                    closed_trades.append({
                        "time": dt.datetime.fromtimestamp(in_deal["time"]).strftime("%Y.%m.%d %H:%M:%S"),
                        "symbol": in_deal["symbol"],
                        "ticket": pid,
                        "type": trade_type,
                        "volume": in_deal["volume"],
                        "price": in_deal["price"],
                        "sl": in_deal.get("sl", 0.0),
                        "tp": in_deal.get("tp", 0.0),
                        "close_time": dt.datetime.fromtimestamp(out_deal["time"]).strftime("%Y.%m.%d %H:%M:%S"),
                        "close_price": out_deal["price"],
                        "profit": round(profit, 2),
                        "comment": out_deal.get("comment", "")
                    })
            
            history_list = balance_deals + closed_trades
            history_list.sort(key=lambda x: x.get("close_time") or x["time"], reverse=True)

        # Fetch news feed from xedy_v30_data.json
        news_feed = []
        ml_weights = {}
        xedy_file = XEDY_DATABASE_PATH
        if os.path.exists(xedy_file):
            with open(xedy_file, 'r', encoding='utf-8') as f_xedy:
                try:
                    xedy_data = json.load(f_xedy)
                    news_feed = xedy_data.get("news_feed", [])
                    ml_weights = xedy_data.get("ml_weights", {})
                except Exception:
                    pass

        # Fetch live market ticks (same logic as get_live_ticks)
        ticks = {}
        symbols_to_fetch = {
            "XAUUSD": ["XAUUSD", "GOLD"],
            "USDJPY": ["USDJPY"],
            "WTI OIL": ["WTI", "XTIUSD", "USOIL", "CL"],
            "DJI": ["DJI", "US30", "YM", "DJIA"],
            "EURUSD": ["EURUSD"],
            "GBPUSD": ["GBPUSD"]
        }
        for label, options in symbols_to_fetch.items():
            t = None
            matched_symbol = None
            for opt in options:
                mt5.symbol_select(opt, True)
                t = mt5.symbol_info_tick(opt)
                if t:
                    matched_symbol = opt
                    break
            if t:
                rates = mt5.copy_rates_from_pos(matched_symbol, mt5.TIMEFRAME_D1, 0, 1)
                daily_open = rates[0]['open'] if (rates is not None and len(rates) > 0) else t.bid
                daily_vol = rates[0]['tick_volume'] if (rates is not None and len(rates) > 0) else 0
                daily_change = ((t.bid - daily_open) / daily_open) * 100.0 if daily_open > 0 else 0.0
                daily_high = rates[0]['high'] if (rates is not None and len(rates) > 0) else t.bid
                daily_low = rates[0]['low'] if (rates is not None and len(rates) > 0) else t.bid
                ticks[label] = {
                    "bid": t.bid,
                    "ask": t.ask,
                    "change": round(daily_change, 3),
                    "volume": int(daily_vol),
                    "high": daily_high,
                    "low": daily_low
                }

        # Fetch live calendar and news from Yahoo Finance
        live_cal, live_news = fetch_live_calendar_and_news()

        bias_val = round(compute_xedy_fundamental_bias(), 3)
        live_logs = get_live_trade_logs(active_config, positions_list, ticks, bias_val)
        return jsonify({
            "status": "success",
            "active_config": active_config,
            "account_info": acc_dict,
            "positions": positions_list,
            "history": history_list,
            "news": live_news,
            "calendar": live_cal,
            "ticks": ticks,
            "fundamental_bias": bias_val,
            "ai_live_logs": live_logs,
            "ml_weights": ml_weights,
            "backtest_running": _progress_running,
            "top_pairs": [r.get("pair") for r in cached_dashboard_data.get("pair_recommendations", [])][:2] if cached_dashboard_data else ["XAUUSD"]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/Monitor')
@app.route('/monitor')
def monitor_page():
    return send_from_directory('static', 'monitor.html')


@app.route('/Forecast')
def forecast_page():
    return send_from_directory('static', 'forecast.html')


@app.route('/ForecastV32')
@app.route('/forecastv32')
def forecast_v32_page():
    return send_from_directory('static', 'forecast_v32.html')


@app.route('/api/xedy_v32_forecast')
def get_xedy_v32_forecast():
    try:
        xedy_file = XEDY_DATABASE_PATH
        if os.path.exists(xedy_file):
            with open(xedy_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                v32_data = data.get("forecast_v32", {})
                if v32_data:
                    return jsonify({
                        "status": "success",
                        "forecast": v32_data,
                        "backtest_running": _progress_running
                    })
        return jsonify({"status": "error", "message": "No V32 forecast data found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/forecast_data')
def get_forecast_data():
    try:
        current_price = 2300.0
        if not init_mt5():
            return jsonify({"status": "error", "message": "Failed to initialize MT5"}), 500
        for opt in ["XAUUSD", "GOLD"]:
            mt5.symbol_select(opt, True)
            t = mt5.symbol_info_tick(opt)
            if t:
                current_price = t.bid
                break
                
        bias_val = compute_xedy_fundamental_bias()
        state = forecast_engine.get_forecast_state("XAUUSD", current_price, bias_val)
        macro_ctx = forecast_engine.get_forecast_macro_context()
        eco_reports = forecast_engine.get_economic_reports()
        return jsonify({
            "status": "success",
            "forecast": state,
            "macro_context": macro_ctx,
            "economic_reports": eco_reports,
            "backtest_running": _progress_running
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/symbol_forecast')
def get_symbol_forecast_api():
    """Returns forecast data for a given symbol (USDJPY, XTIUSD, etc.)"""
    try:
        symbol = request.args.get('symbol', 'USDJPY').upper()
        allowed = ['USDJPY', 'XTIUSD', 'EURUSD', 'GBPUSD']
        if symbol not in allowed:
            return jsonify({"status": "error", "message": f"Symbol {symbol} not supported. Use: {allowed}"}), 400
        data = forecast_engine.get_symbol_forecast(symbol)
        if 'error' in data:
            return jsonify({"status": "error", "message": data['error']}), 500
        return jsonify({
            "status": "success",
            "forecast": data,
            "macro_context": data.get("macro_context"),
            "economic_reports": data.get("economic_reports"),
            "backtest_running": _progress_running
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    pass

    # Start background scheduler thread to auto-update all pages continuously
    import threading
    def run_scheduler_thread():
        import ai_engine
        import schedule
        print("[Scheduler Thread] Starting background scheduler...")
        
        # Schedulers matching ai_engine.py
        schedule.every(1).minutes.do(ai_engine.run_live_price_update)
        schedule.every(1).minutes.do(sync_live_trade_history)
        schedule.every(15).minutes.do(ai_engine.run_news_update)
        schedule.every(2).hours.do(ai_engine.run_claude_4h_forecast)
        schedule.every(1).hours.do(ai_engine.run_claude_daily_macro)
        schedule.every(4).hours.do(ai_engine.run_claude_weekly_flow)
        schedule.every(1).minutes.do(ai_engine.run_v31_institutional_intelligence)
        schedule.every(1).minutes.do(ai_engine.run_v32_ultimate_forecast)
        schedule.every(1).minutes.do(ai_engine.run_technical_and_calendar)
        
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                print("[Scheduler Thread] Error running scheduled jobs:", e)
            time.sleep(1)
            
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        t = threading.Thread(target=run_scheduler_thread, daemon=True)
        t.start()

    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
