import urllib.request, json

d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
pairs = d.get('pair_recommendations', [])
print(f"Total signals: {len(pairs)}")
print()
for p in pairs:
    chg = p.get('change_pct')
    chg_str = f"{chg:+.3f}%" if chg is not None else "N/A"
    print(f"  {p['pair']:<12} {p['action']:<4}  entry:{p.get('entry','---')}  sl:{p.get('sl','---')}  tp:{p.get('tp','---')}  chg:{chg_str}  conf:{p['confidence']}%")
