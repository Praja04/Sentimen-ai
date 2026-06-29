from flask import Flask, jsonify, send_from_directory
import MetaTrader5 as mt5
from flask_cors import CORS
import os

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

if __name__ == '__main__':
    # Start the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
