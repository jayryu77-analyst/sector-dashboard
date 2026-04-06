"""
Fetch recent news headlines for sector ETFs via yfinance.

Inspired by keyword-filtered disclosure monitoring (DART pattern).
Keywords target macro/sector-moving events relevant to US equity sectors.
"""

import yfinance as yf
import streamlit as st
from datetime import datetime

# Keywords that indicate high-impact sector news (analogous to DART keyword filter)
HIGH_IMPACT_KEYWORDS = [
    "earnings", "dividend", "buyback", "merger", "acquisition",
    "fed", "rate", "inflation", "recession", "tariff",
    "guidance", "downgrade", "upgrade", "outlook",
]


@st.cache_data(ttl=600)
def fetch_sector_news(tickers: list[str], max_per_ticker: int = 3) -> list[dict]:
    """
    Fetch recent news for the given tickers.
    Returns a list of dicts: {ticker, title, url, published, high_impact}
    sorted by publish time descending.
    """
    articles = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).news or []
            for item in info[:max_per_ticker]:
                title = item.get("title", "")
                pub_ts = item.get("providerPublishTime", 0)
                published = datetime.fromtimestamp(pub_ts) if pub_ts else None
                high_impact = any(kw in title.lower() for kw in HIGH_IMPACT_KEYWORDS)
                articles.append({
                    "ticker": ticker,
                    "title": title,
                    "url": item.get("link", ""),
                    "published": published,
                    "high_impact": high_impact,
                    "source": item.get("publisher", ""),
                })
        except Exception:
            pass

    articles.sort(key=lambda x: x["published"] or datetime.min, reverse=True)
    return articles


def format_news_for_telegram(articles: list[dict], limit: int = 5) -> str:
    """Format top news articles as a Telegram message."""
    if not articles:
        return ""
    lines = ["📰 *Sector News Highlights*\n"]
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
