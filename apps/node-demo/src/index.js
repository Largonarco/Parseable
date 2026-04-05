const express = require("express");
const { logger } = require("./logger");

// Patch Console
logger.patchConsole();

const app = express();
const PORT = process.env.PORT || 3000;

// Log HTTP request
app.use(logger.expressMiddleware());

// Routes
app.get("/", (req, res) => {
  logger.info("Home page visited", { route: "/" });
  res.json({
    status: "running",
    message: "Railway + Parseable demo app",
    docs: "Check your Parseable dashboard for logs!",
  });
});

app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.get("/demo/info", (req, res) => {
  logger.info("Demo info log", {
    user_id: "user_123",
    action: "page_view",
    extra: "some metadata",
  });
  res.json({ logged: "info message", check: "parseable dashboard" });
});
app.get("/demo/warn", (req, res) => {
  logger.warn("High memory usage detected", {
    memory_mb: 450,
    threshold_mb: 400,
  });
  res.json({ logged: "warning message" });
});
app.get("/demo/error", (req, res) => {
  logger.error("Payment processing failed", {
    amount: 99.99,
    order_id: "ord_789",
    error_code: "CARD_DECLINED",
  });
  res.json({ logged: "error message" });
});
app.get("/demo/burst", async (req, res) => {
  const count = parseInt(req.query.count || "20", 10);
  for (let i = 0; i < count; i++) {
    logger.info(`Burst log ${i + 1}/${count}`, {
      total: count,
      burst_index: i,
    });
  }
  res.json({ logged: count, message: `Sent ${count} logs - check Parseable!` });
});

// Start
app.listen(PORT, () => {
  console.log(`Demo app listening on port ${PORT}`);
  logger.info("Application started", {
    port: PORT,
    node_version: process.version,
    environment: process.env.NODE_ENV || "production",
  });
});

// Simulate Logs
setInterval(() => {
  const messages = [
    [
      "info",
      "Heartbeat - app is healthy",
      { type: "heartbeat", uptime_seconds: process.uptime() },
    ],
    [
      "info",
      "Cache hit rate nominal",
      { type: "metric", cache_hit_rate: 0.94 },
    ],
    [
      "info",
      "Background job completed",
      { type: "job", job_name: "cleanup", duration_ms: 42 },
    ],
  ];
  const [level, msg, meta] =
    messages[Math.floor(Math.random() * messages.length)];
  logger[level](msg, meta);
}, 30000);
