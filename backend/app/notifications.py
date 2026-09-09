"""Generic webhook notifications -- pipe into ntfy/Discord/Slack/etc. via their own
inbound-webhook adapters. Deliberately not SMTP-specific: a single URL config
covers far more destinations without asking for mail server credentials."""

import logging

import httpx

from app import config

logger = logging.getLogger("haven_backup.notifications")


def notify(event: str, message: str) -> None:
    if not config.NOTIFICATION_WEBHOOK_URL:
        return
    try:
        httpx.post(config.NOTIFICATION_WEBHOOK_URL, json={"event": event, "message": message}, timeout=10)
    except httpx.HTTPError as e:
        logger.warning("Failed to deliver notification webhook: %s", e)
