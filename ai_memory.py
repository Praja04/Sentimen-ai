import sqlite3
import time
import os
from datetime import datetime

# Build DB path dynamically relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "forecast_history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            datetime_str TEXT,
            symbol TEXT,
            direction TEXT,
            predicted_bp REAL,
            entry_price REAL,
            best_pillar TEXT,
            evaluated INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0
        )
    ''')
    # Speed optimization: Create indexes for fast lookups during live evaluation and ranking
    c.execute('CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions (symbol)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_predictions_evaluated ON predictions (evaluated)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_predictions_timestamp ON predictions (timestamp)')
    conn.commit()
    conn.close()

def log_prediction(symbol, direction, predicted_bp, entry_price, best_pillar):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = time.time()
    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # We only want to log if there isn't a very recent prediction (e.g. within the last 30 minutes) to avoid spamming the DB every 1 minute
    c.execute("SELECT timestamp FROM predictions WHERE symbol=? ORDER BY timestamp DESC LIMIT 1", (symbol,))
    last_record = c.fetchone()
    if last_record:
        if (now - last_record[0]) < 1800: # 30 minutes
            conn.close()
            return

    c.execute('''
        INSERT INTO predictions (timestamp, datetime_str, symbol, direction, predicted_bp, entry_price, best_pillar)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (now, dt_str, symbol, direction, predicted_bp, entry_price, best_pillar))
    
    conn.commit()
    conn.close()

def evaluate_predictions(current_prices_dict):
    """
    Evaluates predictions older than 4 hours (14400 seconds).
    Returns a dict of penalties (if a pillar was wrong).
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = time.time()
    
    # Select predictions older than 4 hours that haven't been evaluated
    # Actually, for testing purposes, we can evaluate things older than 1 hour (3600), but let's stick to 4 hours (14400)
    c.execute("SELECT id, symbol, direction, entry_price, best_pillar FROM predictions WHERE evaluated=0 AND (? - timestamp) > 14400", (now,))
    pending = c.fetchall()
    
    penalties = []
    
    for row in pending:
        pid, symbol, direction, entry_price, best_pillar = row
        if symbol in current_prices_dict:
            current_price = current_prices_dict[symbol]['price']
            
            # Did it go the right way?
            is_correct = 0
            if "BULL" in direction and current_price > entry_price:
                is_correct = 1
            elif "BEAR" in direction and current_price < entry_price:
                is_correct = 1
                
            c.execute("UPDATE predictions SET evaluated=1, correct=? WHERE id=?", (is_correct, pid))
            
            # If wrong, we want to penalize the pillar that was most responsible
            if not is_correct:
                penalties.append(best_pillar)
                
    conn.commit()
    conn.close()
    
    # Calculate penalty adjustments
    penalty_adjustments = {}
    for p in penalties:
        penalty_adjustments[p] = penalty_adjustments.get(p, 0) + 0.05 # 5% penalty per failure
        
    return penalty_adjustments
