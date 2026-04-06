"""Sector Dashboard — Streamlit entry point."""

import os
import io
from pathlib import Path
import streamlit as st

# Load credentials: st.secrets (Streamlit Cloud) → .env (local) → env vars
def _load_env():
    # 1. Streamlit Cloud secrets
    for key in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"):
        try:
            if key in st.secrets:
                os.environ.setdefault(key, st.secrets[key])
        except Exception:
            pass
    # 2. Local .env file
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_load_env()
from data.fetcher import SECTORS, PERIOD_OPTIONS, fetch_sector_history, fetch_sector_performance
from data.news import fetch_sector_news
from components.charts import sector_heatmap, performance_bar, price_history, candlestick

st.set_page_config(
    page_title="Sector Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 S&P 500 Sector Dashboard")

# ── Sidebar controls ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    period_label = st.selectbox("Period", list(PERIOD_OPTIONS.keys()), index=1)
    period = PERIOD_OPTIONS[period_label]

    st.divider()
    st.subheader("Telegram Alerts")
    tg_token = st.text_input("Bot Token", value=os.environ.get("TELEGRAM_TOKEN", ""), type="password")
    tg_chat  = st.text_input("Chat ID", value=os.environ.get("TELEGRAM_CHAT_ID", ""))
    alert_threshold = st.slider("Alert threshold (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)

    send_alert = st.button("📤 Send Alert Now")
    send_chart_btn = st.button("📊 Send Chart to Telegram")

    st.divider()
    st.caption("Data via Yahoo Finance (yfinance). Refreshes every 5 min.")
    if st.button("🔄 Force Refresh"):
        fetch_sector_history.clear()
        fetch_sector_performance.clear()
        st.rerun()

# ── Fetch data ───────────────────────────────────────────────────────────────
with st.spinner("Fetching sector data…"):
    df_perf = fetch_sector_performance(period)
    history = fetch_sector_history(period)

if df_perf.empty:
    st.error("Failed to load sector data. Check your internet connection.")
    st.stop()

# ── Telegram: send alert ─────────────────────────────────────────────────────
if send_alert or send_chart_btn:
    if not tg_token or not tg_chat:
        st.sidebar.error("Enter Bot Token and Chat ID first.")
    else:
        os.environ["TELEGRAM_TOKEN"]   = tg_token
        os.environ["TELEGRAM_CHAT_ID"] = tg_chat
        from notifier import notify_sector_moves, send_chart, TELEGRAM_AVAILABLE
        if not TELEGRAM_AVAILABLE:
            st.sidebar.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        else:
            if send_alert:
                with st.spinner("Sending alert…"):
                    try:
                        sent = notify_sector_moves(df_perf, threshold=alert_threshold, period_label=period_label)
                        st.sidebar.success("Alert sent!" if sent else "No sectors crossed threshold — nothing sent.")
                    except Exception as e:
                        st.sidebar.error(f"Failed: {e}")

            if send_chart_btn:
                with st.spinner("Exporting chart…"):
                    try:
                        fig = performance_bar(df_perf)
                        img_bytes = fig.to_image(format="png", width=900, height=500)
                        send_chart(img_bytes, caption=f"Sector Performance ({period_label})")
                        st.sidebar.success("Chart sent!")
                    except Exception as e:
                        st.sidebar.error(f"Failed: {e}")

# ── Overview metrics ─────────────────────────────────────────────────────────
best = df_perf.iloc[0]
worst = df_perf.iloc[-1]
gainers = (df_perf["change_pct"] > 0).sum()
losers = (df_perf["change_pct"] < 0).sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Best Sector", best["name"], f"{best['change_pct']:+.2f}%")
col2.metric("Worst Sector", worst["name"], f"{worst['change_pct']:+.2f}%")
col3.metric("Gainers", gainers)
col4.metric("Losers", losers)

st.divider()

# ── Heatmap + Bar chart ──────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🗺 Heatmap", "📊 Bar Chart"])

with tab1:
    st.plotly_chart(sector_heatmap(df_perf), use_container_width=True)

with tab2:
    st.plotly_chart(performance_bar(df_perf), use_container_width=True)

st.divider()

# ── Price history comparison ──────────────────────────────────────────────────
st.subheader("Price History (Normalized)")
selected_tickers = st.multiselect(
    "Compare sectors",
    options=list(SECTORS.keys()),
    default=["XLK", "XLE", "XLF"],
    format_func=lambda t: f"{t} — {SECTORS[t]}",
)
if selected_tickers:
    st.plotly_chart(price_history(history, selected_tickers), use_container_width=True)

st.divider()

# ── Individual sector detail ──────────────────────────────────────────────────
st.subheader("Sector Detail")
detail_ticker = st.selectbox(
    "Select sector ETF",
    options=list(SECTORS.keys()),
    format_func=lambda t: f"{t} — {SECTORS[t]}",
)
df_detail = history.get(detail_ticker)
if df_detail is not None and not df_detail.empty:
    st.plotly_chart(candlestick(df_detail, detail_ticker), use_container_width=True)

    with st.expander("Raw data"):
        st.dataframe(df_detail.sort_index(ascending=False), use_container_width=True)

st.divider()

# ── Sector News ───────────────────────────────────────────────────────────────
st.subheader("Sector News")
news_tickers = st.multiselect(
    "News for",
    options=list(SECTORS.keys()),
    default=["XLK", "XLE", "XLF", "XLV"],
    format_func=lambda t: f"{t} — {SECTORS[t]}",
    key="news_tickers",
)
if news_tickers:
    with st.spinner("Fetching news…"):
        articles = fetch_sector_news(news_tickers, max_per_ticker=3)

    if not articles:
        st.info("No recent news found.")
    else:
        for a in articles:
            icon = "🔔" if a["high_impact"] else "📰"
            ts = a["published"].strftime("%b %d %H:%M") if a["published"] else ""
            with st.container():
                cols = st.columns([0.05, 0.95])
                cols[0].write(icon)
                cols[1].markdown(
                    f"**[{a['ticker']}]** [{a['title']}]({a['url']})  \n"
                    f"<span style='color:gray;font-size:0.8em'>{a['source']} · {ts}</span>",
                    unsafe_allow_html=True,
                )
