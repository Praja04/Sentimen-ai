"""
fundamental/scorer.py
Master fundamental scorer — combines all 4 sources into a single score
per instrument with weighted averaging.

Weights:
  Calendar    20%  (event risk / data surprises)
  News        35%  (current sentiment from headlines)
  COT         20%  (smart money positioning)
  Fed/CB      25%  (central bank policy direction)
"""

import datetime
import concurrent.futures

from .calendar      import get_calendar_score
from .news_sentiment import get_news_sentiment
from .cot_report    import get_cot_score
from .fed_scanner   import get_fed_score

WEIGHTS = {
    "calendar": 0.20,
    "news":     0.35,
    "cot":      0.20,
    "fed":      0.25,
}

_score_cache = {}
CACHE_TTL = 1800  # 30 minutes

INSTRUMENTS = ["XAUUSD", "USDJPY", "WTI OIL", "NIKKEI", "DOW JONES"]


def _fetch_all_scores(instrument: str) -> dict:
    """Fetch all 4 fundamental scores in parallel for speed."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        f_cal  = ex.submit(get_calendar_score, instrument)
        f_news = ex.submit(get_news_sentiment, instrument)
        f_cot  = ex.submit(get_cot_score,      instrument)
        f_fed  = ex.submit(get_fed_score,       instrument)

        cal  = f_cal.result()
        news = f_news.result()
        cot  = f_cot.result()
        fed  = f_fed.result()

    return {"calendar": cal, "news": news, "cot": cot, "fed": fed}


def get_fundamental_score(instrument: str) -> dict:
    """
    Returns a combined fundamental score for an instrument.

    Returns:
        {
          "combined_score": float (-1 to +1),
          "combined_confidence_adj": float (-20 to +20, added to technical conf),
          "bias": str,
          "bias_icon": str,
          "components": { calendar, news, cot, fed },
          "summary": str,
        }
    """
    global _score_cache
    now = datetime.datetime.utcnow()

    if (instrument in _score_cache and
            (now - _score_cache[instrument]["ts"]).total_seconds() < CACHE_TTL):
        return _score_cache[instrument]["data"]

    try:
        components = _fetch_all_scores(instrument)
    except Exception as e:
        return {
            "combined_score": 0.0,
            "combined_confidence_adj": 0.0,
            "bias": "NEUTRAL",
            "bias_icon": "🟡",
            "components": {},
            "summary": f"Fundamental data unavailable: {e}",
        }

    # Weighted average
    cal_s  = components["calendar"]["score"]
    news_s = components["news"]["score"]
    cot_s  = components["cot"]["score"]
    fed_s  = components["fed"]["score"]

    combined = (
        cal_s  * WEIGHTS["calendar"] +
        news_s * WEIGHTS["news"] +
        cot_s  * WEIGHTS["cot"] +
        fed_s  * WEIGHTS["fed"]
    )
    combined = max(-1.0, min(1.0, combined))

    # Convert to confidence adjustment (-20% to +20%)
    conf_adj = round(combined * 20.0, 1)

    # Classify bias
    if combined >= 0.15:
        bias = "BULLISH"
        bias_icon = "🟢"
    elif combined <= -0.15:
        bias = "BEARISH"
        bias_icon = "🔴"
    else:
        bias = "NEUTRAL"
        bias_icon = "🟡"

    # Build human-readable summary
    parts = []
    if abs(cal_s) > 0.1:
        parts.append(components["calendar"]["note"])
    if components["news"]["bias"] != "NEUTRAL":
        parts.append(components["news"]["note"])
    if components["fed"]["bias"] != "NEUTRAL":
        parts.append(components["fed"]["note"])
    if components["cot"]["net_position"] is not None:
        parts.append(components["cot"]["note"])

    summary = " · ".join(parts[:2]) if parts else "No significant fundamental signals"

    result = {
        "combined_score":          round(combined, 3),
        "combined_confidence_adj": conf_adj,
        "bias":       bias,
        "bias_icon":  bias_icon,
        "components": {
            "calendar": {
                "score": cal_s,
                "note":  components["calendar"]["note"],
                "alerts": components["calendar"].get("alerts", []),
            },
            "news": {
                "score":     news_s,
                "bias":      components["news"]["bias"],
                "bias_icon": components["news"].get("bias_icon", "🟡"),
                "headlines": components["news"].get("top_headlines", []),
            },
            "cot": {
                "score":        cot_s,
                "bias":         components["cot"]["bias"],
                "net_position": components["cot"]["net_position"],
                "note":         components["cot"]["note"],
            },
            "fed": {
                "score":   fed_s,
                "bias":    components["fed"]["bias"],
                "details": components["fed"].get("details", []),
            },
        },
        "summary": summary,
    }

    _score_cache[instrument] = {"data": result, "ts": now}
    return result


def get_all_fundamental_scores() -> dict:
    """Fetch fundamental scores for all 5 instruments in parallel."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(get_fundamental_score, inst): inst for inst in INSTRUMENTS}
        for future, inst in futures.items():
            try:
                results[inst] = future.result(timeout=15)
            except Exception:
                results[inst] = {
                    "combined_score": 0.0,
                    "combined_confidence_adj": 0.0,
                    "bias": "NEUTRAL",
                    "bias_icon": "🟡",
                    "components": {},
                    "summary": "Timeout",
                }
    return results
