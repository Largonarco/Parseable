"""
Railway + Parseable Python Demo App

Shows structured log shipping to Parseable via Vector.
Hit the /demo/* endpoints to generate logs, then check your Parseable dashboard.
"""

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI  # type: ignore[import-untyped]

from src.logger import parseable_logger  # type: ignore[import-untyped]

logging.basicConfig(level=logging.INFO)
logging.getLogger().addHandler(parseable_logger.get_handler())


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    parseable_logger.info(
        "Application started",
        framework="FastAPI",
        python_version=sys.version,
        environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "production"),
    )

    # Background Heartbeat Task
    async def heartbeat():
        while True:
            await asyncio.sleep(30)
            parseable_logger.info(
                "Heartbeat",
                type="heartbeat",
                uptime_note="app is healthy",
            )

    task = asyncio.create_task(heartbeat())

    yield

    # Shutdown
    task.cancel()
    parseable_logger.info("Application shutting down")
    parseable_logger.stop()


# App
app = FastAPI(
    title="Railway + Parseable Demo",
    description="Demo app for Railway → Vector → Parseable log pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

# Request Logging Middleware
app.add_middleware(parseable_logger.asgi_middleware())


# Routes
@app.get("/")
async def root():
    parseable_logger.info("Home page visited", route="/")
    return {
        "message": "Railway + Parseable Python demo app",
        "status": "running",
        "docs": "/docs",
        "demo_endpoints": [
            "/demo/info",
            "/demo/warn",
            "/demo/error",
            "/demo/burst?count=20",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/demo/info")
async def demo_info():
    parseable_logger.info(
        "User action recorded",
        user_id="user_456",
        action="page_view",
        page="/dashboard",
    )
    return {"logged": "info message", "check": "parseable dashboard"}


@app.get("/demo/warn")
async def demo_warn():
    parseable_logger.warn(
        "Database connection pool near capacity",
        pool_size=10,
        active_connections=9,
        threshold=8,
    )
    return {"logged": "warning message"}


@app.get("/demo/error")
async def demo_error():
    parseable_logger.error(
        "Failed to process webhook",
        webhook_id="wh_abc123",
        error="timeout after 30s",
        retry_count=3,
    )
    return {"logged": "error message"}


@app.get("/demo/burst")
async def demo_burst(count: int = 20):
    for i in range(count):
        parseable_logger.info(
            f"Burst log {i + 1}/{count}",
            burst_index=i,
            total=count,
        )
    return {"logged": count, "message": f"Sent {count} logs - check Parseable!"}
