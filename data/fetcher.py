"""
Fetches sector ETF data via yfinance.

SPDR sector ETFs (S&P 500 sectors):
  XLC  - Communication Services
  XLY  - Consumer Discretionary
  XLP  - Consumer Staples
  XLE  - Energy
  XLF  - Financials
  XLV  - Health Care
  XLI  - Industrials
  XLB  - Materials
  XLRE - Real Estate
  XLK  - Technology
  XLU  - Utilities
"""

import yfinance as yf
import pandas as pd
import streamlit as st

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

PERIOD_OPTIONS = {
    "1 Week": "5d",
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "YTD": "ytd",
    "1 Year": "1y",
}


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
    """
    Return a DataFrame with columns:
      ticker, name, current_price, change_pct, volume
    sorted by change_pct descending.
    """
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
            "current_price": round(end_price, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(df["Volume"].iloc[-1]),
        })
    df_perf = pd.DataFrame(rows)
    if not df_perf.empty:
        df_perf = df_perf.sort_values("change_pct", ascending=False).reset_index(drop=True)
    return df_perf
