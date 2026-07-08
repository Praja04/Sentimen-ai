"""
fundamental/cot_report.py
CFTC Commitments of Traders (COT) Report
Non-commercial (Large Speculator / Smart Money) net positions
Data updated every Friday from CFTC.gov
"""

import urllib.request
import csv
import io
import datetime

# CFTC COT data sources (tried in order)
CFTC_URLS = [
    # Legacy combined futures - has gold, currencies, oil
    "https://www.cftc.gov/dea/futures/com_fut.txt",
    # Disaggregated futures (backup)
    "https://www.cftc.gov/dea/futures/fut_disagg_txt_2025.zip",
    # Financial futures - has currencies
    "https://www.cftc.gov/dea/futures/fin_fut.txt",
]

# Market codes for each instrument
COT_MARKET_CODES = {
    "XAUUSD":    ["GOLD - COMMODITY EXCHANGE INC.", "GOLD"],
    "USDJPY":    ["JAPANESE YEN", "YEN"],
    "WTI OIL":   ["CRUDE OIL, LIGHT SWEET", "WTI CRUDE"],
    "NIKKEI":    ["NIKKEI STOCK AVERAGE", "NIKKEI"],
    "DOW JONES": ["DOW JONES", "DJIA"],
}

_cot_cache = {"data": None, "ts": None}
CACHE_TTL = 86400  # 24 hours (weekly data)


def _parse_cot_csv(text: str) -> dict:
    """Parse CFTC COT CSV text and return net positions by market name."""
    positions = {}
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            name = row.get("Market and Exchange Names", "").upper()
            try:
                nc_long  = int(row.get("Noncommercial Positions-Long (All)", 0) or 0)
                nc_short = int(row.get("Noncommercial Positions-Short (All)", 0) or 0)
                net = nc_long - nc_short
                positions[name] = {"long": nc_long, "short": nc_short, "net": net}
            except (ValueError, TypeError):
                continue
    except Exception:
        pass
    return positions


def _fetch_cot_data() -> dict:
    """Fetch latest COT data from CFTC. Returns dict of {market_name: positions}."""
    global _cot_cache
    now = datetime.datetime.utcnow()

    if (_cot_cache["ts"] and
            (now - _cot_cache["ts"]).total_seconds() < CACHE_TTL and
            _cot_cache["data"] is not None):
        return _cot_cache["data"]

    for url in CFTC_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read()
                # Handle zip files
                if url.endswith(".zip"):
                    import zipfile
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        name = zf.namelist()[0]
                        text = zf.read(name).decode("utf-8", errors="ignore")
                else:
                    text = content.decode("utf-8", errors="ignore")
            positions = _parse_cot_csv(text)
            if positions:
                _cot_cache["data"] = positions
                _cot_cache["ts"] = now
                return positions
        except Exception:
            continue

    _cot_cache["data"] = {}
    _cot_cache["ts"] = now
    return {}


def get_cot_score(instrument: str) -> dict:
    """
    Returns COT net position score for an instrument.
    Score: -1.0 (net short / bearish) to +1.0 (net long / bullish)
    """
    positions = _fetch_cot_data()

    market_keys = COT_MARKET_CODES.get(instrument, [])
    matched = None

    for key in market_keys:
        for market_name, pos in positions.items():
            if key in market_name:
                matched = pos
                break
        if matched:
            break

    if not matched:
        return {
            "score": 0.0, "bias": "NEUTRAL",
            "net_position": None,
            "note": "COT data not available for this instrument",
            "source": "CFTC.gov",
        }

    net = matched["net"]
    total = matched["long"] + matched["short"]

    # Normalize net position to -1 to +1
    if total > 0:
        raw_score = net / total
    else:
        raw_score = 0.0

    # Clamp and scale
    score = max(-1.0, min(1.0, raw_score))

    if score >= 0.2:
        bias = "BULLISH (Smart Money Long)"
        bias_icon = "🟢"
    elif score <= -0.2:
        bias = "BEARISH (Smart Money Short)"
        bias_icon = "🔴"
    else:
        bias = "NEUTRAL"
        bias_icon = "🟡"

    return {
        "score": round(score, 3),
        "bias": bias,
        "bias_icon": bias_icon,
        "net_position": net,
        "long": matched["long"],
        "short": matched["short"],
        "note": f"Net: {net:+,} contracts",
        "source": "CFTC COT (weekly)",
    }
