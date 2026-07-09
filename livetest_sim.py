import json
import os
import time
from datetime import datetime

DEMO_PATH = r'C:\Antigravity\livetest_demo.json'

def init_demo_file():
    needs_init = False
    if not os.path.exists(DEMO_PATH):
        needs_init = True
    else:
        try:
            with open(DEMO_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict) or "balance" not in data or "equity" not in data or "active_trades" not in data:
                    needs_init = True
        except Exception:
            needs_init = True
            
    if needs_init:
        initial_data = {
            "balance": 10543.10,
            "equity": 10543.10,
            "active_trades": [],
            "history": [
                {
                    "ticket": 2873426,
                    "open_time": "2026-06-29 10:15:30",
                    "close_time": "2026-06-29 14:22:45",
                    "symbol": "XAUUSD",
                    "type": "SELL",
                    "lots": 0.52,
                    "entry": 2335.20,
                    "exit": 2328.10,
                    "commission": -1.50,
                    "swap": 0.00,
                    "gross_profit": 369.20,
                    "net_profit": 367.70,
                    "exit_reason": "TP HIT",
                    "result": "PROFIT"
                },
                {
                    "ticket": 2873912,
                    "open_time": "2026-06-29 16:45:00",
                    "close_time": "2026-06-29 18:10:12",
                    "symbol": "XAUUSD",
                    "type": "SELL",
                    "lots": 0.52,
                    "entry": 2330.50,
                    "exit": 2334.80,
                    "commission": -1.50,
                    "swap": 0.00,
                    "gross_profit": -223.60,
                    "net_profit": -225.10,
                    "exit_reason": "SL HIT",
                    "result": "LOSS"
                },
                {
                    "ticket": 2874108,
                    "open_time": "2026-06-30 08:30:00",
                    "close_time": "2026-06-30 11:15:20",
                    "symbol": "XAUUSD",
                    "type": "SELL",
                    "lots": 0.53,
                    "entry": 2328.90,
                    "exit": 2321.40,
                    "commission": -1.50,
                    "swap": 0.00,
                    "gross_profit": 397.50,
                    "net_profit": 396.00,
                    "exit_reason": "TP HIT",
                    "result": "PROFIT"
                }
            ],
            "last_update": time.time()
        }
        os.makedirs(os.path.dirname(DEMO_PATH), exist_ok=True)
        with open(DEMO_PATH, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=4)

def get_demo_state():
    init_demo_file()
    try:
        with open(DEMO_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print("Error reading demo state:", e)
        return None

def save_demo_state(state):
    try:
        with open(DEMO_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print("Error saving demo state:", e)

def update_livetest_sim(current_gold_price, bias, news_halt_active=False, confidence=70.0):
    state = get_demo_state()
    if not state:
        return None

    # Connect to DB to load dynamic self-learning parameters for TP and SL scaling
    import sqlite3
    db_path = r"C:\Antigravity\forecast_history.db"
    win_rate = 92.5
    avg_mae_pct = 0.0
    avg_mfe_pct = 0.0
    try:
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT correct FROM predictions WHERE evaluated = 1 ORDER BY timestamp DESC LIMIT 50")
            rows = c.fetchall()
            if rows:
                win_rate = (sum(r[0] for r in rows) / len(rows)) * 100.0
            
            c.execute("""
                SELECT entry_price, max_favorable_price, max_adverse_price 
                FROM predictions 
                WHERE evaluated = 1 AND max_favorable_price IS NOT NULL AND max_adverse_price IS NOT NULL
                ORDER BY timestamp DESC LIMIT 20
            """)
            excursions = c.fetchall()
            conn.close()
            if excursions:
                mae_sums = [abs(mae - entry)/entry for entry, mfe, mae in excursions if entry > 0]
                mfe_sums = [abs(mfe - entry)/entry for entry, mfe, mae in excursions if entry > 0]
                if mae_sums:
                    avg_mae_pct = sum(mae_sums) / len(mae_sums)
                    avg_mfe_pct = sum(mfe_sums) / len(mfe_sums)
    except Exception as db_err:
        print("[Demo Adaptive Engine Error]", db_err)

    # 1. Update Active Trade
    active_list = state.get("active_trades", [])
    if active_list:
        trade = active_list[0]
        trade["current_price"] = current_gold_price
        
        # Calculate profit in USD (Gold contract size = 100)
        if trade["type"] == "SELL":
            profit = (trade["entry_price"] - current_gold_price) * trade["lots"] * 100.0
        else:
            profit = (current_gold_price - trade["entry_price"]) * trade["lots"] * 100.0
            
        trade["profit"] = round(profit, 2)
        state["equity"] = round(state["balance"] + profit, 2)
        
        # Check SL / TP hits
        is_closed = False
        exit_price = current_gold_price
        result_text = "PROFIT"
        
        if trade["type"] == "SELL":
            if current_gold_price >= trade["sl"]:
                is_closed = True
                exit_price = trade["sl"]
                result_text = "LOSS"
            elif current_gold_price <= trade["tp"]:
                is_closed = True
                exit_price = trade["tp"]
                result_text = "PROFIT"
        else:
            if current_gold_price <= trade["sl"]:
                is_closed = True
                exit_price = trade["sl"]
                result_text = "LOSS"
            elif current_gold_price >= trade["tp"]:
                is_closed = True
                exit_price = trade["tp"]
                result_text = "PROFIT"
                
        if is_closed:
            # Re-calculate final profit on target exit price
            if trade["type"] == "SELL":
                final_profit = (trade["entry_price"] - exit_price) * trade["lots"] * 100.0
            else:
                final_profit = (exit_price - trade["entry_price"]) * trade["lots"] * 100.0
                
            final_profit = round(final_profit, 2)
            commission = trade.get("commission", -1.50)
            swap = trade.get("swap", 0.00)
            net_profit = round(final_profit + commission + swap, 2)
            
            state["balance"] = round(state["balance"] + net_profit, 2)
            state["equity"] = state["balance"]
            
            # Move to history
            state["history"].insert(0, {
                "ticket": trade["ticket"],
                "open_time": trade["time"],
                "close_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": trade["symbol"],
                "type": trade["type"],
                "lots": trade["lots"],
                "entry": trade["entry_price"],
                "exit": round(exit_price, 2),
                "commission": commission,
                "swap": swap,
                "gross_profit": final_profit,
                "net_profit": net_profit,
                "exit_reason": "TP HIT" if result_text == "PROFIT" else "SL HIT",
                "result": result_text
            })
            # Clear active trades
            state["active_trades"] = []
            
    # 2. If no active trade, open a new one
    else:
        if news_halt_active:
            state["last_update"] = time.time()
            save_demo_state(state)
            return state
            
        # Load active config from decoupled active_config.json
        config_file = r'C:\Antigravity\active_config.json'
        config = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f_cfg:
                    config = json.load(f_cfg)
            except Exception:
                pass
        
        # If no config is deployed, do NOT open any simulated trades
        if not config:
            state["last_update"] = time.time()
            save_demo_state(state)
            return state
            
        risk_percent = config.get("risk_percent", 1.0)
        
        # Base distances
        sl_dist = config.get("sl_dist", 15.0)
        tp_dist = config.get("tp_dist", 22.0)
        
        # Self-learning adjustments on SL/TP bounds based on historical MAE / MFE
        gap_multiplier = 1.0
        sl_multiplier = 1.0
        if avg_mae_pct > 0:
            if avg_mae_pct < 0.0015:
                sl_multiplier = 0.80
            elif avg_mae_pct > 0.0050:
                sl_multiplier = 1.25
        if avg_mfe_pct > 0 and win_rate < 90.0:
            deviation = 90.0 - win_rate
            gap_multiplier = max(0.50, min(1.0, (avg_mfe_pct * 1000) * (1.0 - deviation * 0.02)))
        elif win_rate < 90.0:
            deviation = 90.0 - win_rate
            gap_multiplier = max(0.50, 1.0 - (deviation * 0.035))
            sl_multiplier = min(1.30, 1.0 + (deviation * 0.015))
            
        sl_dist = sl_dist * sl_multiplier
        tp_dist = tp_dist * gap_multiplier
        
        # Open Sell since fundamental bias is Bearish, Buy if Bullish
        trade_type = "SELL" if bias < 0 else "BUY"
        
        # Smart Dynamic Lot sizing scaled directly with confidence %
        conf_factor = float(confidence) / 70.0
        conf_factor = max(0.5, min(1.5, conf_factor))
        effective_risk_pct = risk_percent * conf_factor
        
        # Calculate dynamic lot size based on risk and balance: Lot Size = (Balance * Risk%) / (SL * 100)
        balance = state.get("balance", 10000.0)
        risk_amount = balance * (effective_risk_pct / 100.0)
        lots = round(risk_amount / (sl_dist * 100.0), 2)
        if lots < 0.01:
            lots = 0.01
            
        entry_price = current_gold_price
        sl_price = entry_price + sl_dist if trade_type == "SELL" else entry_price - sl_dist
        tp_price = entry_price - tp_dist if trade_type == "SELL" else entry_price + tp_dist
        
        new_trade = {
            "ticket": 20000000 + (int(time.time() * 100) % 10000000),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": "XAUUSD",
            "type": trade_type,
            "lots": lots,
            "entry_price": round(entry_price, 2),
            "current_price": round(entry_price, 2),
            "sl": round(sl_price, 2),
            "tp": round(tp_price, 2),
            "commission": -1.50,
            "swap": 0.00,
            "status": "RUNNING",
            "profit": 0.0
        }
        state["active_trades"].append(new_trade)
        state["equity"] = state["balance"]

    state["last_update"] = time.time()
    save_demo_state(state)
    return state
