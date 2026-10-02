from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from app.admin_store import SupabaseAdminStore
from app.completion import telegram_chat_id
from app.runtime import BotRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

runtime = BotRuntime()
security = HTTPBasic(auto_error=False)


class ChannelCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=200)


class ChannelUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=200)
    source_chat_id: int | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class KeywordCreate(BaseModel):
    phrase: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)


class KeywordUpdate(BaseModel):
    phrase: str | None = Field(default=None, min_length=1, max_length=500)
    language: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None


class SettingsUpdate(BaseModel):
    destination: str | None = Field(default=None, min_length=1, max_length=200)
    important_destination: str | None = Field(default=None, max_length=200)
    destination_chat_id: int | None = None
    important_destination_chat_id: int | None = None
    backfill_days: int | None = Field(default=None, ge=0)
    config_refresh_seconds: int | None = Field(default=None, ge=10)


def require_admin(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
) -> str:
    expected_username = os.getenv("ADMIN_USERNAME", "").strip()
    expected_password = os.getenv("ADMIN_PASSWORD", "")
    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured",
        )
    authenticated = credentials is not None and secrets.compare_digest(
        credentials.username.encode("utf-8"), expected_username.encode("utf-8")
    ) and secrets.compare_digest(
        credentials.password.encode("utf-8"), expected_password.encode("utf-8")
    )
    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": 'Basic realm="TeleTrans Admin"'},
        )
    return expected_username


@lru_cache(maxsize=1)
def get_admin_store() -> SupabaseAdminStore:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase admin storage is not configured",
        )
    return SupabaseAdminStore(url, key)


def _clean_optional(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    return cleaned or None


def _channel_values(values: dict) -> dict:
    if "username" in values and values["username"] is not None:
        values["username"] = values["username"].strip().lstrip("@")
        if not values["username"]:
            raise HTTPException(status_code=422, detail="Channel username is required")
    if "display_name" in values:
        values["display_name"] = _clean_optional(values["display_name"])
    return values


def _keyword_values(values: dict) -> dict:
    if "phrase" in values and values["phrase"] is not None:
        values["phrase"] = values["phrase"].strip()
        if not values["phrase"]:
            raise HTTPException(status_code=422, detail="Keyword phrase is required")
    for field in ("language", "category"):
        if field in values:
            values[field] = _clean_optional(values[field])
    return values


async def _resolve_source_channel(username: str) -> tuple[str, int]:
    client = runtime.client
    if not client or not client.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram is not connected; try again after the service is ready",
        )
    try:
        entity = await client.get_entity(username)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Could not resolve admin source channel %r: %s", username, exc
        )
        raise HTTPException(
            status_code=422,
            detail="Telegram channel was not found or is not accessible",
        ) from exc
    resolved_username = str(getattr(entity, "username", None) or username)
    return resolved_username, telegram_chat_id(entity)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="TeleTrans", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    status_code = 503 if runtime.status == "error" else 200
    return JSONResponse(runtime.health(), status_code=status_code)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(_admin: Annotated[str, Depends(require_admin)]) -> HTMLResponse:
    html = Path(__file__).with_name("admin.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/admin/config")
async def admin_config(
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    return await get_admin_store().get_configuration()


@app.post("/api/admin/channels", status_code=201)
async def create_channel(
    payload: ChannelCreate,
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    values = _channel_values(payload.model_dump())
    values["username"], values["source_chat_id"] = await _resolve_source_channel(
        values["username"]
    )
    return await get_admin_store().insert("source_channels", values)


@app.patch("/api/admin/channels/{row_id}")
async def update_channel(
    row_id: int,
    payload: ChannelUpdate,
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    values = _channel_values(payload.model_dump(exclude_unset=True))
    if not values:
        raise HTTPException(status_code=422, detail="No channel changes supplied")
    if "username" in values:
        values["username"], values["source_chat_id"] = await _resolve_source_channel(
            values["username"]
        )
    return await get_admin_store().update("source_channels", row_id, values)


@app.delete("/api/admin/channels/{row_id}", status_code=204)
async def delete_channel(
    row_id: int,
    _admin: Annotated[str, Depends(require_admin)],
) -> Response:
    await get_admin_store().delete("source_channels", row_id)
    return Response(status_code=204)


@app.post("/api/admin/keywords", status_code=201)
async def create_keyword(
    payload: KeywordCreate,
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    values = _keyword_values(payload.model_dump())
    return await get_admin_store().insert("important_keywords", values)


@app.patch("/api/admin/keywords/{row_id}")
async def update_keyword(
    row_id: int,
    payload: KeywordUpdate,
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    values = _keyword_values(payload.model_dump(exclude_unset=True))
    if not values:
        raise HTTPException(status_code=422, detail="No keyword changes supplied")
    return await get_admin_store().update("important_keywords", row_id, values)


@app.delete("/api/admin/keywords/{row_id}", status_code=204)
async def delete_keyword(
    row_id: int,
    _admin: Annotated[str, Depends(require_admin)],
) -> Response:
    await get_admin_store().delete("important_keywords", row_id)
    return Response(status_code=204)


@app.patch("/api/admin/settings")
async def update_settings(
    payload: SettingsUpdate,
    _admin: Annotated[str, Depends(require_admin)],
) -> dict:
    values = payload.model_dump(exclude_unset=True)
    for field in ("destination", "important_destination"):
        if field in values:
            values[field] = _clean_optional(values[field])
    if not values:
        raise HTTPException(status_code=422, detail="No setting changes supplied")
    if values.get("destination") is None and "destination" in values:
        raise HTTPException(status_code=422, detail="Destination is required")
    return await get_admin_store().update("app_settings", 1, values)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        log_level="info",
    )
