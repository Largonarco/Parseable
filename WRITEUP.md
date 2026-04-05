# Writeup: Parseable on Railway

*Under 500 words.*

---

## What I Built

A Railway template that deploys **Parseable** (a Rust-based observability platform) alongside a **Vector** log aggregation service. Together they give any Railway-hosted app structured, searchable, AI-queryable logs — persisted beyond Railway's 7-30 day retention window.

The architecture is deliberately minimal: Vector runs on Railway's private network, receiving JSON log batches from apps on port 9000. It compresses and batches them before forwarding to Parseable. Apps need no agent, no sidecar, no Docker config change — just two environment variables (`VECTOR_URL` and `SERVICE_NAME`) and a small logging snippet (< 30 lines) dropped at the top of the entry file. No structural code changes required.

Two demo apps (Node.js/Express and Python/FastAPI) are pre-wired and deploy as part of the template. You can hit `/demo/burst?count=50` and watch 50 structured logs appear in the Parseable dashboard in real time.

---

## What I'd Build Next to Drive Adoption

**The current gap is friction at "step 1"** — developers have to add a snippet to their existing app, redeploy, and then learn Parseable's UI. That's three cognitive context-switches.

The highest-leverage next thing is a **one-command CLI integration**:

```bash
npx parseable-railway add
```

This command would:
1. Detect your framework (Next.js, Express, Django, FastAPI, Rails)
2. Auto-inject the correct snippet into your entry file
3. Set the required Railway env vars via the Railway API
4. Open the Parseable dashboard

No docs to read. No snippet to copy. Zero decisions.

The second priority is a **pre-built dashboard template** for each framework — so when a Next.js developer deploys, they immediately see a dashboard with HTTP request latency, error rate, and top 5 slowest routes populated. Seeing value in 60 seconds, not 60 minutes, is what converts template users into active Parseable users.

---

## How I'd Get It Noticed in the Railway Ecosystem

**1. Railway template marketplace** — Publishing to the marketplace is table stakes. The key is the description: "Persistent logs for Railway apps. Works in 5 minutes." The copy needs to speak to the pain (Railway only keeps logs 7-30 days) not the solution (Parseable is a Rust observability platform).

**2. Central Station** — Railway's community forum. Post a "Show & Tell" thread with a 90-second video of the template working end-to-end. Railway's community is highly technical and responds well to working demos over marketing.

**3. The Parseable open-source angle** — Railway has an Open Source Technology Partner program with kickback commissions. Parseable is a real OSS project. Applying for partner status gets the template featured and earns commission on each deploy — aligning incentives.

**4. Framework-specific content** — "How to add persistent logging to your Next.js app on Railway" is a better SEO target than "Parseable Railway integration." One blog post per framework, each with a direct template deploy link.

**5. Existing Railway template users** — The Parseable template can reference other popular templates (e.g. "Using Next.js on Railway? Add this."). Cross-linking from high-traffic templates is the fastest organic path to discoverability.

---

## Scoping Decisions

- **Local Volume by default, S3 optional** — volume is zero-config; S3 docs are in SNIPPETS.md for anyone who needs it
- **Vector as aggregator, not sidecar** — Railway has no Docker socket access; Vector over private HTTP is the only clean option
- **Two demo apps (Node + Python)** — these are the two dominant Railway language ecosystems
- **Snippets over SDK** — a 20-line snippet beats a new npm dependency for adoption. Developers paste, they don't install.
