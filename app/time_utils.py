from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ISRAEL_TIMEZONE = ZoneInfo("Asia/Jerusalem")


def israel_now() -> str:
    return datetime.now(ISRAEL_TIMEZONE).isoformat()


def format_israel_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(ISRAEL_TIMEZONE).strftime("%d/%m/%Y %H:%M")
