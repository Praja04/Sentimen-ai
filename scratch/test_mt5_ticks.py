import MetaTrader5 as mt5

def test_prices_extended():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return
        
    alternatives = {
        "XAUUSD": ["XAUUSD", "GOLD"],
        "USDJPY": ["USDJPY"],
        "WTI OIL": ["WTI", "XTIUSD", "USOIL", "CL"],
        "NIKKEI": ["JP225", "JPN225", "NI225", "JP225Cash", "JAPAN225"],
        "DOW JONES": ["US30", "DJ30", "DJIA", "WS30", "USA30"]
    }
    
    for label, options in alternatives.items():
        print(f"--- {label} ---")
        for opt in options:
            select = mt5.symbol_select(opt, True)
            tick = mt5.symbol_info_tick(opt)
            if tick:
                print(f"  {opt}: select={select}, bid={tick.bid}, ask={tick.ask}")
            else:
                print(f"  {opt}: select={select}, tick=None")
                
    mt5.shutdown()

if __name__ == '__main__':
    test_prices_extended()
