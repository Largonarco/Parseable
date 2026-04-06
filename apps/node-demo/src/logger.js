/**
 * ParseableLogger - ships structured logs to Vector → Parseable
 *
 * Drop-in for any Node.js app. Supports:
 * - console.log monkey-patching
 * - Winston transport
 * - Pino transport
 * - Direct API (logger.info / logger.error / etc.)
 *
 * Environment variables:
 *   VECTOR_URL      - Vector HTTP endpoint (default: http://vector.railway.internal:9000/logs)
 *   SERVICE_NAME    - Tag logs with your service name (default: "app")
 *   LOG_LEVEL       - Minimum log level to ship (default: "info")
 *   LOG_BATCH_SIZE  - Max logs per batch (default: 50)
 *   LOG_FLUSH_MS    - Flush interval in ms (default: 3000)
 */

const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };

class ParseableLogger {
  constructor(options = {}) {
    this._queue = [];
    this.projectId = process.env.RAILWAY_PROJECT_ID || undefined;
    this.minLevel = options.level || process.env.LOG_LEVEL || "info";
    this.deploymentId = process.env.RAILWAY_DEPLOYMENT_ID || undefined;
    this.flushMs = parseInt(
      options.flushMs || process.env.LOG_FLUSH_MS || "3000",
      10,
    );
    this.batchSize = parseInt(
      options.batchSize || process.env.LOG_BATCH_SIZE || "50",
      10,
    );
    this.vectorUrl =
      options.vectorUrl ||
      process.env.VECTOR_URL ||
      "http://vector.railway.internal:9000/logs";
    this.serviceName =
      options.serviceName ||
      process.env.SERVICE_NAME ||
      process.env.RAILWAY_SERVICE_NAME ||
      "app";
    this.environment =
      process.env.RAILWAY_ENVIRONMENT_NAME ||
      process.env.NODE_ENV ||
      "production";

    this._consoleError = console.error.bind(console);

    this._flushTimer = setInterval(() => this._flush(), this.flushMs);
    if (this._flushTimer.unref) this._flushTimer.unref();

    // Flush on process exit
    // beforeExit fires when the event loop is empty — Promise resolution keeps it alive
    process.on("beforeExit", () => {
      this._flush().catch(() => {});
    });

    // SIGTERM: flush then exit so Railway shutdown doesn't drop buffered logs
    process.on("SIGTERM", () => {
      this._flush().catch(() => {});
    });
  }

  _shouldLog(level) {
    return (LEVELS[level] ?? 1) >= (LEVELS[this.minLevel] ?? 1);
  }

  _enqueue(level, message, meta = {}) {
    if (!this._shouldLog(level)) return;

    const entry = {
      level,
      service: this.serviceName,
      environment: this.environment,
      timestamp: new Date().toISOString(),
      message:
        typeof message === "object" ? JSON.stringify(message) : String(message),
      ...meta,
    };

    if (this.projectId) entry.project_id = this.projectId;
    if (this.deploymentId) entry.deployment_id = this.deploymentId;

    this._queue.push(entry);

    if (this._queue.length >= this.batchSize) {
      this._flush().catch(() => {});
    }
  }

  async _flush() {
    if (this._queue.length === 0) return;

    const batch = this._queue.splice(0, this._queue.length);

    try {
      const response = await fetch(this.vectorUrl, {
        method: "POST",
        body: JSON.stringify(batch),
        signal: AbortSignal.timeout(5000),
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) {
        this._consoleError(
          `[ParseableLogger] Vector returned ${response.status}`,
        );
      }
    } catch (err) {
      // Silently fail - never let logging break your app
      // Uncomment to debug: console.error('[ParseableLogger] Failed to flush:', err.message);
    }
  }

  debug(message, meta = {}) {
    this._enqueue("debug", message, meta);
  }
  info(message, meta = {}) {
    this._enqueue("info", message, meta);
  }
  warn(message, meta = {}) {
    this._enqueue("warn", message, meta);
  }
  error(message, meta = {}) {
    this._enqueue("error", message, meta);
  }
  log(message, meta = {}) {
    this._enqueue("info", message, meta);
  }

  /**
   * Monkey-patch console.log / console.error / console.warn
   * to ship all console output to Parseable automatically.
   * Call this once at app startup.
   */
  patchConsole() {
    if (this._consolePatchApplied) return this;
    this._consolePatchApplied = true;

    const originalLog = console.log.bind(console);
    const originalWarn = console.warn.bind(console);
    const originalError = console.error.bind(console);

    console.log = (...args) => {
      originalLog(...args);
      this.info(
        args
          .map((a) => (typeof a === "object" ? JSON.stringify(a) : a))
          .join(" "),
      );
    };

    console.warn = (...args) => {
      originalWarn(...args);
      this.warn(
        args
          .map((a) => (typeof a === "object" ? JSON.stringify(a) : a))
          .join(" "),
      );
    };

    console.error = (...args) => {
      originalError(...args);
      this.error(
        args
          .map((a) => (typeof a === "object" ? JSON.stringify(a) : a))
          .join(" "),
      );
    };

    return this;
  }

  /**
   * Returns an Express middleware that logs all HTTP requests.
   */
  expressMiddleware({ ignorePaths = ["/health"] } = {}) {
    return (req, res, next) => {
      if (ignorePaths.includes(req.path)) return next();
      const start = Date.now();
      res.on("finish", () => {
        this.info(`${req.method} ${req.path} ${res.statusCode}`, {
          ip: req.ip,
          path: req.path,
          method: req.method,
          type: "http_request",
          status_code: res.statusCode,
          duration_ms: Date.now() - start,
          user_agent: req.get("User-Agent"),
        });
      });
      next();
    };
  }

  /**
   * Winston transport - use with winston.createLogger
   *
   * Example:
   *   const winston = require('winston');
   *   const { ParseableLogger } = require('./logger');
   *   const pLogger = new ParseableLogger();
   *   const logger = winston.createLogger({
   *     transports: [
   *       new winston.transports.Console(),
   *       pLogger.winstonTransport(),
   *     ]
   *   });
   */
  winstonTransport() {
    const self = this;
    // lazy require - only if winston is installed
    try {
      const Transport = require("winston-transport");
      return new (class ParseableTransport extends Transport {
        log(info, callback) {
          const { level, message, ...meta } = info;
          self._enqueue(level, message, meta);
          callback();
        }
      })();
    } catch {
      throw new Error(
        "winston-transport is required. Run: npm install winston-transport",
      );
    }
  }

  /**
   * Pino destination - use with pino({ destination: logger.pinoDestination() })
   *
   * Example:
   *   const pino = require('pino');
   *   const { ParseableLogger } = require('./logger');
   *   const pLogger = new ParseableLogger();
   *   const logger = pino({}, pLogger.pinoDestination());
   */
  pinoDestination() {
    const self = this;
    const { Writable } = require("stream");
    return new Writable({
      write(chunk, _enc, cb) {
        try {
          const log = JSON.parse(chunk.toString());
          const levelMap = {
            10: "trace",
            20: "debug",
            30: "info",
            40: "warn",
            50: "error",
            60: "fatal",
          };
          const level = levelMap[log.level] || "info";
          const { msg, level: _l, time, ...meta } = log;
          self._enqueue(level, msg || log.message || "", meta);
        } catch {
          /* ignore malformed */
        }
        cb();
      },
    });
  }
}

// Singleton Export
const logger = new ParseableLogger();

module.exports = { ParseableLogger, logger };
