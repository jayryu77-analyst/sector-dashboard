# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Streamlit dashboard tracking S&P 500 sector ETFs (SPDR XL* series) with yfinance for live market data, Telegram bot alerts, and a standalone monitoring script.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard
streamlit run app.py

# Run standalone monitor (sends Telegram alert + chart + news)
python monitor.py
```

## Architecture

```
app.py              # Streamlit UI — all page layout lives here
data/
  fetcher.py        # yfinance calls + @st.cache_data wrappers; defines SECTORS dict and PERIOD_OPTIONS
  news.py           # yfinance .news fetch + keyword-based high-impact filtering
components/
  charts.py         # Pure Plotly figure builders — no Streamlit calls, no side effects
notifier.py         # Telegram send helpers (text alerts + photo); reads TELEGRAM_TOKEN / TELEGRAM_CHAT_ID env vars
monitor.py          # Standalone script: fetch → alert → send chart image → send news
requirements.txt
```

**Data flow:**
- `app.py` calls `fetch_sector_performance()` / `fetch_sector_history()` → passes results to chart builders → renders with `st.plotly_chart()`
- `monitor.py` calls the same fetch functions, then `notifier.py` helpers to push to Telegram
- Both paths are independent; `monitor.py` is meant to be scheduled (cron / Task Scheduler)

**Caching:** `@st.cache_data(ttl=300)` on all fetch functions (5-min TTL). Force-cleared by the sidebar "🔄 Force Refresh" button in `app.py`, or naturally bypassed when called from `monitor.py` (no Streamlit session).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | For alerts | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | For alerts | Channel/group/user ID (e.g. `@mychannel` or numeric) |
| `ALERT_THRESHOLD` | Optional | % move to trigger alert, default `2.0` |
| `ALERT_PERIOD` | Optional | yfinance period string, default `1d` |
| `SEND_ALWAYS` | Optional | Set `1` to send even when no threshold crossed |

The dashboard also lets users enter Token/Chat ID in the sidebar (stored only in session state, not persisted).

## Key Constants

- `SECTORS` in [data/fetcher.py](data/fetcher.py) — maps ticker → full sector name (11 SPDR ETFs)
- `PERIOD_OPTIONS` in [data/fetcher.py](data/fetcher.py) — maps UI labels to yfinance period strings
- `HIGH_IMPACT_KEYWORDS` in [data/news.py](data/news.py) — keywords that flag news as high-impact

## Extending the Dashboard

- **New chart:** add a builder function in `components/charts.py` (returns `go.Figure`), call it in `app.py`
- **New data source:** add a `@st.cache_data`-decorated function in `data/fetcher.py`
- **Multi-page app:** create a `pages/` directory; each `pages/N_Name.py` becomes a nav item automatically
- **Chart to image (for Telegram):** use `fig.to_image(format="png")` — requires `kaleido` package
