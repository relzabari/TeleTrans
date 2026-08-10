from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.runtime import BotRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

runtime = BotRuntime()


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


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000")),
        log_level="info",
    )
