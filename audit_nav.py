import os

pages = [
    ('index.html',       'C:/Antigravity/static/index.html'),
    ('backtest.html',    'C:/Antigravity/static/backtest.html'),
    ('forecast.html',    'C:/Antigravity/static/forecast.html'),
    ('monitor.html',     'C:/Antigravity/static/monitor.html'),
    ('trade.html',       'C:/Antigravity/static/trade.html'),
    ('intermarket.html', 'C:/Antigravity/templates/intermarket.html'),
]
targets = [
    ('HOME',        'href="/"'),
    ('BACKTEST',    '/backtest'),
    ('TRADE',       '/trade'),
    ('FORECAST',    '/Forecast'),
    ('MONITOR',     '/Monitor'),
    ('INTERMARKET', '/Intermarket'),
]
for name, path in pages:
    content = open(path, encoding='utf-8').read()
    print(f'--- {name} ---')
    for label, pattern in targets:
        found = pattern in content
        status = 'OK     ' if found else 'MISSING'
        print(f'  {status}  {label}')
    print()
