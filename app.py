"""Sector Dashboard — Streamlit entry point."""

import os
from datetime import datetime, timedelta
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
    # Load local secrets first, then fall back to .env
    for _name in (".env.local", ".env"):
        _env_path = Path(__file__).parent / _name
        if _env_path.exists():
            # Try UTF-8 first (most common), then fall back to CP949 for Windows KR locales.
            try:
                env_text = _env_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                env_text = _env_path.read_text(encoding="cp949")
            for line in env_text.splitlines():
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
    fetch_market_caps,
)
from data.news import fetch_sector_news, fetch_all_sector_news, format_articles_for_telegram
from data.news_multi import fetch_all_sources_for_sector
from components.charts import sector_heatmap, performance_bar, price_history, candlestick

st.set_page_config(page_title="Sector Dashboard", page_icon="📊", layout="wide")


def _render_news_selectable(
    articles: list,
    name_map: dict | None = None,
    section_key: str = "news",
) -> list[dict]:
    """
    Render articles with checkboxes. Returns the list of selected articles.
    All articles shown are already filtered to last 24 hours.
    """
    if not articles:
        st.info("No news in the last 24 hours.")
        return []

    st.caption(f"{len(articles)} article(s) from the last 24 hours — check to add to Telegram")
    selected = []
    for i, a in enumerate(articles):
        icon = "🔔" if a["high_impact"] else "📰"
        ts    = a["published"].strftime("%b %d %H:%M") if a["published"] else ""
        label = (name_map or {}).get(a["ticker"], a["ticker"])
        text  = (
            f"{icon} **[{label}]** [{a['title']}]({a['url']})  \n"
            f"<span style='color:gray;font-size:0.8em'>{a['source']} · {ts}</span>"
        )
        col_cb, col_txt = st.columns([0.04, 0.96])
        checked = col_cb.checkbox("", key=f"{section_key}_{i}", label_visibility="collapsed")
        col_txt.markdown(text, unsafe_allow_html=True)
        if checked:
            selected.append(a)
    return selected


st.title("📊 Sector Dashboard")

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    market = st.radio("Market", ["🇺🇸 US (S&P 500)", "🇰🇷 Korea (KRX)"], horizontal=True, index=1)
    is_korea = market.startswith("🇰🇷")

    period_label = st.selectbox("Period", list(PERIOD_OPTIONS.keys()), index=0)
    period = PERIOD_OPTIONS[period_label]

    st.divider()
    st.subheader("Telegram Alerts")
    _tg_ready = bool(os.environ.get("TELEGRAM_TOKEN")) and bool(os.environ.get("TELEGRAM_CHAT_ID"))
    if _tg_ready:
        st.success("Credentials loaded from .env ✓", icon="🔒")
    else:
        st.warning("No credentials found. Add them to your `.env` file.", icon="⚠️")
    alert_threshold  = st.slider("Alert threshold (%)", 0.5, 10.0, 2.0, 0.5)
    send_alert_btn   = st.button("📤 Send Alert Now",          disabled=not _tg_ready)
    send_chart_btn   = st.button("📊 Send Chart to Telegram",  disabled=not _tg_ready)
    send_sel_news_btn = st.button("📩 Send Selected News",     disabled=not _tg_ready)

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
        missing = [t for t in KR_TICKER_NAME.keys() if t not in history]
        if missing:
            st.warning(f"Missing KR data for {len(missing)} tickers.")

else:
    with st.spinner("Fetching US market data…"):
        df_perf = fetch_sector_performance(period)
        history = fetch_sector_history(period)

if df_perf.empty:
    st.error("Failed to load market data. Check your internet connection.")
    st.stop()

# ── Session state: collect selected news across sections ──────────────────
if "selected_news" not in st.session_state:
    st.session_state["selected_news"] = []

# ── Telegram actions ───────────────────────────────────────────────────────
if send_alert_btn or send_chart_btn or send_sel_news_btn:
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
                    _tickers = df_perf["ticker"].tolist()
                    caps = fetch_market_caps(_tickers)
                    df_for_heat = df_perf.copy()
                    df_for_heat["market_cap"] = df_for_heat["ticker"].map(caps)
                    fig = sector_heatmap(df_for_heat, group_by_sector=is_korea, size_col="market_cap")
                    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
                    img_bytes = fig.to_image(format="png", width=1200, height=800)
                    send_chart(img_bytes, caption=f"{'Korea' if is_korea else 'US'} Heatmap ({period_label})")
                    st.sidebar.success("Chart sent!")
                except Exception as e:
                    st.sidebar.error(f"Failed: {e}")

        if send_sel_news_btn:
            selected = st.session_state.get("selected_news", [])
            if not selected:
                st.sidebar.warning("No articles selected. Check boxes next to articles first.")
            else:
                with st.spinner(f"Sending {len(selected)} article(s)…"):
                    try:
                        name_map = KR_TICKER_NAME if is_korea else None
                        msg = format_articles_for_telegram(selected, name_map=name_map)
                        send_text(msg)
                        st.sidebar.success(f"Sent {len(selected)} article(s)!")
                        st.session_state["selected_news"] = []
                    except Exception as e:
                        st.sidebar.error(f"Failed: {e}")

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
    st.subheader("Sector News (last 24h)")
    news_tickers = st.multiselect(
        "News for",
        options=list(SECTORS.keys()),
        default=["XLK", "XLE", "XLF", "XLV"],
        format_func=lambda t: f"{t} — {SECTORS[t]}",
        key="us_news_tickers",
    )
    if news_tickers:
        with st.spinner("Fetching news…"):
            articles = fetch_sector_news(news_tickers, max_per_ticker=5)
        sel = _render_news_selectable(articles, section_key="us_news")
        st.session_state["selected_news"] = sel

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
    with st.spinner("Fetching valuation data??"):
        df_val = fetch_kr_valuation()

    df_combined = df_perf.merge(df_val, on="ticker", how="left")
    # Compare valuation ratios using start vs current price basis.
    price_ratio = df_combined["start_price"] / df_combined["current_price"]
    df_combined["per_start"] = df_combined["per"] * price_ratio
    df_combined["pbr_start"] = df_combined["pbr"] * price_ratio

    df_display = df_combined[
        ["sector", "name", "ticker", "start_price", "current_price", "change_pct", "per_start", "per", "pbr_start", "pbr", "val_source"]
    ].copy()
    df_display.columns = [
        "Sector", "Name", "Ticker", "Price (Start)", "Price (Now)", "Change %",
        "PER (Start)", "PER (Now)", "PBR (Start)", "PBR (Now)", "Source",
    ]

    def _color_change(val):
        if isinstance(val, float):
            color = "#1a9850" if val > 0 else ("#d73027" if val < 0 else "")
            return f"color: {color}"
        return ""

    styler = df_display.style
    if hasattr(styler, "map"):
        styler = styler.map(_color_change, subset=["Change %"])
    else:
        styler = styler.applymap(_color_change, subset=["Change %"])

    st.dataframe(
        styler.format({
            "Price (Start)": "{:,.0f}",
            "Price (Now)": "{:,.0f}",
            "Change %": "{:+.2f}%",
            "PER (Start)": lambda x: f"{x:.1f}" if x is not None and x == x else "N/A",
            "PER (Now)": lambda x: f"{x:.1f}" if x is not None and x == x else "N/A",
            "PBR (Start)": lambda x: f"{x:.2f}" if x is not None and x == x else "N/A",
            "PBR (Now)": lambda x: f"{x:.2f}" if x is not None and x == x else "N/A",
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.divider()

    # Korean stock news — multi-source, last 24h
    st.subheader("Korean Stock News (last 24h)")
    st.caption("Multi-source: Naver News + yfinance + NewsAPI + NewsData.io. Transport & Holdings sectors with extended Korean keywords.")

    all_selected: list[dict] = []

    with st.spinner("Fetching news from multiple sources…"):
        # Combine: yfinance + NewsAPI + NewsData.io
        transport_articles = fetch_all_sources_for_sector("transport", ticker_names=KR_STOCKS["Transport"])
        holdings_articles = fetch_all_sources_for_sector("holdings", ticker_names=KR_STOCKS["Holdings"])

    with st.expander(f"📂 Transport ({len(transport_articles)} articles)", expanded=True):
        sel = _render_news_selectable(transport_articles, name_map=KR_TICKER_NAME, section_key="kr_transport")
        all_selected.extend(sel)

    with st.expander(f"📂 Holdings ({len(holdings_articles)} articles)", expanded=True):
        sel = _render_news_selectable(holdings_articles, name_map=KR_TICKER_NAME, section_key="kr_holdings")
        all_selected.extend(sel)

    st.session_state["selected_news"] = all_selected
    if all_selected:
        st.success(f"{len(all_selected)} article(s) selected — click **📩 Send Selected News** in the sidebar.")
