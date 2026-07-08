"""
fundamental/fed_scanner.py
Fed + Trump + Central Bank speech/policy sentiment scanner
Sources: Fed.gov RSS, ECB, BoJ, Google News RSS
Detects: hawkish/dovish signals, tariff risks, geopolitical events
"""

import feedparser
import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

# Hawkish/dovish keyword lexicon
HAWKISH_KEYWORDS = [
    "rate hike", "tighten", "hawkish", "inflation concern",
    "aggressive", "restrictive", "higher for longer",
    "tariff", "trade war", "sanction", "ban",
    "strong dollar", "dollar strength",
]
DOVISH_KEYWORDS = [
    "rate cut", "dovish", "easing", "stimulus",
    "quantitative easing", "QE", "pause hike",
    "soft landing", "support growth",
    "weak dollar", "dollar weakness",
]

# RSS feeds to monitor
FEEDS = {
    "Fed": [
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "https://news.google.com/rss/search?q=Federal+Reserve+Powell+interest+rate&hl=en&gl=US&ceid=US:en",
    ],
    "Trump": [
        "https://news.google.com/rss/search?q=Trump+economy+tariff+dollar&hl=en&gl=US&ceid=US:en",
    ],
    "BoJ": [
        "https://news.google.com/rss/search?q=Bank+of+Japan+BoJ+yen+interest+rate&hl=en&gl=US&ceid=US:en",
    ],
    "OPEC": [
        "https://news.google.com/rss/search?q=OPEC+crude+oil+production&hl=en&gl=US&ceid=US:en",
    ],
    "Geopolitical": [
        "https://news.google.com/rss/search?q=geopolitical+risk+war+sanctions&hl=en&gl=US&ceid=US:en",
    ],
}

# Which sources affect which instruments
SOURCE_INSTRUMENT_MAP = {
    "Fed":         ["XAUUSD", "USDJPY", "DOW JONES", "WTI OIL"],
    "Trump":       ["XAUUSD", "USDJPY", "DOW JONES", "WTI OIL"],
    "BoJ":         ["USDJPY", "NIKKEI"],
    "OPEC":        ["WTI OIL"],
    "Geopolitical":["XAUUSD"],
}

_fed_cache = {}
CACHE_TTL = 1800  # 30 minutes


def _fetch_feed_headlines(urls: list, max_items: int = 5) -> list:
    headlines = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_items]:
                headlines.append(entry.get("title", ""))
            if headlines:
                break
        except Exception:
            continue
    return headlines


def _classify_text(text: str) -> float:
    """
    Returns a score:
    - Hawkish (bad for gold, good for USD) → negative score for gold, positive for USD
    - Dovish (good for gold, bad for USD) → positive score
    """
    text_lower = text.lower()
    hawkish_count = sum(1 for kw in HAWKISH_KEYWORDS if kw in text_lower)
    dovish_count  = sum(1 for kw in DOVISH_KEYWORDS  if kw in text_lower)

    vader_score = analyzer.polarity_scores(text)["compound"]

    # Combine keyword count with VADER
    keyword_score = (dovish_count - hawkish_count) * 0.2
    combined = (keyword_score * 0.6) + (vader_score * 0.4)
    return max(-1.0, min(1.0, combined))


def get_fed_score(instrument: str) -> dict:
    """
    Returns Fed/CB/Trump policy sentiment score for an instrument.
    Score: -1.0 (hawkish / risk-off) to +1.0 (dovish / bullish)
    """
    global _fed_cache
    now = datetime.datetime.utcnow()
    cache_key = instrument

    if (cache_key in _fed_cache and
            (now - _fed_cache[cache_key]["ts"]).total_seconds() < CACHE_TTL):
        return _fed_cache[cache_key]["data"]

    # Find which sources affect this instrument
    relevant_sources = [src for src, insts in SOURCE_INSTRUMENT_MAP.items()
                        if instrument in insts]

    all_scores = []
    source_details = []

    for source_name in relevant_sources:
        urls = FEEDS.get(source_name, [])
        headlines = _fetch_feed_headlines(urls, max_items=5)
        if not headlines:
            continue

        scores = [_classify_text(h) for h in headlines]
        avg = sum(scores) / len(scores)
        all_scores.append(avg)

        if avg >= 0.15:
            bias_icon = "🟢"
        elif avg <= -0.15:
            bias_icon = "🔴"
        else:
            bias_icon = "🟡"

        source_details.append(f"{bias_icon} {source_name}: {avg:+.2f}")

    if not all_scores:
        result = {
            "score": 0.0, "bias": "NEUTRAL",
            "note": "No CB/policy data available",
            "details": [],
            "source": "Fed/BoJ/OPEC/Trump RSS",
        }
        _fed_cache[cache_key] = {"data": result, "ts": now}
        return result

    final_score = sum(all_scores) / len(all_scores)

    if final_score >= 0.15:
        bias = "DOVISH / BULLISH"
        bias_icon = "🟢"
    elif final_score <= -0.15:
        bias = "HAWKISH / RISK-OFF"
        bias_icon = "🔴"
    else:
        bias = "NEUTRAL"
        bias_icon = "🟡"

    result = {
        "score": round(final_score, 3),
        "bias": bias,
        "bias_icon": bias_icon,
        "details": source_details[:3],
        "note": f"{bias_icon} {bias} from {len(relevant_sources)} sources",
        "source": "Fed/BoJ/OPEC/Trump RSS",
    }

    _fed_cache[cache_key] = {"data": result, "ts": now}
    return result
