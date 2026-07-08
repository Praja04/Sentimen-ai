import sqlite3

def check_stale_prices():
    conn = sqlite3.connect('forecast_history.db')
    c = conn.cursor()
    c.execute("SELECT * FROM predictions ORDER BY timestamp DESC LIMIT 30")
    rows = c.fetchall()
    print("Predictions in SQLite:")
    for r in rows:
        print(f"ID={r[0]}, DT={r[2]}, SYM={r[3]}, DIR={r[4]}, ENTRY={r[6]}, EVAL={r[8]}, CORRECT={r[9]}")
    conn.close()

if __name__ == '__main__':
    check_stale_prices()
