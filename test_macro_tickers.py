import yfinance as yf

tickers = "DX-Y.NYB ^TNX ^VIX ^DJI ^IRX TIP BIL DBC ADP ^DJT HYG IEF GLD ^SKEW USO"
data = yf.Tickers(tickers)

print("Fetching data...")
for t in tickers.split():
    try:
        hist = data.tickers[t].history(period="1mo")['Close'].tolist()
        print(f"{t}: {len(hist)} closes, last = {hist[-1] if len(hist) > 0 else 'N/A'}")
    except Exception as e:
        print(f"{t} failed: {e}")
