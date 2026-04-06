"""
Standalone sector monitoring script.

Runs once (or on a schedule via cron/Task Scheduler) and:
  1. Checks if any sector moved beyond ALERT_THRESHOLD %
  2. Sends a Telegram text alert with movers
  3. Sends the performance bar chart as a PNG image
  4. Sends top sector news headlines (high-impact items first)

Required environment variables:
  TELEGRAM_TOKEN    — from @BotFather
  TELEGRAM_CHAT_ID  — channel/group/user chat ID

Optional environment variables:
  ALERT_THRESHOLD   — % move to trigger an alert (default: 2.0)
  ALERT_PERIOD      — yfinance period string (default: 1d)
  SEND_ALWAYS       — set to "1" to send even if no threshold is crossed

Usage:
  python monitor.py

  # Windows Task Scheduler: run every 30 min during market hours
  # Linux/macOS cron (every 30 min, Mon-Fri 9:30–16:00 ET):
  #   */30 13-20 * * 1-5 cd /path/to/project && python monitor.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Auto-load .env if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from data.fetcher import fetch_sector_performance, fetch_sector_history, SECTORS, PERIOD_OPTIONS
from data.news import fetch_sector_news, format_news_for_telegram
from components.charts import performance_bar
from notifier import notify_sector_moves, send_chart, TELEGRAM_AVAILABLE

ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "2.0"))
ALERT_PERIOD    = os.environ.get("ALERT_PERIOD", "1d")
SEND_ALWAYS     = os.environ.get("SEND_ALWAYS", "0") == "1"

_PERIOD_LABEL = {v: k for k, v in PERIOD_OPTIONS.items()}
_PERIOD_LABEL["1d"] = "1 Day"


def main() -> None:
    if not TELEGRAM_AVAILABLE:
        print("ERROR: python-telegram-bot not installed. Run: pip install python-telegram-bot")
        sys.exit(1)

    period_label = _PERIOD_LABEL.get(ALERT_PERIOD, ALERT_PERIOD)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{ts}] Fetching sector data (period={ALERT_PERIOD})…")

    df_perf = fetch_sector_performance(ALERT_PERIOD)
    if df_perf.empty:
        print("No data returned. Check internet connection.")
        sys.exit(1)

    movers = df_perf[df_perf["change_pct"].abs() >= ALERT_THRESHOLD]
    should_send = SEND_ALWAYS or not movers.empty

    if not should_send:
        print(f"No sectors crossed ±{ALERT_THRESHOLD}%. Nothing sent.")
        return

    print(f"Threshold ±{ALERT_THRESHOLD}% — {len(movers)} mover(s):")
    for _, row in movers.iterrows():
        print(f"  {row['ticker']:5s} {row['change_pct']:+.2f}%  {row['name']}")

    # 1. Send text alert
    sent = notify_sector_moves(df_perf, threshold=ALERT_THRESHOLD, period_label=period_label)
    if sent:
        print("Text alert sent.")
    elif SEND_ALWAYS:
        print("(SEND_ALWAYS=1) No movers to alert but continuing.")

    # 2. Send performance bar chart as image
    try:
        history = fetch_sector_history(ALERT_PERIOD)
        fig = performance_bar(df_perf)
        img_bytes = fig.to_image(format="png", width=900, height=500)
        send_chart(img_bytes, caption=f"Sector Performance — {period_label} ({ts})")
        print("Chart image sent.")
    except Exception as e:
        print(f"Chart send failed: {e}")

    # 3. Send top news (high-impact items, top 4 sectors by move)
    top_tickers = df_perf["ticker"].head(4).tolist()
    articles = fetch_sector_news(top_tickers, max_per_ticker=2)
    news_msg = format_news_for_telegram(articles, limit=6)
    if news_msg:
        try:
            import asyncio
            from notifier import _send_text
            asyncio.run(_send_text(news_msg))
            print("News headlines sent.")
        except Exception as e:
            print(f"News send failed: {e}")


if __name__ == "__main__":
    main()
