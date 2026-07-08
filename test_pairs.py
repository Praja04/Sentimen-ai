import urllib.request, json

d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
ci = d['currency_indices']
pairs = d['pair_recommendations']

print("=== CSI RANKING ===")
sorted_ci = sorted(ci.items(), key=lambda x: x[1]['score'], reverse=True)
for k, v in sorted_ci:
    print(f"  {k}: score={v['score']:5.1f}  pct={v['percentage']:+.3f}%")

print()
print("=== CURRENT PAIRS ===")
for p in pairs:
    print(f"  {p['pair']:<10}  {p['action']:<4}  strong={p['strong']}  weak={p['weak']}")

# Count how many times each currency appears
from collections import Counter
strong_count = Counter(p['strong'] for p in pairs)
weak_count   = Counter(p['weak'] for p in pairs)
print()
print("=== CURRENCY DOMINATION ===")
print("Strong:", dict(strong_count))
print("Weak  :", dict(weak_count))
