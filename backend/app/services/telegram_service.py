"""Telegram Notification Service for Feedback, Community Alerts, and Beta Bug Reporting.

Sends formatted markdown alerts to Telegram groups/channels when configured.
Safe fallback: if tokens are missing, logs without raising exceptions.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
import httpx

logger = logging.getLogger("app.services.telegram")

# Environment / settings
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_FEEDBACK_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_FEEDBACK_CHAT_ID", "")

# Default community links for public beta
DEFAULT_TELEGRAM_CHANNEL_URL = os.environ.get("TELEGRAM_CHANNEL_URL", "https://t.me/TradingLabsOfficial")
DEFAULT_TELEGRAM_GROUP_URL = os.environ.get("TELEGRAM_GROUP_URL", "https://t.me/TradingLabsDiscussion")


async def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
) -> bool:
    """Send a message to a Telegram chat/group via Bot API.

    Returns True if sent successfully, False otherwise.
    """
    token = TELEGRAM_BOT_TOKEN.strip()
    target_chat = (chat_id or TELEGRAM_CHAT_ID).strip()

    if not token or not target_chat:
        logger.debug("Telegram credentials not configured; message not sent: %s", text[:80])
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info("Telegram notification sent successfully to chat %s", target_chat)
                return True
            else:
                logger.warning("Telegram API error (%s): %s", resp.status_code, resp.text[:200])
                return False
    except Exception as exc:
        logger.warning("Failed to send Telegram message: %s", exc)
        return False


def format_feedback_for_telegram(feedback: dict[str, Any]) -> str:
    """Format feedback entry as clean HTML for Telegram."""
    category = (feedback.get("category") or "other").upper().replace("_", " ")
    page = feedback.get("page_or_feature") or "Unknown Page"
    msg = feedback.get("message") or "No message provided."
    contact = feedback.get("contact_method") or "Not provided"
    feedback_id = feedback.get("id", "N/A")
    has_screenshot = "Yes" if feedback.get("screenshot") else "No"

    # HTML formatted for Telegram
    return (
        f"🚨 <b>Trading Labs Beta Feedback</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>ID:</b> <code>{feedback_id}</code>\n"
        f"<b>Category:</b> {category}\n"
        f"<b>Page / Feature:</b> {page}\n"
        f"<b>Contact:</b> {contact}\n"
        f"<b>Screenshot:</b> {has_screenshot}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Message:</b>\n"
        f"{msg}\n"
    )
