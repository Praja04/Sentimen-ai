import MetaTrader5 as mt5
from ai_engine import generate_forecast

mt5.initialize()
macro_score = 50
sentiment_score = 50
flow_score = 50
regime_score = 50
tech_s = 50
cal_score = 50
ml_weights = {'macro': 0.1, 'sentiment': 0.1, 'flow': 0.5, 'regime': 0.1, 'tech': 0.1, 'cal': 0.1}

f4 = generate_forecast('XAUUSD', '1D', macro_score, sentiment_score, flow_score, regime_score, tech_s, cal_score, ml_weights)
print('F4:', f4)
