"""
Telegram notification module.

Uses a dedicated thread+event-loop to avoid conflicts with
Streamlit's own asyncio event loop.
"""

import os
import asyncio
import threading
import pandas as pd

try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


def _run_coroutine(coro):
    """Run an async coroutine safely from any context (including Streamlit)."""
    result = [None]
    exc = [None]

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result[0] = loop.run_until_complete(coro)
        except Exception as e:
            exc[0] = e
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=30)
    if exc[0]:
        raise exc[0]
    return result[0]


def _get_credentials():
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise ValueError("TELEGRAM_TOKEN is not set.")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is not set.")
    return token, chat_id


async def _async_send_text(token: str, chat_id: str, message: str) -> None:
    async with Bot(token=token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown",
        )


async def _async_send_photo(token: str, chat_id: str, image_bytes: bytes, caption: str) -> None:
    import io
    async with Bot(token=token) as bot:
        await bot.send_photo(
            chat_id=chat_id,
            photo=io.BytesIO(image_bytes),
            caption=caption,
        )


def send_text(message: str) -> None:
    """Send a plain text / Markdown message to Telegram."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot not installed.")
    token, chat_id = _get_credentials()
    _run_coroutine(_async_send_text(token, chat_id, message))


def send_chart(image_bytes: bytes, caption: str = "Sector Dashboard Chart") -> None:
    """Send a PNG image to Telegram."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot not installed.")
    token, chat_id = _get_credentials()
    _run_coroutine(_async_send_photo(token, chat_id, image_bytes, caption))


def _build_alert_message(df_perf: pd.DataFrame, threshold: float, period_label: str) -> str | None:
    movers = df_perf[df_perf["change_pct"].abs() >= threshold]
    if movers.empty:
        return None

    gainers = movers[movers["change_pct"] > 0].sort_values("change_pct", ascending=False)
    losers  = movers[movers["change_pct"] < 0].sort_values("change_pct")

    lines = [f"📊 *Sector Alert* — {period_label}\n"]
    if not gainers.empty:
        lines.append("🟢 *Top Gainers*")
        for _, row in gainers.iterrows():
            name = row.get("name", row["ticker"])
            lines.append(f"  {row['ticker']} ({name}): *+{row['change_pct']:.2f}%*")
    if not losers.empty:
        lines.append("\n🔴 *Top Losers*")
        for _, row in losers.iterrows():
            name = row.get("name", row["ticker"])
            lines.append(f"  {row['ticker']} ({name}): *{row['change_pct']:.2f}%*")
    return "\n".join(lines)


def notify_sector_moves(
    df_perf: pd.DataFrame,
    threshold: float = 2.0,
    period_label: str = "1 Month",
) -> bool:
    """Send alert if any row in df_perf has |change_pct| >= threshold. Returns True if sent."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot not installed.")
    message = _build_alert_message(df_perf, threshold, period_label)
    if message is None:
        return False
    send_text(message)
    return True
