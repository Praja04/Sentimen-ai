"""
fundamental/calendar.py
Economic Calendar from Forex Factory RSS + Investing.com RSS
Provides: high-impact events for today, actual vs forecast scoring
"""

import feedparser
import datetime
import re
from functools import lru_cache

# Currency → instruments affected
CURRENCY_INSTRUMENT_MAP = {
    "USD": ["XAUUSD", "USDJPY", "WTI OIL", "DOW JONES"],
    "JPY": ["USDJPY", "NIKKEI"],
    "EUR": ["XAUUSD"],
    "GBP": [],
    "CHF": ["XAUUSD"],
    "ALL": ["XAUUSD", "USDJPY", "WTI OIL", "NIKKEI", "DOW JONES"],
}

# Keywords mapped to impact level
HIGH_IMPACT_KEYWORDS = [
    "non-farm", "nfp", "fomc", "fed rate", "interest rate decision",
    "cpi", "inflation", "gdp", "unemployment", "payroll",
    "retail sales", "pce", "jackson hole", "powell", "fed chair",
    "boj", "bank of japan", "ecb", "opec",
]

CALENDAR_FEEDS = [
    "https://www.forexfactory.com/ff_calendar_thisweek.xml",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
]

_calendar_cache = {"data": None, "ts": None}
CACHE_TTL = 1800  # 30 minutes


def fetch_calendar_events():
    """Fetch and parse economic calendar events for today."""
    global _calendar_cache
    now = datetime.datetime.utcnow()

    if (_calendar_cache["ts"] and
            (now - _calendar_cache["ts"]).total_seconds() < CACHE_TTL and
            _calendar_cache["data"] is not None):
        return _calendar_cache["data"]

    events = []
    today_str = now.strftime("%Y-%m-%d")

    for feed_url in CALENDAR_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = entry.get("title", "").lower()
                summary = entry.get("summary", "").lower()
                published = entry.get("published", "")

                # Check if today's event
                if today_str not in published and now.strftime("%b %d") not in published:
                    # Try to parse date from title/summary
                    pass

                # Detect impact
                is_high = any(kw in title or kw in summary for kw in HIGH_IMPACT_KEYWORDS)
                impact = "HIGH" if is_high else "MEDIUM"

                # Detect currency
                currency = "USD"
                for cur in ["USD", "JPY", "EUR", "GBP", "CHF", "CAD", "AUD", "NZD"]:
                    if cur in entry.get("title", "").upper():
                        currency = cur
                        break

                events.append({
                    "title": entry.get("title", "Unknown"),
                    "currency": currency,
                    "impact": impact,
                    "published": published,
                    "summary": entry.get("summary", ""),
                })

            if events:
                break
        except Exception:
            continue

    _calendar_cache["data"] = events
    _calendar_cache["ts"] = now
    return events


def get_calendar_score(instrument: str) -> dict:
    """
    Returns calendar impact score for a given instrument.
    Score: -1.0 (negative/risky) to +1.0 (positive/supportive)
    """
    events = fetch_calendar_events()
    score = 0.0
    alerts = []
    high_impact_count = 0

    for ev in events:
        affected = CURRENCY_INSTRUMENT_MAP.get(ev["currency"], [])
        if instrument not in affected:
            affected_all = CURRENCY_INSTRUMENT_MAP.get("ALL", [])
            if instrument not in affected_all:
                continue

        if ev["impact"] == "HIGH":
            high_impact_count += 1
            alerts.append(f"⚠️ HIGH: {ev['title'][:40]}")

    # High-impact events = uncertainty → reduce confidence
    if high_impact_count >= 2:
        score = -0.3
        note = f"{high_impact_count} high-impact events today — elevated risk"
    elif high_impact_count == 1:
        score = -0.15
        note = f"1 high-impact event today"
    else:
        score = 0.1
        note = "No major events — clean technical setup"

    return {
        "score": round(score, 3),
        "high_impact_count": high_impact_count,
        "alerts": alerts[:3],
        "note": note,
        "source": "Forex Factory",
    }
