import MetaTrader5 as mt5

mt5.initialize()
symbol = 'XAUUSD'

def calc_atr(rate_list):
    if rate_list is None or len(rate_list) == 0: return 0
    return sum([(r['high'] - r['low']) for r in rate_list]) / len(rate_list)

rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 14)
w_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 14)
m_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_MN1, 0, 14)

print('D1 ATR:', calc_atr(rates))
print('W1 ATR:', calc_atr(w_rates))
print('MN1 ATR:', calc_atr(m_rates))
