"""Thin Telegram notification helper — best-effort outbound alerts.

Sends a message to Stefano's personal chat via the Telegram Bot API using
``httpx`` (already pinned in pyproject — no new dependency). Reads the bot
token and chat id from the environment; when either is absent the call is a
no-op so callers (e.g. the apply route) never fail because of a missing alert.

Security: T-03-SC — secrets are never logged. The bot token and chat id are
read from env and used only in the request; structlog events log the event
name and HTTP status only, never the token, chat id, or message text.
"""

import os
from typing import Final

import httpx
import structlog

log = structlog.get_logger()

_TELEGRAM_TIMEOUT: Final[float] = 10.0


async def send_telegram(text: str) -> None:
    """Send a Telegram message, best-effort (never raises).

    When ``TELEGRAM_BOT_TOKEN`` or ``TELEGRAM_CHAT_ID`` is unset/empty, logs a
    warning and returns without sending. On send, POSTs to the Bot API and logs
    success/failure by HTTP status. All exceptions are swallowed — notification
    failure must not break the calling request (T-03-05-05).

    Args:
        text: Message body. Sent with ``parse_mode=HTML``.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log.warning("telegram_env_missing")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    try:
        async with httpx.AsyncClient(timeout=_TELEGRAM_TIMEOUT) as client:
            resp = await client.post(url, json=body)
        if 200 <= resp.status_code < 300:
            log.info("telegram_sent")
        else:
            log.warning("telegram_send_failed", status_code=resp.status_code)
    except Exception:
        # Best-effort — swallow all errors (timeouts, DNS, connection resets).
        log.warning("telegram_send_failed", status_code=None)
