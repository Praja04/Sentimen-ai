import sys
sys.path.insert(0, r'C:\Antigravity')
import urllib.request, json

print("=== Testing Fundamental Modules ===\n")

# Test 1: Calendar
from fundamental.calendar import get_calendar_score
c = get_calendar_score("XAUUSD")
print(f"[CALENDAR] XAUUSD: score={c['score']}  note='{c['note']}'")

# Test 2: News Sentiment
from fundamental.news_sentiment import get_news_sentiment
n = get_news_sentiment("XAUUSD")
print(f"[NEWS]     XAUUSD: score={n['score']}  bias={n['bias']}  headlines={n['headline_count']}")

# Test 3: COT
from fundamental.cot_report import get_cot_score
k = get_cot_score("XAUUSD")
print(f"[COT]      XAUUSD: score={k['score']}  note='{k['note']}'")

# Test 4: Fed Scanner
from fundamental.fed_scanner import get_fed_score
f = get_fed_score("XAUUSD")
print(f"[FED]      XAUUSD: score={f['score']}  bias={f['bias']}")

# Test 5: Combined scorer
from fundamental.scorer import get_fundamental_score
fs = get_fundamental_score("XAUUSD")
print(f"\n[COMBINED] XAUUSD: score={fs['combined_score']}  conf_adj={fs['combined_confidence_adj']}%  bias={fs['bias_icon']} {fs['bias']}")
print(f"           Summary: {fs['summary']}")

print("\n=== Testing API endpoint ===\n")
d = json.loads(urllib.request.urlopen('http://127.0.0.1:5000/api/laggard_detection').read())
pairs = d.get('pair_recommendations', [])
for p in pairs:
    print(f"  {p['pair']:<12} tech={p.get('confidence_tech','?')}%  adj={p.get('confidence_fund_adj','?')}%  combined={p['confidence']}%  fund={p.get('fundamental_icon','?')} {p.get('fundamental_bias','?')}")
