import sqlite3

def check_db():
    conn = sqlite3.connect('forecast_history.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    for table_name in tables:
        table_name = table_name[0]
        cursor.execute(f"PRAGMA table_info({table_name});")
        print(f"Table {table_name} Columns:", cursor.fetchall())
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        print(f"Row count in {table_name}:", cursor.fetchone()[0])
        # Select first row
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 1;")
        print(f"Sample row from {table_name}:", cursor.fetchone())
        print("-" * 50)
    conn.close()

if __name__ == '__main__':
    check_db()
