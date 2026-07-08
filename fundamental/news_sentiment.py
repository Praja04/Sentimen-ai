"""
fundamental/news_sentiment.py
News sentiment scoring using Google News RSS + VADER sentiment analysis
Covers: Fed speeches, Trump statements, OPEC, BoJ, economic news
"""

import feedparser
import datetime
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

# Custom finance-aware word boosts
analyzer.lexicon.update({
    "bullish": 2.5, "bearish": -2.5,
    "rally": 2.0, "surge": 2.0, "soar": 2.0, "spike": 1.5,
    "crash": -2.5, "plunge": -2.5, "tumble": -2.0, "slump": -2.0,
    "hawkish": -1.5, "dovish": 1.5,       # from gold/risk perspective
    "rate hike": -1.5, "rate cut": 1.5,
    "inflation": -0.5, "deflation": -1.0,
    "tariff": -1.5, "sanction": -1.5,
    "stimulus": 1.5, "QE": 1.5,
    "geopolitical": -1.0, "war": -2.0, "tension": -1.0,
    "safe haven": 2.0, "risk off": 1.5, "risk on": -0.5,
})

# Keywords per instrument → Google News RSS search
INSTRUMENT_QUERIES = {
    "XAUUSD": [
        "gold price Federal Reserve",
        "gold rally inflation",
        "gold safe haven",
        "Trump tariff gold",
    ],
    "USDJPY": [
        "Bank of Japan yen",
        "USD JPY dollar yen",
        "BoJ interest rate",
        "Japan economy",
    ],
    "WTI OIL": [
        "crude oil price OPEC",
        "WTI oil supply",
        "oil demand forecast",
    ],
    "NIKKEI": [
        "Nikkei Japan stock market",
        "Tokyo stock exchange",
        "Japan economy GDP",
    ],
    "DOW JONES": [
        "Dow Jones Wall Street",
        "S&P 500 US economy",
        "Federal Reserve rate decision",
        "Trump economy stock market",
    ],
}

_news_cache = {}
CACHE_TTL = 1800  # 30 minutes


def _fetch_google_news_rss(query: str, max_items: int = 8) -> list:
    """Fetch headlines from Google News RSS."""
    url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title": entry.get("title", ""),
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            })
        return items
    except Exception:
        return []


def _score_headline(text: str) -> float:
    """Score a single headline using VADER. Returns -1.0 to +1.0."""
    vs = analyzer.polarity_scores(text)
    return vs["compound"]


def get_news_sentiment(instrument: str) -> dict:
    """
    Returns news sentiment score for an instrument.
    Score: -1.0 (very bearish) to +1.0 (very bullish)
    """
    global _news_cache
    now = datetime.datetime.utcnow()
    cache_key = instrument

    if (cache_key in _news_cache and
            (now - _news_cache[cache_key]["ts"]).total_seconds() < CACHE_TTL):
        return _news_cache[cache_key]["data"]

    queries = INSTRUMENT_QUERIES.get(instrument, [instrument])
    all_headlines = []

    for query in queries[:2]:   # limit to 2 queries per instrument to save time
        headlines = _fetch_google_news_rss(query, max_items=5)
        all_headlines.extend(headlines)

    if not all_headlines:
        result = {
            "score": 0.0, "bias": "NEUTRAL",
            "headline_count": 0, "top_headlines": [],
            "note": "No news data available", "source": "Google News"
        }
        _news_cache[cache_key] = {"data": result, "ts": now}
        return result

    # Score each headline
    scores = []
    top_headlines = []
    for h in all_headlines[:10]:
        text = h["title"] + " " + h.get("summary", "")[:100]
        sc = _score_headline(text)
        scores.append(sc)
        top_headlines.append({
            "title": h["title"][:60],
            "score": round(sc, 2),
        })

    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Classify bias
    if avg_score >= 0.20:
        bias = "BULLISH"
        bias_icon = "🟢"
    elif avg_score <= -0.20:
        bias = "BEARISH"
        bias_icon = "🔴"
    else:
        bias = "NEUTRAL"
        bias_icon = "🟡"

    result = {
        "score": round(avg_score, 3),
        "bias": bias,
        "bias_icon": bias_icon,
        "headline_count": len(scores),
        "top_headlines": sorted(top_headlines, key=lambda x: abs(x["score"]), reverse=True)[:3],
        "note": f"{bias} sentiment from {len(scores)} headlines",
        "source": "Google News + VADER",
    }

    _news_cache[cache_key] = {"data": result, "ts": now}
    return result
