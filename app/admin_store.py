from __future__ import annotations

import asyncio
from typing import Any


class SupabaseAdminStore:
    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, key)

    async def get_configuration(self) -> dict[str, Any]:
        def query() -> dict[str, Any]:
            channels = (
                self.client.table("source_channels")
                .select("*")
                .order("sort_order")
                .order("id")
                .execute()
                .data
            )
            keywords = (
                self.client.table("important_keywords")
                .select("*")
                .order("id")
                .execute()
                .data
            )
            settings = (
                self.client.table("app_settings")
                .select("*")
                .eq("id", 1)
                .limit(1)
                .execute()
                .data
            )
            return {
                "channels": channels,
                "keywords": keywords,
                "settings": settings[0] if settings else None,
            }

        return await asyncio.to_thread(query)

    async def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        def query() -> dict[str, Any]:
            response = self.client.table(table).insert(values).execute()
            return response.data[0]

        return await asyncio.to_thread(query)

    async def update(
        self, table: str, row_id: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        def query() -> dict[str, Any]:
            response = (
                self.client.table(table)
                .update(values)
                .eq("id", row_id)
                .execute()
            )
            if not response.data:
                raise LookupError(f"Row {row_id} was not found in {table}")
            return response.data[0]

        return await asyncio.to_thread(query)

    async def delete(self, table: str, row_id: int) -> None:
        def query() -> None:
            self.client.table(table).delete().eq("id", row_id).execute()

        await asyncio.to_thread(query)
