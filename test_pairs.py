import urllib.request, json, time
time.sleep(3)
d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
pairs = d.get('pair_recommendations', [])
print('Total signals:', len(pairs))
for p in pairs:
    print(f"  {p['pair']:8}  {p['action']:4}  {p['quality']:6}  conf:{p['confidence']}%  gap:{p['gap']}")
