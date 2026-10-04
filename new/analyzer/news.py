"""News context panel (framework §11) — DISPLAY-ONLY, NOT scored.

We proved (see EDGE.md) that headline sentiment has ~zero predictive power at
retail horizons — it's priced in within seconds and attention spikes mean-revert.
So news is surfaced purely as context for the human reader, with a neutral
sentiment tag, and it never touches the quality score.
"""
from __future__ import annotations


def run_news(ticker: str, limit: int = 8) -> dict:
    import yfinance as yf
    try:
        an = _analyzer()
    except Exception:
        an = None
    items = []
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        raw = []
    for n in raw[:limit]:
        c = n.get("content", n)
        title = c.get("title") or ""
        if not title:
            continue
        pub = c.get("pubDate") or c.get("providerPublishTime") or ""
        tag = "neutral"
        if an is not None:
            s = an.polarity_scores(title)["compound"]
            tag = "positive" if s > 0.25 else "negative" if s < -0.25 else "neutral"
        items.append({"title": title[:140], "published": str(pub)[:10], "sentiment_tag": tag})
    return {
        "headlines": items, "count": len(items),
        "note": "DISPLAY-ONLY, not scored — headline sentiment has ~zero predictive "
                "power at retail horizons (priced in seconds); for human context only",
    }


def _analyzer():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    return SentimentIntensityAnalyzer()
