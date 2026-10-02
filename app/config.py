from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass
class BotConfig:
    source_channels: list[str]
    destination: str | int
    api_id: int
    api_hash: str
    phone: str
    telegram_session: str | None
    session_path: Path
    checkpoint_path: Path
    supabase_url: str | None
    supabase_key: str | None
    important_destination: str | int | Any | None = None
    important_keywords: list[str] = field(default_factory=list)
    backfill_days: int = 2


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _get_required_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not str(value).strip():
        raise RuntimeError(f"Missing environment variable: {key}")
    return str(value).strip()


def _get_nonnegative_int_env(key: str, default: int) -> int:
    raw_value = os.getenv(key)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {key} must be an integer") from exc
    if value < 0:
        raise RuntimeError(f"Environment variable {key} must be zero or greater")
    return value


def _resolve_config_path(root: Path) -> Path:
    for candidate in (root / "data" / "config.json", root / "config.json"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No configuration file found")


def _resolve_session_path(root: Path) -> Path:
    data_session = root / "data" / "sessions" / "telegram"
    legacy_session = root / "session" / "session"

    if legacy_session.exists() or legacy_session.with_suffix(".session").exists():
        return legacy_session
    return data_session


def load_config() -> BotConfig:
    root = get_project_root()
    load_dotenv(root / ".env")

    config_path = _resolve_config_path(root)
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = json.load(handle)

    session_path = _resolve_session_path(root)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    return BotConfig(
        source_channels=list(raw_config.get("source_channels", [])),
        destination=str(raw_config.get("destination", "")),
        api_id=int(_get_required_env("API_ID")),
        api_hash=_get_required_env("API_HASH"),
        phone=_get_required_env("PHONE"),
        telegram_session=os.getenv("TELEGRAM_SESSION") or None,
        session_path=session_path,
        checkpoint_path=root / "data" / "checkpoints.json",
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_key=os.getenv("SUPABASE_KEY") or None,
        important_destination=raw_config.get("important_destination") or None,
        important_keywords=[
            str(keyword).strip()
            for keyword in raw_config.get("important_keywords", [])
            if str(keyword).strip()
        ],
        backfill_days=_get_nonnegative_int_env("BACKFILL_DAYS", 2),
    )
