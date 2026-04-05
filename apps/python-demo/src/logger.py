"""
ParseableLogger for Python - ships structured logs to Vector → Parseable

Drop-in for any Python app. Supports:
- logging.Handler (works with all standard library logging)
- Direct API (logger.info / logger.error / etc.)
- Console patch

Environment variables:
  VECTOR_URL      - Vector HTTP endpoint (default: http://vector.railway.internal:9000/logs)
  SERVICE_NAME    - Tag logs with your service name (default: "app")
  LOG_LEVEL       - Minimum log level (default: INFO)
  LOG_BATCH_SIZE  - Max logs per batch (default: 50)
  LOG_FLUSH_SECS  - Flush interval in seconds (default: 3)
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx  # type: ignore[import-untyped]

LEVEL_MAP = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warn",
    "ERROR": "error",
    "CRITICAL": "error",
}


class ParseableLogger:
    """Buffers log entries and ships them to Vector in batches via HTTP."""

    def __init__(
        self,
        vector_url: str | None = None,
        service_name: str | None = None,
        min_level: str = "INFO",
        batch_size: int | None = None,
        flush_secs: float | None = None,
    ):
        self.vector_url = vector_url or os.environ.get(
            "VECTOR_URL", "http://vector.railway.internal:9000/logs"
        )
        self.service_name = (
            service_name
            or os.environ.get("SERVICE_NAME")
            or os.environ.get("RAILWAY_SERVICE_NAME", "app")
        )
        self.min_level = getattr(logging, min_level.upper(), logging.INFO)
        self.batch_size = int(batch_size or os.environ.get("LOG_BATCH_SIZE", "50"))
        self.flush_secs = float(flush_secs or os.environ.get("LOG_FLUSH_SECS", "3"))
        self.environment = os.environ.get("RAILWAY_ENVIRONMENT_NAME") or os.environ.get(
            "ENV", "production"
        )
        self.deployment_id = os.environ.get("RAILWAY_DEPLOYMENT_ID")
        self.project_id = os.environ.get("RAILWAY_PROJECT_ID")

        self._queue: list[dict] = []
        self._lock = threading.Lock()
        self._client = httpx.Client(timeout=5.0)
        self._closed = False

        # Background flush thread
        self._stop_event = threading.Event()
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

        import atexit

        atexit.register(self.stop)

    def _flush_loop(self):
        while not self._stop_event.wait(self.flush_secs):
            self._flush()

    def _should_log(self, level: str) -> bool:
        numeric = getattr(logging, level.upper(), logging.INFO)
        return numeric >= self.min_level

    def _enqueue(self, level: str, message: str, **meta: Any):
        if not self._should_log(level):
            return

        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": LEVEL_MAP.get(level.upper(), "info"),
            "message": str(message),
            "service": self.service_name,
            "environment": self.environment,
            **meta,
        }
        if self.deployment_id:
            entry["deployment_id"] = self.deployment_id
        if self.project_id:
            entry["project_id"] = self.project_id

        with self._lock:
            self._queue.append(entry)
            should_flush = len(self._queue) >= self.batch_size

        if should_flush:
            self._flush()

    def _flush(self):
        with self._lock:
            if not self._queue:
                return
            batch = self._queue[:]
            self._queue.clear()

        try:
            resp = self._client.post(
                self.vector_url,
                content=json.dumps(batch).encode(),
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                pass  # silently fail — never let logging break your app
        except Exception:
            pass  # silently fail

    def _flush_final(self):
        """Blocking flush used only at shutdown — bypasses the _closed guard."""
        with self._lock:
            if not self._queue:
                return
            batch = self._queue[:]
            self._queue.clear()
        try:
            self._client.post(
                self.vector_url,
                content=json.dumps(batch).encode(),
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    def debug(self, message: str, **meta: Any):
        self._enqueue("DEBUG", message, **meta)

    def info(self, message: str, **meta: Any):
        self._enqueue("INFO", message, **meta)

    def warn(self, message: str, **meta: Any):
        self._enqueue("WARNING", message, **meta)

    def warning(self, message: str, **meta: Any):
        self._enqueue("WARNING", message, **meta)

    def error(self, message: str, **meta: Any):
        self._enqueue("ERROR", message, **meta)

    def critical(self, message: str, **meta: Any):
        self._enqueue("CRITICAL", message, **meta)

    # ── Integrations ─────────────────────────────────────────────────────────

    def get_handler(self) -> logging.Handler:
        """
        Returns a logging.Handler that ships records to Parseable.

        Usage:
            import logging
            from src.logger import parseable_logger

            logging.getLogger().addHandler(parseable_logger.get_handler())
            logging.info("This goes to Parseable!")
        """
        logger_self = self

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord):
                try:
                    msg = self.format(record)
                    meta = {
                        "logger_name": record.name,
                        "module": record.module,
                        "funcName": record.funcName,
                        "lineno": record.lineno,
                    }
                    if record.exc_info:
                        import traceback

                        meta["exception"] = "".join(
                            traceback.format_exception(*record.exc_info)
                        )
                    logger_self._enqueue(record.levelname, msg, **meta)
                except Exception:
                    pass

        return _Handler()

    def asgi_middleware(self):
        """
        Returns an ASGI middleware class for FastAPI / Starlette that logs all HTTP requests.

        Usage:
            from src.logger import parseable_logger
            app.add_middleware(parseable_logger.asgi_middleware())

        Note: this method returns the middleware *class* (not an instance), which is
        exactly what Starlette's add_middleware() expects.
        """
        logger_self = self

        class _ParseableMiddleware:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] != "http":
                    await self.app(scope, receive, send)
                    return

                start = time.time()
                status_code = 500

                async def send_wrapper(message):
                    nonlocal status_code
                    if message["type"] == "http.response.start":
                        status_code = message["status"]
                    await send(message)

                try:
                    await self.app(scope, receive, send_wrapper)
                except Exception:
                    # Re-raise so FastAPI/Starlette exception handlers still fire,
                    # but guarantee the request is logged regardless.
                    status_code = 500
                    raise
                finally:
                    duration_ms = round((time.time() - start) * 1000)
                    path = scope.get("path", "/")
                    method = scope.get("method", "GET")

                    logger_self.info(
                        f"{method} {path} {status_code}",
                        method=method,
                        path=path,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        type="http_request",
                    )

        return _ParseableMiddleware

    def stop(self):
        if self._closed:
            return
        self._stop_event.set()
        with self._lock:
            self._closed = True
        self._flush_final()  # drain whatever remains
        self._client.close()


# Singleton
parseable_logger = ParseableLogger()
