"""
Fetches sector ETF and Korean stock data via yfinance.
"""

import yfinance as yf
import pandas as pd
import streamlit as st

# ── US Market ────────────────────────────────────────────────────────────────
SECTORS = {
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLK": "Technology",
    "XLU": "Utilities",
}

# ── Korean Market ─────────────────────────────────────────────────────────────
KR_STOCKS = {
    "Transport": {
        "086280.KS": "Hyundai Glovis",
        "000120.KS": "CJ Logistics",
        "003490.KS": "Korean Air",
        "011200.KS": "HMM",
        "028670.KS": "Pan Ocean",
    },
    "Holdings": {
        "034730.KS": "SK Holdings",
        "028260.KS": "Samsung C&T",
        "003550.KS": "LG Corp",
        "267250.KS": "HD Hyundai",
        "000880.KS": "Hanwha Corp",
        "001040.KS": "CJ Corp",
        "006260.KS": "LS Corp",
    },
}

# Flat maps for quick lookups
KR_TICKER_NAME = {t: n for sec in KR_STOCKS.values() for t, n in sec.items()}
KR_TICKER_SECTOR = {t: sec for sec, stocks in KR_STOCKS.items() for t in stocks}

PERIOD_OPTIONS = {
    "1 Week": "5d",
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "YTD": "ytd",
    "1 Year": "1y",
}


# ── US Fetch ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_sector_history(period: str = "1mo") -> dict[str, pd.DataFrame]:
    """Return OHLCV DataFrames keyed by ticker for the given period."""
    tickers = list(SECTORS.keys())
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    result = {}
    for ticker in tickers:
        try:
            df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]]
            df = df.dropna()
            result[ticker] = df
        except KeyError:
            pass
    return result


@st.cache_data(ttl=300)
def fetch_sector_performance(period: str = "1mo") -> pd.DataFrame:
    """Return DataFrame: ticker, name, current_price, change_pct, volume."""
    history = fetch_sector_history(period)
    rows = []
    for ticker, df in history.items():
        if df.empty or len(df) < 2:
            continue
        start_price = df["Close"].iloc[0]
        end_price = df["Close"].iloc[-1]
        change_pct = (end_price - start_price) / start_price * 100
        rows.append({
            "ticker": ticker,
            "name": SECTORS[ticker],
            "current_price": round(float(end_price), 2),
            "change_pct": round(float(change_pct), 2),
            "volume": int(df["Volume"].iloc[-1]),
        })
    df_perf = pd.DataFrame(rows)
    if not df_perf.empty:
        df_perf = df_perf.sort_values("change_pct", ascending=False).reset_index(drop=True)
    return df_perf


# ── Korean Fetch ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_kr_history(period: str = "1mo") -> dict[str, pd.DataFrame]:
    """Return OHLCV DataFrames for Korean stocks."""
    tickers = list(KR_TICKER_NAME.keys())
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    result = {}
    for ticker in tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]]
            else:
                df = raw[["Open", "High", "Low", "Close", "Volume"]]
            df = df.dropna()
            result[ticker] = df
        except (KeyError, TypeError):
            pass
    return result


@st.cache_data(ttl=300)
def fetch_kr_performance(period: str = "1mo") -> pd.DataFrame:
    """
    Return DataFrame: ticker, name, sector, current_price(KRW),
    change_pct, per, pbr  — sorted by sector then change_pct.
    """
    history = fetch_kr_history(period)
    rows = []
    for ticker, df in history.items():
        if df.empty or len(df) < 2:
            continue
        start_price = float(df["Close"].iloc[0])
        end_price = float(df["Close"].iloc[-1])
        change_pct = (end_price - start_price) / start_price * 100
        rows.append({
            "ticker": ticker,
            "name": KR_TICKER_NAME.get(ticker, ticker),
            "sector": KR_TICKER_SECTOR.get(ticker, ""),
            "current_price": round(end_price, 0),
            "change_pct": round(change_pct, 2),
        })
    df_perf = pd.DataFrame(rows)
    if not df_perf.empty:
        df_perf = df_perf.sort_values(
            ["sector", "change_pct"], ascending=[True, False]
        ).reset_index(drop=True)
    return df_perf


@st.cache_data(ttl=3600)
def fetch_kr_valuation() -> pd.DataFrame:
    """
    Return DataFrame: ticker, per, pbr
    Cached for 1 hour since .info calls are slow.
    """
    rows = []
    for ticker in KR_TICKER_NAME:
        try:
            info = yf.Ticker(ticker).info
            per = info.get("trailingPE") or info.get("forwardPE")
            pbr = info.get("priceToBook")
            rows.append({
                "ticker": ticker,
                "per": round(per, 1) if per and per > 0 else None,
                "pbr": round(pbr, 2) if pbr and pbr > 0 else None,
            })
        except Exception:
            rows.append({"ticker": ticker, "per": None, "pbr": None})
    return pd.DataFrame(rows)
