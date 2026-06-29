import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

if not mt5.initialize():
    print('initialize() failed')
    mt5.shutdown()
    exit()

symbol = 'XAUUSD'
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 5)

if rates is None or len(rates) == 0:
    print('Failed to get rates')
else:
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['range'] = df['high'] - df['low']
    
    print('Daily Analysis (Last 5 Days) for', symbol)
    for index, row in df.iterrows():
        print(f"Date: {row['time'].date()}, High: {row['high']:.2f}, Low: {row['low']:.2f}, Range: {row['range']:.2f}")
        
    avg_range = df['range'].mean()
    print(f"\nAverage Range (5 Days): {avg_range:.2f}")

mt5.shutdown()
