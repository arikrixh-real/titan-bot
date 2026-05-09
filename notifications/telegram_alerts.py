"""
Legacy Telegram compatibility wrapper.

All Telegram sends must go through alerts.telegram_alert so the shared
3-alert/day cap and duplicate-message protection remain enforced.
"""

from alerts.telegram_alert import get_daily_alert_status, send_telegram_message


__all__ = ["send_telegram_message", "get_daily_alert_status"]
