from app import search_backtest_methods

try:
    print("Running fast test (2 days of data)...")
    res = search_backtest_methods(
        symbol="XAUUSD",
        initial_capital=10000.0,
        start_month=None,
        end_month=None,
        days=2,
        risk_pct=1.0,
        filters={
            "drawdown": {"operator": ">", "value": 5.0},
            "win_rate": {"operator": "<", "value": 80.0},
            "monthly_profit": {"operator": "<", "value": 40.0},
        }
    )
    print("Success: tested", res["strategies_tested"], "strategies.")
except Exception as e:
    import traceback
    traceback.print_exc()
