# Log Integration Snippets

> Copy-paste any of these snippets into your Railway-hosted app to start shipping logs to Parseable via Vector.
>
> **Prerequisite**: The Vector service must be running in your Railway project. Logs are sent to `http://vector.railway.internal:9000/logs` over private networking — no public URL needed.

---

## Node.js

### Option 1: Copy the logger file (zero dependencies)

Copy [`apps/node-demo/src/logger.js`](apps/node-demo/src/logger.js) into your project, then:

```javascript
const { logger } = require('./logger');

// One-liner: patches console.log/warn/error to ship everything to Parseable
logger.patchConsole();

// Or use structured logging directly:
logger.info('User signed up', { user_id: '123', plan: 'pro' });
logger.warn('Rate limit approaching', { requests: 950, limit: 1000 });
logger.error('Payment failed', { order_id: 'ord_abc', reason: 'card_declined' });
```

Set these env vars in Railway:
```
VECTOR_URL=http://vector.railway.internal:9000/logs
SERVICE_NAME=my-service
```

---

### Option 2: console.log monkey-patch (truly zero config)

Drop this at the very top of your entry file. No imports, no changes to existing code:

```javascript
// ── Parseable log shipping (drop this at top of your entry file) ──────────
(() => {
  const VECTOR_URL = process.env.VECTOR_URL || 'http://vector.railway.internal:9000/logs';
  const SERVICE = process.env.SERVICE_NAME || process.env.RAILWAY_SERVICE_NAME || 'app';
  const ENV = process.env.RAILWAY_ENVIRONMENT_NAME || process.env.NODE_ENV || 'production';
  const queue = [];
  let timer;

  const flush = async () => {
    if (!queue.length) return;
    const batch = queue.splice(0, queue.length);
    try {
      await fetch(VECTOR_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(batch),
        signal: AbortSignal.timeout(5000),
      });
    } catch { /* never let logging crash the app */ }
  };

  const enqueue = (level, args) => {
    const message = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
    queue.push({ timestamp: new Date().toISOString(), level, message, service: SERVICE, environment: ENV });
    if (!timer) { timer = setInterval(flush, 3000); timer.unref(); }
    if (queue.length >= 50) flush();
  };

  const _log = console.log.bind(console);
  const _warn = console.warn.bind(console);
  const _error = console.error.bind(console);
  console.log = (...a) => { _log(...a); enqueue('info', a); };
  console.warn = (...a) => { _warn(...a); enqueue('warn', a); };
  console.error = (...a) => { _error(...a); enqueue('error', a); };

  process.on('beforeExit', flush);
  process.on('SIGTERM', () => flush().finally(() => process.exit(0)));
})();
// ── End Parseable snippet ─────────────────────────────────────────────────
```

---

### Option 3: Winston transport

```javascript
const winston = require('winston');

// Custom Parseable transport for Winston
class ParseableTransport extends require('winston-transport') {
  constructor(opts = {}) {
    super(opts);
    this.url = opts.url || process.env.VECTOR_URL || 'http://vector.railway.internal:9000/logs';
    this.service = opts.service || process.env.SERVICE_NAME || 'app';
    this._queue = [];
    setInterval(() => this._flush(), 3000).unref();
  }
  log({ level, message, ...meta }, cb) {
    this._queue.push({
      timestamp: new Date().toISOString(), level, message,
      service: this.service, ...meta,
    });
    if (this._queue.length >= 50) this._flush();
    cb();
  }
  async _flush() {
    if (!this._queue.length) return;
    const batch = this._queue.splice(0);
    try {
      await fetch(this.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(batch) });
    } catch {}
  }
}

const logger = winston.createLogger({
  transports: [
    new winston.transports.Console(),
    new ParseableTransport(),
  ],
});

logger.info('Server started', { port: 3000 });
```

---

### Option 4: Pino transport

```javascript
const pino = require('pino');
const { Writable } = require('stream');

const VECTOR_URL = process.env.VECTOR_URL || 'http://vector.railway.internal:9000/logs';
const SERVICE = process.env.SERVICE_NAME || 'app';

// Parseable destination for pino
const queue = [];
const flushToVector = async () => {
  if (!queue.length) return;
  const batch = queue.splice(0);
  try {
    await fetch(VECTOR_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(batch),
    });
  } catch {}
};
setInterval(flushToVector, 3000).unref();

const pinoStream = new Writable({
  write(chunk, _enc, cb) {
    try {
      const log = JSON.parse(chunk);
      const lvlMap = { 10: 'trace', 20: 'debug', 30: 'info', 40: 'warn', 50: 'error', 60: 'fatal' };
      queue.push({
        timestamp: new Date(log.time).toISOString(),
        level: lvlMap[log.level] || 'info',
        message: log.msg,
        service: SERVICE,
        ...Object.fromEntries(Object.entries(log).filter(([k]) => !['level','msg','time'].includes(k))),
      });
    } catch {}
    cb();
  }
});

const logger = pino({}, pinoStream);
logger.info({ user: 'alice' }, 'User logged in');
```

---

## Python

### Option 1: Copy the logger file (recommended)

Copy [`apps/python-demo/src/logger.py`](apps/python-demo/src/logger.py) into your project, then:

```python
from src.logger import parseable_logger
import logging

# Wire into standard library logging (catches all third-party library logs too)
logging.getLogger().addHandler(parseable_logger.get_handler())

# Use directly
parseable_logger.info("User signed up", user_id="123", plan="pro")
parseable_logger.warn("Rate limit approaching", requests=950, limit=1000)
parseable_logger.error("Payment failed", order_id="ord_abc", reason="card_declined")
```

Set these env vars in Railway:
```
VECTOR_URL=http://vector.railway.internal:9000/logs
SERVICE_NAME=my-service
```

---

### Option 2: Minimal Python snippet (no extra files)

Drop this at the top of your `main.py`:

```python
# ── Parseable log shipping ────────────────────────────────────────────────────
import json, logging, os, queue, threading, urllib.request

class _ParseableHandler(logging.Handler):
    _LEVEL = {"DEBUG":"debug","INFO":"info","WARNING":"warn","ERROR":"error","CRITICAL":"error"}
    def __init__(self):
        super().__init__()
        self.setLevel(getattr(logging, os.environ.get("LOG_LEVEL","INFO").upper(), logging.INFO))
        self._url = os.environ.get("VECTOR_URL","http://vector.railway.internal:9000/logs")
        self._svc = os.environ.get("SERVICE_NAME", os.environ.get("RAILWAY_SERVICE_NAME","app"))
        self._env = os.environ.get("RAILWAY_ENVIRONMENT_NAME","production")
        self._q = []
        self._lock = threading.Lock()
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        import atexit; atexit.register(self._flush)
    def _loop(self):
        import time
        while True:
            time.sleep(3)
            self._flush()
    def _flush(self):
        with self._lock:
            if not self._q: return
            batch, self._q = self._q[:], []
        try:
            data = json.dumps(batch).encode()
            req = urllib.request.Request(self._url, data=data, headers={"Content-Type":"application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except: pass
    def emit(self, r):
        from datetime import datetime, timezone
        ts = datetime.fromtimestamp(r.created, tz=timezone.utc).isoformat()
        with self._lock:
            self._q.append({"timestamp":ts,"level":self._LEVEL.get(r.levelname,"info"),
                            "message":self.format(r),"service":self._svc,"environment":self._env})
            if len(self._q)>=50: threading.Thread(target=self._flush,daemon=True).start()

logging.getLogger().addHandler(_ParseableHandler())
# ── End Parseable snippet ─────────────────────────────────────────────────────
```

---

### Option 3: Django logging backend

In `settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
        # Add this handler:
        'parseable': {
            'class': 'myapp.parseable_handler.ParseableHandler',
            # (copy the _ParseableHandler class above into myapp/parseable_handler.py)
            # Note: _ParseableHandler is a logging.Handler — use it with Python's standard
            # logging module (logging.info(), logging.warning(), etc.), not as a direct
            # logger object. For a direct API (logger.info(), logger.warn()), use the
            # full ParseableLogger class from logger.py instead.
        },
    },
    'root': {
        'handlers': ['console', 'parseable'],
        'level': 'INFO',
    },
}
```

---

### Option 4: FastAPI middleware

```python
import time, json, os
import httpx
from starlette.middleware.base import BaseHTTPMiddleware

VECTOR_URL = os.environ.get("VECTOR_URL", "http://vector.railway.internal:9000/logs")
SERVICE = os.environ.get("SERVICE_NAME", "app")
_client = httpx.AsyncClient()

class ParseableMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        await _client.post(VECTOR_URL, json=[{
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": "info",
            "message": f"{request.method} {request.url.path} {response.status_code}",
            "service": SERVICE,
            "method": request.method,
            "path": str(request.url.path),
            "status_code": response.status_code,
            "duration_ms": round((time.time() - start) * 1000),
            "type": "http_request",
        }])
        return response

# app.add_middleware(ParseableMiddleware)
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `VECTOR_URL` | `http://vector.railway.internal:9000/logs` | Vector HTTP endpoint (private network) |
| `SERVICE_NAME` | `app` | Tag to identify which service the log came from |
| `LOG_LEVEL` | `info` | Minimum level to ship (`debug`, `info`, `warn`, `error`) |
| `LOG_BATCH_SIZE` | `50` | Flush after this many queued entries |
| `LOG_FLUSH_MS` (Node) / `LOG_FLUSH_SECS` (Python) | `3000` / `3` | Flush interval |

---

## Using S3 Storage Instead of Railway Volume

To use S3-compatible storage (AWS S3, Backblaze B2, DigitalOcean Spaces, MinIO):

1. Remove the Volume from the Parseable service
2. Change the start command to `parseable server s3-store`
3. Add these variables to the Parseable service:

```
P_S3_URL=https://s3.us-east-1.amazonaws.com
P_S3_ACCESS_KEY=your_access_key
P_S3_SECRET_KEY=your_secret_key
P_S3_BUCKET=my-parseable-logs
P_S3_REGION=us-east-1
```

For Backblaze B2:
```
P_S3_URL=https://s3.us-west-004.backblazeb2.com
P_S3_PATH_STYLE=true
```
