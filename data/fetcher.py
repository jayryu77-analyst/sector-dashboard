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
    "1 Day": "1d",
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
    # yfinance returns only one row for "1d"; use 2d/1d interval for last-day change.
    if period == "1d":
        yf_period = "2d"
        yf_interval = "1d"
    else:
        yf_period = period
        yf_interval = None
    tickers = list(SECTORS.keys())
    raw = yf.download(
        tickers,
        period=yf_period,
        interval=yf_interval,
        auto_adjust=True,
        progress=False,
    )
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
        if period == "1d":
            if len(df) < 2:
                continue
            start_price = df["Close"].iloc[-2]
        else:
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
    # yfinance returns only one row for "1d"; use 2d/1d interval for last-day change.
    if period == "1d":
        yf_period = "2d"
        yf_interval = "1d"
    else:
        yf_period = period
        yf_interval = None
    tickers = list(KR_TICKER_NAME.keys())
    raw = yf.download(
        tickers,
        period=yf_period,
        interval=yf_interval,
        auto_adjust=True,
        progress=False,
    )
    result = {}
    def _extract_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
        cols = ["Open", "High", "Low", "Close", "Volume"]
        if all(c in df.columns for c in cols):
            return df[cols].dropna()
        return None
    for ticker in tickers:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                df = None
                # yfinance can return either level-1 or level-0 as ticker depending on group_by/version
                if ticker in raw.columns.get_level_values(1):
                    df = raw.xs(ticker, axis=1, level=1)
                elif ticker in raw.columns.get_level_values(0):
                    df = raw.xs(ticker, axis=1, level=0)
                if isinstance(df, pd.DataFrame):
                    df = _extract_ohlcv(df)
                if df is not None and not df.empty:
                    result[ticker] = df
            else:
                # Single-ticker download returns a flat DataFrame
                if len(tickers) == 1:
                    df = _extract_ohlcv(raw)
                    if df is not None and not df.empty:
                        result[ticker] = df
        except (KeyError, TypeError):
            pass
    # Fallback: per-ticker download if multi-ticker request failed
    if not result:
        for ticker in tickers:
            try:
                single = yf.download(
                    ticker,
                    period=yf_period,
                    interval=yf_interval,
                    auto_adjust=True,
                    progress=False,
                )
                df = _extract_ohlcv(single)
                if df is not None and not df.empty:
                    result[ticker] = df
            except Exception:
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
        if period == "1d":
            if len(df) < 2:
                continue
            start_price = float(df["Close"].iloc[-2])
        else:
            start_price = float(df["Close"].iloc[0])
        end_price = float(df["Close"].iloc[-1])
        change_pct = (end_price - start_price) / start_price * 100
        rows.append({
            "ticker": ticker,
            "name": KR_TICKER_NAME.get(ticker, ticker),
            "sector": KR_TICKER_SECTOR.get(ticker, ""),
            "start_price": round(start_price, 0),
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
    Return DataFrame: ticker, per, pbr, source.
    Primary source: pykrx (KRX official data).
    Fallback: yfinance .info.
    Cached for 1 hour.
    """
    # ── 1. Try pykrx (most accurate for Korean stocks) ───────────────────
    pykrx_data: dict[str, dict] = {}
    try:
        from pykrx import stock as krx_stock
        from datetime import datetime, timedelta
        # KRX may not have today's data yet; try up to 5 business days back
        for days_back in range(0, 7):
            date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
            try:
                df_fund = krx_stock.get_market_fundamental_by_ticker(date_str, "KOSPI")
                if df_fund is not None and not df_fund.empty:
                    for code_6, row in df_fund.iterrows():
                        pykrx_data[str(code_6)] = {
                            "per": float(row["PER"]) if row["PER"] > 0 else None,
                            "pbr": float(row["PBR"]) if row["PBR"] > 0 else None,
                        }
                    break  # got data — stop
            except Exception:
                continue
    except ImportError:
        pass

    # ── 2. Build result, fall back to yfinance per ticker ────────────────
    rows = []
    for ticker in KR_TICKER_NAME:
        code_6 = ticker.replace(".KS", "").replace(".KQ", "")
        per, pbr, source = None, None, "N/A"

        if code_6 in pykrx_data:
            per = pykrx_data[code_6]["per"]
            pbr = pykrx_data[code_6]["pbr"]
            source = "KRX"
        else:
            # Fallback: yfinance
            try:
                info = yf.Ticker(ticker).info
                per_yf = info.get("trailingPE") or info.get("forwardPE")
                pbr_yf = info.get("priceToBook")
                if not pbr_yf:
                    book = info.get("bookValue")
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                    if book and price:
                        pbr_yf = price / book
                per = round(float(per_yf), 1) if per_yf and per_yf > 0 else None
                pbr = round(float(pbr_yf), 2) if pbr_yf and pbr_yf > 0 else None
                if per or pbr:
                    source = "yfinance"
            except Exception:
                pass

        rows.append({
            "ticker": ticker,
            "per": round(per, 1) if per else None,
            "pbr": round(pbr, 2) if pbr else None,
            "val_source": source,
        })

    return pd.DataFrame(rows)


@st.cache_data(ttl=21600)
def fetch_market_caps(tickers: list[str]) -> dict[str, float]:
    """Return market cap per ticker (best-effort)."""
    caps: dict[str, float] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            cap = info.get("marketCap")
            if cap:
                caps[t] = float(cap)
        except Exception:
            pass
    return caps
