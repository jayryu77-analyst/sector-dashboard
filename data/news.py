"""
Fetch recent news headlines via yfinance.
Handles both old (pre-1.0) and new (1.x) yfinance news item structures.
All public functions return only articles published within the last 24 hours.
"""

import yfinance as yf
import streamlit as st
from datetime import datetime, timedelta

HIGH_IMPACT_KEYWORDS = [
    # English
    "earnings", "dividend", "buyback", "merger", "acquisition",
    "fed", "rate", "inflation", "recession", "tariff",
    "guidance", "downgrade", "upgrade", "outlook",
    "contract", "deal", "agreement", "joint venture",
    # Korean — Transport/Logistics
    "운송", "항공", "해운", "물류", "글로비스", "대한항공", "대한통운", "택배",
    "HMM", "팬오션", "한진", "현대글로비스",
    # Korean — Holdings/Conglomerate
    "지주회사", "지배구조", "밸류업", "복합기업", "홀딩스",
    "삼성물산", "한화", "포스코인터내셔널", "LX인터내셔널", "상사",
    # Korean — Energy/Utilities
    "에너지", "전력", "가스", "재생에너지", "발전", "전망",
    # Common Korean
    "실적", "배당", "합병", "인수", "금리", "수주", "공시", "계약",
]


def _parse_item(item: dict, ticker: str) -> dict | None:
    """Parse a yfinance news item regardless of API version."""
    title, url, source, published = "", "", "", None

    if "content" in item:                        # yfinance 1.x
        c = item["content"]
        title = c.get("title", "")
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
    else:                                        # legacy format
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


def _is_recent(article: dict, hours: int = 24) -> bool:
    pub = article.get("published")
    if not pub:
        return False
    return pub >= datetime.now() - timedelta(hours=hours)


@st.cache_data(ttl=600)
def fetch_sector_news(tickers: list[str], max_per_ticker: int = 5) -> list[dict]:
    """
    Fetch news for the given tickers published in the last 24 hours.
    Returns list of article dicts sorted by (high_impact desc, publish time desc).
    """
    articles = []
    cutoff = datetime.now() - timedelta(hours=24)

    for ticker in tickers:
        try:
            raw_news = yf.Ticker(ticker).news or []
            count = 0
            for item in raw_news:
                if count >= max_per_ticker:
                    break
                parsed = _parse_item(item, ticker)
                if parsed and parsed["published"] and parsed["published"] >= cutoff:
                    articles.append(parsed)
                    count += 1
        except Exception:
            pass

    articles.sort(key=lambda x: (x["high_impact"], x["published"] or datetime.min), reverse=True)
    return articles


def fetch_all_sector_news(kr_stocks: dict[str, dict[str, str]], max_per_ticker: int = 3) -> dict[str, list[dict]]:
    """
    Fetch last-24h news for all stocks grouped by sector.
    kr_stocks: {sector_name: {ticker: name, ...}}
    Returns: {sector_name: [article, ...]}
    """
    result = {}
    for sector, stocks in kr_stocks.items():
        tickers = list(stocks.keys())
        result[sector] = fetch_sector_news(tickers, max_per_ticker=max_per_ticker)
    return result


def format_articles_for_telegram(articles: list[dict], name_map: dict | None = None) -> str:
    """Format selected articles as a Telegram Markdown message."""
    if not articles:
        return ""
    lines = ["📰 *News Digest*\n"]
    for a in articles:
        flag = "🔔 " if a["high_impact"] else ""
        ts = a["published"].strftime("%m/%d %H:%M") if a["published"] else ""
        label = (name_map or {}).get(a["ticker"], a["ticker"])
        lines.append(f"{flag}*[{label}]* {a['title']}")
        if ts or a.get("source"):
            lines.append(f"  _{a.get('source', '')} · {ts}_")
        if a.get("url"):
            lines.append(f"  {a['url']}")
        lines.append("")
    return "\n".join(lines)
