import MetaTrader5 as mt5

mt5.initialize()
symbol = 'XAUUSD'

rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 30)
closes = [r['close'] for r in rates]
print('Closes:', closes[-5:])
