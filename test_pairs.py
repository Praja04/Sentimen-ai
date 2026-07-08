import urllib.request, json, time
time.sleep(2)
d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
pairs = d.get('pair_recommendations', [])
print('Total signals:', len(pairs))
for p in pairs:
    print(f"  {p['pair']:<10}  {p['action']:<4}  conf:{p['confidence']}%  chg:{p.get('change_pct', 'N/A')}")
