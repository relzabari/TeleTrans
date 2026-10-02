from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class DynamicConfig:
    source_channels: list[str]
    destination: str | int
    important_destination: str | int | None
    important_keywords: list[str]
    backfill_days: int
    refresh_seconds: int


class SupabaseConfigStore:
    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, key)

    async def load(self) -> DynamicConfig:
        def query() -> DynamicConfig:
            channel_response = (
                self.client.table("source_channels")
                .select("username")
                .eq("enabled", True)
                .order("sort_order")
                .order("id")
                .execute()
            )
            keyword_response = (
                self.client.table("important_keywords")
                .select("phrase")
                .eq("enabled", True)
                .order("id")
                .execute()
            )
            settings_response = (
                self.client.table("app_settings")
                .select(
                    "destination,destination_chat_id,important_destination,"
                    "important_destination_chat_id,backfill_days,"
                    "config_refresh_seconds"
                )
                .eq("id", 1)
                .limit(1)
                .execute()
            )
            if not settings_response.data:
                raise RuntimeError("Supabase app_settings row 1 was not found")

            settings = settings_response.data[0]
            channels = [
                str(row["username"]).strip().lstrip("@")
                for row in channel_response.data
                if str(row.get("username", "")).strip()
            ]
            if not channels:
                raise RuntimeError("Supabase has no enabled source channels")

            return DynamicConfig(
                source_channels=channels,
                destination=(
                    int(settings["destination_chat_id"])
                    if settings.get("destination_chat_id") is not None
                    else str(settings["destination"]).strip()
                ),
                important_destination=(
                    int(settings["important_destination_chat_id"])
                    if settings.get("important_destination_chat_id") is not None
                    else (
                        str(settings["important_destination"]).strip()
                        if settings.get("important_destination")
                        else None
                    )
                ),
                important_keywords=[
                    str(row["phrase"]).strip()
                    for row in keyword_response.data
                    if str(row.get("phrase", "")).strip()
                ],
                backfill_days=int(settings["backfill_days"]),
                refresh_seconds=int(settings["config_refresh_seconds"]),
            )

        return await asyncio.to_thread(query)
