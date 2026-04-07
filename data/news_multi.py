"""
Multi-source news fetcher: yfinance + Naver + NewsAPI + NewsData.io.
All articles filtered to last 24 hours and sector-relevant keywords.
"""

import os
import requests
import streamlit as st
from datetime import datetime, timedelta
import json

# ── Keywords ────────────────────────────────────────────────────────────────
TRANSPORT_KEYWORDS = {
    "en": ["shipping", "freight", "forwarding", "logistics", "airlines", "transport", "HMM", "glovis", "korean air", "cj logistics", "pan ocean"],
    "ko": ["운송", "항공", "해운", "물류", "글로비스", "대한항공", "대한통운", "택배", "HMM", "팬오션", "현대글로비스", "한진"],
}

HOLDINGS_KEYWORDS = {
    "en": ["conglomerate", "holding", "trading company", "diversified", "business portfolio", "SK", "Samsung", "LG", "CJ", "LS", "Hanwha", "HD Hyundai"],
    "ko": ["지주회사", "지배구조", "밸류업", "복합기업", "홀딩스", "삼성물산", "한화", "LG", "LS", "CJ", "SK", "HD현대", "HD", "포스코인터내셔널", "LX인터내셔널", "상사"],
}

ENERGY_KEYWORDS = {
    "en": ["energy", "power", "renewable", "electricity", "gas", "utilities"],
    "ko": ["에너지", "전력", "가스", "재생에너지", "발전"],
}

ALL_KEYWORDS = {
    "transport": TRANSPORT_KEYWORDS,
    "holdings": HOLDINGS_KEYWORDS,
    "energy": ENERGY_KEYWORDS,
}


def _is_sector_relevant(title: str, sector: str = "transport") -> bool:
    """Check if article title matches sector keywords."""
    title_lower = title.lower()
    keywords = ALL_KEYWORDS.get(sector, {})
    en_kw = keywords.get("en", [])
    ko_kw = keywords.get("ko", [])
    return any(kw in title_lower for kw in en_kw) or any(kw in title_lower for kw in ko_kw)


@st.cache_data(ttl=300)
def fetch_naver_news(query: str, max_results: int = 10) -> list[dict]:
    """
    Fetch news from Naver News Search API.
    Requires NAVER_CLIENT_ID and NAVER_CLIENT_SECRET environment variables.
    Returns list of {title, url, published, source} dicts.
    """
    client_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return []

    articles = []
    try:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {
            "query": query,
            "sort": "date",  # Latest first
            "display": max_results,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                # Naver returns HTML-encoded title and description
                title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                url_item = item.get("originalLink", "")
                source = item.get("source", "Naver News")
                pub_str = item.get("pubDate", "")
                published = None
                if pub_str:
                    try:
                        # Naver format: "Mon, 07 Apr 2026 10:30:00 +0900"
                        from email.utils import parsedate_to_datetime
                        published = parsedate_to_datetime(pub_str).replace(tzinfo=None)
                    except Exception:
                        pass
                articles.append({
                    "title": title,
                    "url": url_item,
                    "source": source,
                    "published": published,
                })
    except Exception:
        pass
    return articles


@st.cache_data(ttl=300)
def fetch_newsapi_news(query: str, max_results: int = 10) -> list[dict]:
    """
    Fetch news from NewsAPI.org.
    Requires NEWSAPI_KEY environment variable.
    """
    api_key = os.environ.get("NEWSAPI_KEY", "").strip()
    if not api_key:
        return []

    articles = []
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": max_results,
            "apiKey": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("articles", []):
                pub_str = item.get("publishedAt", "")
                published = None
                if pub_str:
                    try:
                        published = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                articles.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", {}).get("name", "NewsAPI"),
                    "published": published,
                })
    except Exception:
        pass
    return articles


@st.cache_data(ttl=300)
def fetch_newsdata_news(query: str, max_results: int = 10) -> list[dict]:
    """
    Fetch news from NewsData.io (supports Korean + English).
    Requires NEWSDATA_KEY environment variable.
    """
    api_key = os.environ.get("NEWSDATA_KEY", "").strip()
    if not api_key:
        return []

    articles = []
    try:
        url = "https://newsdata.io/api/1/news"
        params = {
            "q": query,
            "sortby": "publish_date",
            "language": "en,ko",
            "max": max_results,
            "apikey": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                pub_str = item.get("pubDate", "")
                published = None
                if pub_str:
                    try:
                        published = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                articles.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "source": item.get("source_id", "NewsData.io"),
                    "published": published,
                })
    except Exception:
        pass
    return articles


@st.cache_data(ttl=300)
def fetch_yfinance_news(ticker: str, max_results: int = 5) -> list[dict]:
    """Wrapper around yfinance news fetch."""
    import yfinance as yf
    from data.news import _parse_item

    articles = []
    try:
        raw_news = yf.Ticker(ticker).news or []
        for i, item in enumerate(raw_news[:max_results]):
            parsed = _parse_item(item, ticker)
            if parsed:
                articles.append({
                    "title": parsed["title"],
                    "url": parsed["url"],
                    "source": parsed["source"] or "yfinance",
                    "published": parsed["published"],
                    "ticker": ticker,
                })
    except Exception:
        pass
    return articles


def fetch_all_sources_for_sector(
    sector: str,
    ticker_names: dict[str, str] | None = None,
    max_per_source: int = 5,
) -> list[dict]:
    """
    Fetch news for a sector from all available sources.
    sector: "transport", "holdings", or "energy"
    ticker_names: {ticker: "company name"} for yfinance lookups
    Returns articles published in last 24h.
    """
    cutoff = datetime.now() - timedelta(hours=24)
    all_articles = []

    # Build query: sector name + all keywords
    keywords = ALL_KEYWORDS.get(sector, {})
    query_terms = (keywords.get("en", []) + keywords.get("ko", []))[:5]  # Top 5 keywords
    query = " OR ".join(query_terms[:3])  # Use first 3 for API query

    # ── Naver News ─────────────────────────────────────────────────────
    articles = fetch_naver_news(query, max_per_source)
    all_articles.extend(articles)

    # ── NewsAPI ─────────────────────────────────────────────────────────
    articles = fetch_newsapi_news(query, max_per_source)
    all_articles.extend(articles)

    # ── NewsData.io ─────────────────────────────────────────────────────
    articles = fetch_newsdata_news(query, max_per_source)
    all_articles.extend(articles)

    # ── yfinance (ticker-specific) ───────────────────────────────────────
    if ticker_names:
        for ticker in list(ticker_names.keys())[:5]:  # Limit to 5 tickers
            articles = fetch_yfinance_news(ticker, max_per_source)
            all_articles.extend(articles)

    # ── Filter to last 24h + deduplicate ─────────────────────────────────
    filtered = []
    seen_urls = set()
    for a in all_articles:
        pub = a.get("published")
        if not pub or pub < cutoff:
            continue
        url = a.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        filtered.append(a)

    # ── Sort by relevance (keyword match) then publish time ──────────────
    def _relevance_score(a: dict) -> tuple:
        title = a.get("title", "").lower()
        keywords = ALL_KEYWORDS.get(sector, {})
        all_kw = keywords.get("en", []) + keywords.get("ko", [])
        match_count = sum(1 for kw in all_kw if kw in title)
        pub = a.get("published") or datetime.min
        return (match_count, pub)

    filtered.sort(key=_relevance_score, reverse=True)
    return filtered[:15]  # Return top 15
