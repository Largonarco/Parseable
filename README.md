# Parseable on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/1eCCDv?referralCode=XB0mqZ&utm_medium=integration&utm_source=template&utm_campaign=generic)

A production-ready Railway template that deploys **Parseable** (a modern observability platform) with a **Vector** log aggregation service — giving any Railway-hosted application structured, searchable, long-term log storage with an AI-native dashboard.

---

## What You Get

```
Your App(s)
    │  HTTP POST JSON logs
    ▼
┌─────────────────────────────┐
│  Vector  (railway.internal) │  ← batches, compresses, routes
│  port 9000                  │
└─────────────┬───────────────┘
              │ gzip + basic auth
              ▼
┌─────────────────────────────┐
│  Parseable                  │  ← stores, indexes, queries
│  port 8000  (public domain) │
└─────────────────────────────┘
        │
        ▼
  Parseable UI Dashboard
  SQL Editor · Alerts · AI
```

- **Parseable** — Rust-based observability platform. Stores logs as Parquet on a Railway Volume (or S3). Ships with a full-featured UI, SQL editor, dashboards, and alerting.
- **Vector** — High-performance log router. Receives JSON log batches from your apps over private networking, adds batching + gzip compression, and forwards to Parseable.
- **Node.js Demo App** — Pre-wired Express app with structured logging. Shows logs in Parseable immediately after deploy.
- **Python Demo App** — Pre-wired FastAPI app with structured logging. Interactive docs at `/docs`, demo endpoints identical to the Node app.

---

## One-Click Deploy

Click the button above, or navigate to:

```
https://railway.com/deploy/1eCCDv?referralCode=XB0mqZ&utm_medium=integration&utm_source=template&utm_campaign=generic
```

Railway will provision all three services with pre-configured networking and auto-generated credentials.

---

## Architecture

### Why Vector as a middle layer?

Railway apps write to stdout/stderr, but Railway has no native log drain/export API. Instead of writing directly to Parseable from each app (which works but creates tight coupling), Vector acts as a **decoupled log aggregator**:

- **Private networking** — apps talk to `vector.railway.internal:9000` — no public traffic, no auth needed from the app side
- **Batching** — Vector buffers up to 1,000 events or 10MB, reducing HTTP round-trips to Parseable
- **Compression** — gzip compression on all payloads
- **Resilience** — if Parseable is temporarily down, Vector queues logs in memory
- **Format normalization** — Vector's VRL transform unifies `msg`/`message` fields, normalizes log levels, and backfills timestamps

### Storage: Railway Volume (default) vs S3

| Mode | Default | Persistent | Production-ready |
|------|---------|-----------|-----------------|
| Railway Volume (`local-store`) | ✅ | ✅ | ✓ (single node) |
| S3-compatible (`s3-store`) | — | ✅ | ✅ (recommended for scale) |

See [SNIPPETS.md](SNIPPETS.md#using-s3-storage-instead-of-railway-volume) for S3 setup.

---

## Connecting Your Own App

### Step 1: Add environment variable

In your Railway service, add:
```
VECTOR_URL=http://vector.railway.internal:9000/logs
SERVICE_NAME=my-service-name
```

### Step 2: Add log shipping (pick your language)

**Node.js — zero-dependency snippet** (drop at top of entry file):

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

**Python — stdlib only** (drop at top of `main.py`):

```python
# ── Parseable log shipping ────────────────────────────────────────────────
import json, logging, os, threading, urllib.request as _ur
class _PH(logging.Handler):
    _L={"DEBUG":"debug","INFO":"info","WARNING":"warn","ERROR":"error","CRITICAL":"error"}
    def __init__(self):
        super().__init__(); self._u=os.environ.get("VECTOR_URL","http://vector.railway.internal:9000/logs")
        self._s=os.environ.get("SERVICE_NAME",os.environ.get("RAILWAY_SERVICE_NAME","app"))
        self._q=[]; self._lk=threading.Lock()
        threading.Thread(target=self._loop,daemon=True).start()
        import atexit; atexit.register(self._flush)
    def _loop(self):
        import time
        while True: time.sleep(3); self._flush()
    def _flush(self):
        with self._lk:
            if not self._q: return
            b,self._q=self._q[:],[]
        try:
            r=_ur.Request(self._u,json.dumps(b).encode(),{"Content-Type":"application/json"},"POST")
            _ur.urlopen(r,timeout=5)
        except: pass
    def emit(self,r):
        from datetime import datetime,timezone
        with self._lk:
            self._q.append({"timestamp":datetime.now(timezone.utc).isoformat(),"level":self._L.get(r.levelname,"info"),"message":self.format(r),"service":self._s})
            if len(self._q)>=50: threading.Thread(target=self._flush,daemon=True).start()
logging.getLogger().addHandler(_PH())
# ── End snippet ────────────────────────────────────────────────────────────
```

For full examples with Winston, Pino, Django, FastAPI, and more — see **[SNIPPETS.md](SNIPPETS.md)**.

---

## Project Structure

```
parseable/
├── railway.json                 # Railway template definition
├── README.md                    # This file
├── SNIPPETS.md                  # Copy-paste integration snippets
├── WRITEUP.md                   # Assignment writeup
│
├── services/
│   ├── parseable/
│   │   ├── railway.toml         # Parseable service config
│   │   └── .env.example         # Env var reference
│   └── vector/
│       ├── Dockerfile           # Bakes vector.toml into image
│       ├── vector.toml          # Vector pipeline config
│       ├── railway.toml         # Vector service config
│       └── .env.example         # Env var reference
│
└── apps/
    ├── node-demo/               # Express demo app (pre-wired)
    │   ├── src/
    │   │   ├── index.js         # App routes + demo endpoints
    │   │   └── logger.js        # ParseableLogger class
    │   ├── package.json
    │   ├── railway.toml
    │   └── .env.example
    │
    └── python-demo/             # FastAPI demo app (pre-wired)
        ├── src/
        │   ├── main.py          # FastAPI routes + demo endpoints
        │   └── logger.py        # ParseableLogger class (Python)
        ├── requirements.txt
        ├── railway.toml
        └── .env.example
```

---

## Accessing Parseable

After deploy, Railway assigns a public domain to the Parseable service. Find it in the Railway dashboard under the Parseable service → Settings → Domains.

- **UI**: `https://your-parseable-domain.railway.app`
- **Default credentials**: `admin` / `<auto-generated from template>`
- **Stream**: `railway-logs` (where all demo app logs land)

---

## Demo Endpoints

Once deployed, hit these endpoints on the **Node Demo App** to generate logs:

| Endpoint | What it logs |
|----------|-------------|
| `GET /` | Info: home page visit |
| `GET /demo/info` | Info: user action with metadata |
| `GET /demo/warn` | Warning: resource threshold |
| `GET /demo/error` | Error: payment processing failure |
| `GET /demo/burst?count=50` | Bulk: 50 info logs |

The Python demo app (FastAPI) has identical endpoints at `/docs` for interactive testing.

---

## Configuration

### Parseable environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `P_USERNAME` | `admin` | Admin username |
| `P_PASSWORD` | *(auto-generated)* | Admin password |
| `P_FS_DIR` | `/data` | Volume mount path for local store |
| `P_ADDR` | `0.0.0.0:8000` | Listen address |
| `P_CORS` | `false` | Enable CORS (set `false` to disable) |

### Vector environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PARSEABLE_URL` | `http://parseable.railway.internal:8000` | Parseable internal URL |
| `PARSEABLE_USERNAME` | *(from Parseable service)* | Auto-wired via reference variable |
| `PARSEABLE_PASSWORD` | *(from Parseable service)* | Auto-wired via reference variable |
| `PARSEABLE_STREAM` | `railway-logs` | Default Parseable stream/dataset |

---

## License

MIT