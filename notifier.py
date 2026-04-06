"""
Telegram notification module.

Set these in your environment (or a .env file):
  TELEGRAM_TOKEN  — bot token from @BotFather
  TELEGRAM_CHAT_ID — channel/chat ID, e.g. @your_channel or a numeric ID

Usage:
  from notifier import notify_sector_moves
  await notify_sector_moves(df_perf, threshold=2.0)
"""

import os
import asyncio
import pandas as pd

try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


def _get_bot() -> "Bot":
    token = os.environ.get("TELEGRAM_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable not set.")
    return Bot(token=token)


def _get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID environment variable not set.")
    return chat_id


def _build_alert_message(df_perf: pd.DataFrame, threshold: float, period_label: str) -> str | None:
    """Build a Telegram message for sectors that moved beyond the threshold.
    Returns None if nothing crossed the threshold."""
    movers = df_perf[df_perf["change_pct"].abs() >= threshold]
    if movers.empty:
        return None

    gainers = movers[movers["change_pct"] > 0].sort_values("change_pct", ascending=False)
    losers  = movers[movers["change_pct"] < 0].sort_values("change_pct")

    lines = [f"📊 *Sector Alert* — {period_label}\n"]

    if not gainers.empty:
        lines.append("🟢 *Top Gainers*")
        for _, row in gainers.iterrows():
            lines.append(f"  {row['ticker']} ({row['name']}): *+{row['change_pct']:.2f}%* @ ${row['current_price']:.2f}")

    if not losers.empty:
        lines.append("\n🔴 *Top Losers*")
        for _, row in losers.iterrows():
            lines.append(f"  {row['ticker']} ({row['name']}): *{row['change_pct']:.2f}%* @ ${row['current_price']:.2f}")

    return "\n".join(lines)


async def _send_text(message: str) -> None:
    bot = _get_bot()
    chat_id = _get_chat_id()
    async with bot:
        await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")


async def _send_photo(image_bytes: bytes, caption: str = "") -> None:
    bot = _get_bot()
    chat_id = _get_chat_id()
    async with bot:
        await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=caption)


def notify_sector_moves(
    df_perf: pd.DataFrame,
    threshold: float = 2.0,
    period_label: str = "1 Month",
) -> bool:
    """
    Send a Telegram alert if any sector moved beyond `threshold` %.
    Returns True if a message was sent, False otherwise.
    Raises ValueError if env vars are missing.
    Raises RuntimeError if Telegram package is not installed.
    """
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot is not installed. Run: pip install python-telegram-bot")

    message = _build_alert_message(df_perf, threshold, period_label)
    if message is None:
        return False

    asyncio.run(_send_text(message))
    return True


def send_chart(image_bytes: bytes, caption: str = "Sector Dashboard Chart") -> None:
    """Send a chart image (PNG bytes) to Telegram."""
    if not TELEGRAM_AVAILABLE:
        raise RuntimeError("python-telegram-bot is not installed. Run: pip install python-telegram-bot")
    asyncio.run(_send_photo(image_bytes, caption))
