import urllib.request, json, time
time.sleep(2)
d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
pairs = d.get('pair_recommendations', [])
print(f'Total signals: {len(pairs)}')
print()
for p in pairs:
    print(f"  {p['pair']:<10}  {p['action']:<4}  entry:{p.get('entry','N/A')}  sl:{p.get('sl','N/A')}  tp:{p.get('tp','N/A')}  atr:{p.get('atr','N/A')}")
