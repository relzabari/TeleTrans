from datetime import datetime
from zoneinfo import ZoneInfo

ISRAEL_TIMEZONE = ZoneInfo("Asia/Jerusalem")


def israel_now() -> str:
    return datetime.now(ISRAEL_TIMEZONE).isoformat()
