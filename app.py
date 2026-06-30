stop_backtest_requested = False
from flask import Flask, jsonify, send_from_directory
import MetaTrader5 as mt5
from flask_cors import CORS
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from flask import request

app = Flask(__name__, static_folder='static')
CORS(app)

# The specific pairs requested
SYMBOLS = [
    "XAUUSD", "USDJPY", "EURUSD", "GBPUSD", 
    "XTIUSD", "US30", "BOND JAPAN", "BOND US"
]

def init_mt5():
    # Initialize connection to the MetaTrader 5 terminal
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        return False
    return True

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/live_ticks')
def get_live_ticks():
    if not init_mt5():
        return jsonify({"error": "Failed to connect to MT5"}), 500
    
    ticks = {}
    for symbol in ["XAUUSD", "USDJPY"]:
        t = mt5.symbol_info_tick(symbol)
        if t: ticks[symbol] = t.bid
        
    for symbol in ["WTI", "XTIUSD", "USOIL"]:
        t = mt5.symbol_info_tick(symbol)
        if t:
            ticks["WTI OIL"] = t.bid
            break
            
    return jsonify(ticks)

@app.route('/api/prices')
def get_prices():
    if not init_mt5():
        return jsonify({"error": "Failed to connect to MT5", "code": mt5.last_error()}), 500

    prices = []
    
    for symbol in SYMBOLS:
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
        with open('xedy_v30_data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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


# --- BACKTEST CORE LOGIC ---

def ensure_mt5():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 Python package is not available.")
    if not mt5.initialize():
        raise RuntimeError(f"MetaTrader5 initialize failed: {mt5.last_error()}")

def load_dashboard_data():
    with open('xedy_v30_data.json', 'r', encoding='utf-8') as f:
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


def make_strategy_library(rr_values=None):
    rr_values = dedupe_rr_values(rr_values or [1.0, 1.4, 1.8, 2.2, 2.6])
    library = []

    # AI XEDY_V30 Core
    for threshold, confirmation, stop_atr, max_hold_bars, rr in product(
        [0.18, 0.28],
        [0.08],
        [1.2, 1.8],
        [30, 90],
        rr_values,
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
                },
            }
        )

    # AI XEDY_V30 Pullback
    for pullback_limit, confirmation, stop_atr, max_hold_bars, rr in product(
        [0.08],
        [0.08],
        [1.2],
        [45],
        rr_values,
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
                },
            }
        )

    # AI XEDY_V30 Mean Revert
    for extreme_rsi, threshold, stop_atr, max_hold_bars, rr in product(
        [30],
        [0.18],
        [1.2],
        [45],
        rr_values,
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
                },
            }
        )

    # AI XEDY_V30 Breakout
    for breakout_buffer, threshold, stop_atr, max_hold_bars, rr in product(
        [0.15],
        [0.18],
        [1.2],
        [45],
        rr_values,
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
                },
            }
        )

    # AI XEDY_V30 MACD Momentum
    for threshold, stop_atr, max_hold_bars, rr in product(
        [0.05, 0.15],
        [1.2],
        [45],
        rr_values,
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


def build_indicator_cache(rates, strategies):
    closes = [row["close"] for row in rates]
    highs = [row["high"] for row in rates]
    lows = [row["low"] for row in rates]
    cache = {
        "close": closes,
        "high": highs,
        "low": lows,
        "atr_14": atr(rates, 14),
        "xedy_fundamental_bias": compute_xedy_fundamental_bias(),
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

    elif strategy["type"] == "xedy_mean_revert":
        combined_score, trend_score = compute_combined_score(cache, index)
        rsi_value = cache["rsi_14"][index]
        if not (None in (combined_score, trend_score, rsi_value)):
            stop_distance = atr_value * params["stop_atr"]
            if combined_score > params["threshold"] and rsi_value <= params["extreme_rsi"]:
                signal = {"side": 1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}
            elif combined_score < -params["threshold"] and rsi_value >= 100 - params["extreme_rsi"]:
                signal = {"side": -1, "stop_distance": stop_distance, "take_distance": stop_distance * params["rr"], "signal_strength": combined_score}

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

    if signal:
        # Check if signal side is counter-trend to fundamental bias
        is_against = (signal["side"] == 1 and bias < 0.0) or (signal["side"] == -1 and bias > 0.0)
        signal["against_fundamental"] = is_against
        return signal
    return None


def exit_signal(strategy, cache, index, position):
    params = strategy["params"]
    if strategy["type"] in {"xedy_v30_ai", "xedy_trend_pullback", "xedy_mean_revert", "xedy_breakout_confirm"}:
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
    warmup = 60
    equity = float(initial_capital)
    peak_equity = equity
    max_drawdown = 0.0
    trades = []
    position = None

    for index in range(warmup, len(rates)):
        bar = rates[index]

        if position is not None:
            update_position_excursions(position, bar)
            
            # --- AVERAGING / GRID LOGIC ---
            atr_val = cache["atr_14"][index]
            if atr_val is not None and atr_val > 0 and len(position["entries"]) < 3:
                grid_spacing = atr_val * 1.5
                last_entry_price = position["entries"][-1]
                
                should_average = False
                if position["side"] == 1 and bar["close"] <= last_entry_price - grid_spacing:
                    should_average = True
                elif position["side"] == -1 and bar["close"] >= last_entry_price + grid_spacing:
                    should_average = True
                    
                if should_average:
                    entry_price = bar["close"]
                    position["entries"].append(entry_price)
                    position["lots"].append(position["initial_lot"])
                    
                    total_lot = sum(position["lots"])
                    avg_entry = sum(e * l for e, l in zip(position["entries"], position["lots"])) / total_lot
                    position["entry"] = avg_entry
                    position["lot"] = total_lot
                    
                    if position["side"] == 1:
                        position["stop"] = avg_entry - position["stop_distance"]
                        position["take"] = avg_entry + position["take_distance"]
                    else:
                        position["stop"] = avg_entry + position["stop_distance"]
                        position["take"] = avg_entry - position["take_distance"]

            exit_price = None
            exit_reason = None

            if position["side"] == 1:
                if bar["low"] <= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif bar["high"] >= position["take"]:
                    exit_price = position["take"]
                    exit_reason = "take"
                elif exit_signal(strategy, cache, index, position):
                    exit_price = bar["close"]
                    exit_reason = "signal"
            else:
                if bar["high"] >= position["stop"]:
                    exit_price = position["stop"]
                    exit_reason = "stop"
                elif bar["low"] <= position["take"]:
                    exit_price = position["take"]
                    exit_reason = "take"
                elif exit_signal(strategy, cache, index, position):
                    exit_price = bar["close"]
                    exit_reason = "signal"

            if exit_price is not None:
                trade, equity = close_position(position, exit_price, bar["time"], exit_reason, equity, risk_pct)
                if trade:
                    trades.append(trade)
                    peak_equity = max(peak_equity, equity)
                    if peak_equity > 0:
                        max_drawdown = max(max_drawdown, ((peak_equity - equity) / peak_equity) * 100.0)
                position = None

        if position is None:
            signal = entry_signal(strategy, cache, index)
            if signal:
                entry = bar["close"]
                stop_distance = signal["stop_distance"]
                take_distance = signal["take_distance"]
                side = signal["side"]
                lot = estimate_lot_size(stop_distance, equity, risk_pct, risk_context or {})
                if signal.get("against_fundamental", False):
                    # Reduce lot size by 50% for trades going against fundamental trend
                    step = (risk_context or {}).get("volume_step", 0.01) or 0.01
                    lot = round((lot * 0.5) / step) * step
                    volume_min = (risk_context or {}).get("volume_min", step) or step
                    lot = max(lot, volume_min)
                    
                position = {
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

    if position is not None:
        trade, equity = close_position(position, rates[-1]["close"], rates[-1]["time"], "end_of_test", equity, risk_pct)
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

    total_buy = sum(1 for t in trades if t["side"] == "LONG")
    total_sell = sum(1 for t in trades if t["side"] == "SHORT")

    return {
        "strategy_name": strategy["name"],
        "strategy_type": strategy["type"],
        "parameters": strategy["params"],
        "total_trades": len(trades),
        "total_buy": total_buy,
        "total_sell": total_sell,
        "win_rate": round(win_rate, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "avg_monthly_profit_pct": round(avg_monthly_profit_pct, 2),
        "net_profit_pct": round(net_profit_pct, 2),
        "ending_balance": round(equity, 2),
        "initial_capital": round(initial_capital, 2),
        "avg_mae_r": round(avg_mae_r, 3),
        "avg_mfe_r": round(avg_mfe_r, 3),
        "score": round(score, 2),
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
    # Enforce drawdown < 10%
    if result.get("max_drawdown_pct", 100.0) >= 10.0:
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
):
    rates = fetch_mt5_rates(symbol=symbol, days=days, start_month=start_month, end_month=end_month, timeframe=timeframe)
    risk_context = get_symbol_risk_context(symbol)

    filters = filters or {
        "drawdown": {"operator": ">", "value": 5},
        "win_rate": {"operator": "<", "value": 80},
        "monthly_profit": {"operator": "<", "value": 40},
    }

    all_results = []
    learning_iterations = []
    rr_values = dedupe_rr_values([1.0, 1.4, 1.8, 2.2, 2.6])
    iteration_sources = [("grid", make_strategy_library(rr_values))]

    global stop_backtest_requested
    for iteration_index in range(5):
        phase_name, strategies = iteration_sources[-1]
        cache = build_indicator_cache(rates, strategies)
        current_results = []
        for strategy in strategies:
            if stop_backtest_requested:
                stop_backtest_requested = False
                raise RuntimeError("Backtest dihentikan oleh user.")
            result = run_backtest(
                rates,
                strategy,
                cache,
                risk_pct=risk_pct,
                initial_capital=initial_capital,
                risk_context=risk_context,
            )
            if result["total_trades"] < 8:
                continue
            result["passes_filters"] = evaluate_result_against_filters(result, filters)
            current_results.append(result)
        rank_results(current_results, sort_priority=sort_priority)
        all_results.extend(current_results)
        passes = sum(1 for item in current_results if item["passes_filters"])
        positive_passing = sum(1 for item in current_results if item["passes_filters"] and item["net_profit_pct"] > 0.0)
        learning_iterations.append(
            {
                "phase": phase_name,
                "tested": len(strategies),
                "returned": len(current_results),
                "passes": passes,
            }
        )
        if positive_passing > 0 and iteration_index >= 1:
            break
        seed_results = current_results[:6]
        rr_values = generate_refined_rr_values(seed_results)
        next_phase = "self_learning" if iteration_index == 0 else f"self_learning_{iteration_index}"
        next_strategies = build_self_learning_strategies(seed_results) + make_strategy_library(rr_values)
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

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": len(rates),
        "days": days,
        "range": {
            "start_month": start_month,
            "end_month": end_month,
        },
        "method": "AI XEDY_V30",
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
    global stop_backtest_requested
    stop_backtest_requested = False
    payload = request.get_json(silent=True) or {}
    filters = payload.get("filters") or {}

    tfs = ["M5", "M15", "M30", "H1", "H4"]
    results_per_tf = {}

    try:
        for tf in tfs:
            if stop_backtest_requested:
                break
                
            tf_result = search_backtest_methods(
                symbol=payload.get("symbol", "XAUUSD"),
                days=int(payload.get("days", 30)),
                risk_pct=float(payload.get("risk_pct", 1.0)),
                initial_capital=float(payload.get("initial_capital", 10000)),
                start_month=payload.get("start_month"),
                end_month=payload.get("end_month"),
                sort_priority=payload.get("sort_priority", ["net_profit", "win_rate", "drawdown"]),
                timeframe=tf,
                filters={
                    "drawdown": {
                        "operator": filters.get("drawdown", {}).get("operator", ">"),
                        "value": float(filters.get("drawdown", {}).get("value", 5)),
                    },
                    "win_rate": {
                        "operator": filters.get("win_rate", {}).get("operator", "<"),
                        "value": float(filters.get("win_rate", {}).get("value", 80)),
                    },
                    "monthly_profit": {
                        "operator": filters.get("monthly_profit", {}).get("operator", "<"),
                        "value": float(filters.get("monthly_profit", {}).get("value", 40)),
                    },
                },
            )
            results_per_tf[tf] = tf_result

        if stop_backtest_requested:
            stop_backtest_requested = False
            return jsonify({"success": False, "error": "Backtest dihentikan oleh user."}), 400

        return jsonify({
            "success": True, 
            "data": {
                "symbol": payload.get("symbol", "XAUUSD"),
                "results_per_tf": results_per_tf
            }
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

@app.route("/api/backtest/stop", methods=["POST"])
def api_backtest_stop():
    global stop_backtest_requested
    stop_backtest_requested = True
    return jsonify({"success": True, "message": "Stop requested."})

if __name__ == '__main__':
    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
