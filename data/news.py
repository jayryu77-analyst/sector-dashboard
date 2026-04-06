"""
Fetch recent news headlines via yfinance.
Handles both old (pre-1.0) and new (1.x) yfinance news item structures.
"""

import yfinance as yf
import streamlit as st
from datetime import datetime, timezone

HIGH_IMPACT_KEYWORDS = [
    "earnings", "dividend", "buyback", "merger", "acquisition",
    "fed", "rate", "inflation", "recession", "tariff",
    "guidance", "downgrade", "upgrade", "outlook",
    # Korean keywords
    "실적", "배당", "합병", "인수", "금리", "수주", "공시",
]


def _parse_item(item: dict, ticker: str) -> dict | None:
    """Parse a yfinance news item regardless of API version."""
    title, url, source, published = "", "", "", None

    # yfinance 1.x format: item has 'content' sub-dict
    if "content" in item:
        c = item["content"]
        title = c.get("title", "")
        # URL is nested
        for url_key in ("canonicalUrl", "clickThroughUrl"):
            if c.get(url_key, {}).get("url"):
                url = c[url_key]["url"]
                break
        source = (c.get("provider") or {}).get("displayName", "")
        pub_str = c.get("pubDate", "")
        if pub_str:
            try:
                published = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass
    else:
        # Legacy format
        title = item.get("title", "")
        url = item.get("link", "") or item.get("url", "")
        source = item.get("publisher", "") or item.get("source", "")
        pub_ts = item.get("providerPublishTime", 0)
        if pub_ts:
            try:
                published = datetime.fromtimestamp(int(pub_ts))
            except Exception:
                pass

    if not title:
        return None

    high_impact = any(kw in title.lower() for kw in HIGH_IMPACT_KEYWORDS)
    return {
        "ticker": ticker,
        "title": title,
        "url": url,
        "published": published,
        "high_impact": high_impact,
        "source": source,
    }


@st.cache_data(ttl=600)
def fetch_sector_news(tickers: list[str], max_per_ticker: int = 3) -> list[dict]:
    """
    Fetch recent news for the given tickers.
    Returns list of article dicts sorted by publish time descending.
    """
    articles = []
    for ticker in tickers:
        try:
            raw_news = yf.Ticker(ticker).news or []
            count = 0
            for item in raw_news:
                if count >= max_per_ticker:
                    break
                parsed = _parse_item(item, ticker)
                if parsed:
                    articles.append(parsed)
                    count += 1
        except Exception:
            pass

    articles.sort(key=lambda x: x["published"] or datetime.min, reverse=True)
    return articles


def format_news_for_telegram(articles: list[dict], limit: int = 5) -> str:
    """Format top news articles as a Telegram Markdown message."""
    if not articles:
        return ""
    lines = ["📰 *News Highlights*\n"]
    for a in articles[:limit]:
        flag = "🔔 " if a["high_impact"] else ""
        ts = a["published"].strftime("%m/%d %H:%M") if a["published"] else ""
        lines.append(f"{flag}*[{a['ticker']}]* {a['title']}")
        if ts:
            lines.append(f"  _{a['source']} · {ts}_")
        if a["url"]:
            lines.append(f"  {a['url']}")
        lines.append("")
    return "\n".join(lines)
