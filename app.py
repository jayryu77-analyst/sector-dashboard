"""Sector Dashboard — Streamlit entry point."""

import os
from pathlib import Path
import streamlit as st

# Load credentials: st.secrets (Streamlit Cloud) → .env file → env vars
def _load_env():
    for key in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        try:
            if key in st.secrets:
                os.environ.setdefault(key, st.secrets[key])
        except Exception:
            pass
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

from data.fetcher import (
    SECTORS, PERIOD_OPTIONS,
    KR_STOCKS, KR_TICKER_NAME, KR_TICKER_SECTOR,
    fetch_sector_history, fetch_sector_performance,
    fetch_kr_history, fetch_kr_performance, fetch_kr_valuation,
)
from data.news import fetch_sector_news
from components.charts import sector_heatmap, performance_bar, price_history, candlestick

st.set_page_config(page_title="Sector Dashboard", page_icon="📊", layout="wide")


def _render_news(articles: list, name_map: dict | None = None):
    if not articles:
        st.info("No recent news found.")
        return
    for a in articles:
        icon = "🔔" if a["high_impact"] else "📰"
        ts   = a["published"].strftime("%b %d %H:%M") if a["published"] else ""
        label = name_map.get(a["ticker"], a["ticker"]) if name_map else a["ticker"]
        with st.container():
            cols = st.columns([0.05, 0.95])
            cols[0].write(icon)
            cols[1].markdown(
                f"**[{label}]** [{a['title']}]({a['url']})  \n"
                f"<span style='color:gray;font-size:0.8em'>{a['source']} · {ts}</span>",
                unsafe_allow_html=True,
            )


st.title("📊 Sector Dashboard")

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    market = st.radio("Market", ["🇺🇸 US (S&P 500)", "🇰🇷 Korea (KRX)"], horizontal=True)
    is_korea = market.startswith("🇰🇷")

    period_label = st.selectbox("Period", list(PERIOD_OPTIONS.keys()), index=1)
    period = PERIOD_OPTIONS[period_label]

    st.divider()
    st.subheader("Telegram Alerts")
    tg_token = st.text_input("Bot Token", value=os.environ.get("TELEGRAM_TOKEN", ""), type="password")
    tg_chat  = st.text_input("Chat ID",   value=os.environ.get("TELEGRAM_CHAT_ID", ""))
    alert_threshold = st.slider("Alert threshold (%)", 0.5, 10.0, 2.0, 0.5)
    send_alert_btn  = st.button("📤 Send Alert Now")
    send_chart_btn  = st.button("📊 Send Chart to Telegram")

    st.divider()
    st.caption("Data via Yahoo Finance. Refreshes every 5 min.")
    if st.button("🔄 Force Refresh"):
        fetch_sector_history.clear()
        fetch_sector_performance.clear()
        fetch_kr_history.clear()
        fetch_kr_performance.clear()
        fetch_kr_valuation.clear()
        st.rerun()

# ── Fetch data ─────────────────────────────────────────────────────────────
if is_korea:
    with st.spinner("Fetching Korean market data…"):
        df_perf = fetch_kr_performance(period)
        history = fetch_kr_history(period)
else:
    with st.spinner("Fetching US market data…"):
        df_perf = fetch_sector_performance(period)
        history = fetch_sector_history(period)

if df_perf.empty:
    st.error("Failed to load market data. Check your internet connection.")
    st.stop()

# ── Telegram actions ───────────────────────────────────────────────────────
if send_alert_btn or send_chart_btn:
    if not tg_token or not tg_chat:
        st.sidebar.error("Enter Bot Token and Chat ID first.")
    else:
        os.environ["TELEGRAM_TOKEN"]   = tg_token
        os.environ["TELEGRAM_CHAT_ID"] = tg_chat
        from notifier import notify_sector_moves, send_chart, send_text, TELEGRAM_AVAILABLE
        if not TELEGRAM_AVAILABLE:
            st.sidebar.error("python-telegram-bot not installed.")
        else:
            if send_alert_btn:
                with st.spinner("Sending alert…"):
                    try:
                        sent = notify_sector_moves(df_perf, threshold=alert_threshold, period_label=period_label)
                        st.sidebar.success("Alert sent!" if sent else "No sectors crossed threshold.")
                    except Exception as e:
                        st.sidebar.error(f"Failed: {e}")

            if send_chart_btn:
                with st.spinner("Exporting + sending chart…"):
                    try:
                        fig = performance_bar(df_perf)
                        img_bytes = fig.to_image(format="png", width=900, height=500)
                        send_chart(img_bytes, caption=f"{'Korea' if is_korea else 'US'} Sector Performance ({period_label})")
                        st.sidebar.success("Chart sent!")
                    except Exception as e:
                        st.sidebar.error(f"Failed: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# US MARKET VIEW
# ══════════════════════════════════════════════════════════════════════════════
if not is_korea:
    best  = df_perf.iloc[0]
    worst = df_perf.iloc[-1]
    gainers = (df_perf["change_pct"] > 0).sum()
    losers  = (df_perf["change_pct"] < 0).sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Best Sector",  best["name"],  f"{best['change_pct']:+.2f}%")
    c2.metric("Worst Sector", worst["name"], f"{worst['change_pct']:+.2f}%")
    c3.metric("Gainers", gainers)
    c4.metric("Losers",  losers)
    st.divider()

    # Heatmap / Bar
    tab1, tab2 = st.tabs(["🗺 Heatmap", "📊 Bar Chart"])
    with tab1:
        st.plotly_chart(sector_heatmap(df_perf), use_container_width=True)
    with tab2:
        st.plotly_chart(performance_bar(df_perf), use_container_width=True)
    st.divider()

    # Sector detail (candlestick)
    st.subheader("Sector Detail")
    detail_ticker = st.selectbox(
        "Select sector ETF",
        options=list(SECTORS.keys()),
        format_func=lambda t: f"{t} — {SECTORS[t]}",
    )
    df_detail = history.get(detail_ticker)
    if df_detail is not None and not df_detail.empty:
        st.plotly_chart(candlestick(df_detail, detail_ticker, SECTORS[detail_ticker]), use_container_width=True)
        with st.expander("Raw data"):
            st.dataframe(df_detail.sort_index(ascending=False), use_container_width=True)
    st.divider()

    # Price history (moved below detail)
    st.subheader("Price History (Normalized)")
    selected = st.multiselect(
        "Compare sectors",
        options=list(SECTORS.keys()),
        default=["XLK", "XLE", "XLF"],
        format_func=lambda t: f"{t} — {SECTORS[t]}",
    )
    if selected:
        st.plotly_chart(price_history(history, selected, SECTORS), use_container_width=True)
    st.divider()

    # News
    st.subheader("Sector News")
    news_tickers = st.multiselect(
        "News for",
        options=list(SECTORS.keys()),
        default=["XLK", "XLE", "XLF", "XLV"],
        format_func=lambda t: f"{t} — {SECTORS[t]}",
        key="us_news_tickers",
    )
    if news_tickers:
        with st.spinner("Fetching news…"):
            articles = fetch_sector_news(news_tickers, max_per_ticker=3)
        _render_news(articles)

# ══════════════════════════════════════════════════════════════════════════════
# KOREA MARKET VIEW
# ══════════════════════════════════════════════════════════════════════════════
else:
    transport = df_perf[df_perf["sector"] == "Transport"]
    holdings  = df_perf[df_perf["sector"] == "Holdings"]

    # Summary metrics
    best_t  = transport.iloc[0] if not transport.empty else None
    best_h  = holdings.iloc[0]  if not holdings.empty  else None
    gainers = (df_perf["change_pct"] > 0).sum()
    losers  = (df_perf["change_pct"] < 0).sum()

    c1, c2, c3, c4 = st.columns(4)
    if best_t is not None:
        c1.metric("Best Transport", best_t["name"], f"{best_t['change_pct']:+.2f}%")
    if best_h is not None:
        c2.metric("Best Holdings", best_h["name"], f"{best_h['change_pct']:+.2f}%")
    c3.metric("Gainers", gainers)
    c4.metric("Losers",  losers)
    st.divider()

    # Heatmap / Bar (grouped by sector)
    tab1, tab2 = st.tabs(["🗺 Heatmap", "📊 Bar Chart"])
    with tab1:
        st.plotly_chart(sector_heatmap(df_perf, group_by_sector=True), use_container_width=True)
    with tab2:
        st.plotly_chart(performance_bar(df_perf), use_container_width=True)
    st.divider()

    # Individual stock candlestick
    st.subheader("Stock Detail")
    all_kr_tickers = list(KR_TICKER_NAME.keys())
    detail_kr = st.selectbox(
        "Select stock",
        options=all_kr_tickers,
        format_func=lambda t: f"{KR_TICKER_NAME[t]} ({t}) — {KR_TICKER_SECTOR[t]}",
    )
    df_kr_detail = history.get(detail_kr)
    if df_kr_detail is not None and not df_kr_detail.empty:
        st.plotly_chart(candlestick(df_kr_detail, detail_kr, KR_TICKER_NAME[detail_kr]), use_container_width=True)
        with st.expander("Raw data"):
            st.dataframe(df_kr_detail.sort_index(ascending=False), use_container_width=True)
    st.divider()

    # Price history
    st.subheader("Price History (Normalized)")
    kr_selected = st.multiselect(
        "Compare stocks",
        options=all_kr_tickers,
        default=["003490.KS", "011200.KS", "034730.KS"],
        format_func=lambda t: f"{KR_TICKER_NAME[t]} ({t})",
    )
    if kr_selected:
        st.plotly_chart(price_history(history, kr_selected, KR_TICKER_NAME), use_container_width=True)
    st.divider()

    # Valuation table (PER / PBR)
    st.subheader("Valuation — PER / PBR")
    with st.spinner("Fetching valuation data…"):
        df_val = fetch_kr_valuation()

    df_combined = df_perf.merge(df_val, on="ticker", how="left")
    df_display = df_combined[["sector", "name", "ticker", "current_price", "change_pct", "per", "pbr"]].copy()
    df_display.columns = ["Sector", "Name", "Ticker", "Price (KRW)", "Change %", "PER", "PBR"]

    def _color_change(val):
        if isinstance(val, float):
            color = "#1a9850" if val > 0 else ("#d73027" if val < 0 else "")
            return f"color: {color}"
        return ""

    st.dataframe(
        df_display.style.applymap(_color_change, subset=["Change %"]).format({
            "Price (KRW)": "{:,.0f}",
            "Change %": "{:+.2f}%",
            "PER": lambda x: f"{x:.1f}" if x == x else "N/A",
            "PBR": lambda x: f"{x:.2f}" if x == x else "N/A",
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.divider()

    # Korean stock news
    st.subheader("Korean Stock News")
    kr_news_tickers = st.multiselect(
        "News for",
        options=all_kr_tickers,
        default=["003490.KS", "011200.KS", "034730.KS", "028260.KS"],
        format_func=lambda t: f"{KR_TICKER_NAME[t]} ({t})",
        key="kr_news_tickers",
    )
    if kr_news_tickers:
        with st.spinner("Fetching news…"):
            articles = fetch_sector_news(kr_news_tickers, max_per_ticker=3)
        _render_news(articles, name_map=KR_TICKER_NAME)

