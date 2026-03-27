<!-- GSD:project-start source:PROJECT.md -->
## Project

**Polymarket Arbitrage Bot**

A fully automated arbitrage trading bot that identifies and executes cross-market mispricing opportunities on Polymarket prediction markets. The bot continuously scans markets, detects arbitrage opportunities, and automatically executes trades to capture price discrepancies.

**Core Value:** Ultra-low latency detection and execution of cross-market arbitrage opportunities on Polymarket before they disappear.

### Constraints

- **Tech stack:** Must integrate with Polymarket's official API
- **Latency:** Ultra-low latency execution required for strategy effectiveness
- **Capital:** Under $1k total capital at risk
- **Deployment:** Must run continuously on cloud VPS
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Python** | 3.10+ | Runtime | Best ecosystem for trading bots, py-clob-client is official Polymarket SDK, asyncio support for concurrent API calls |
| **py-clob-client** | Latest (2026) | Polymarket API client | Official Polymarket Python SDK, supports full CLOB API including market data, order management, authentication, and WebSocket streaming |
### Blockchain Interaction
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **ethers.py** | v5+ | Wallet signing, chain interaction | Required by py-clob-client for signer, simpler API than web3.py for this use case, Polymarket docs explicitly recommend ethers@5 (TS) equivalent |
### HTTP Client
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **httpx** | 0.28+ | Async HTTP requests | Best balance of sync/async support, HTTP/2 for reduced latency, cleaner API than aiohttp for <300 concurrent requests (typical for Polymarket scanning), used by OpenAI/Anthropic SDKs |
### WebSocket
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **websockets** | 16.0+ | Real-time market data | Official Polymarket SDK uses this internally, asyncio-native, production-proven, 80+ contributors, actively maintained (Jan 2026 release) |
### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **SQLite** | 3.40+ | Trade logs, metrics storage | Under $1k capital = low write volume, zero configuration, single file deployment, sufficient for local dashboard metrics |
| **TimescaleDB** | 2.20+ (optional) | Time-series market data | Only if storing tick-level order book snapshots for backtesting. Use PostgreSQL + TimescaleDB extension when ready for historical analysis |
### Logging
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Loguru** | 0.7+ | Application logging | Zero configuration, automatic rotation, JSON serialization for production, exception catching with `@logger.catch`, 10x faster than stdlib logging |
### Notifications
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **python-telegram-bot** | 21+ | Telegram alerts | Official Telegram Bot API wrapper, async support, battle-tested (10M+ downloads), simple setup |
| **discord.py** | 2.4+ | Discord webhooks | Official Discord library, webhook support for simple notifications, active maintenance |
### Process Management (VPS Deployment)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Docker** | 24+ | Containerization | Reproducible deployments, quick rollbacks, resource limits, isolation, health checks |
| **Docker Compose** | 2.20+ | Multi-container orchestration | Single-command deployment, volume management for logs/data |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **python-dotenv** | 1.0+ | Environment variable management | Always — load API keys from `.env` file |
| **pandas** | 2.2+ | Data manipulation | If computing rolling statistics, OHLCV aggregations |
| **numpy** | 1.26+ | Numerical operations | If doing complex probability calculations |
| **redis** | 5.0+ | Caching layer | Only if caching order book data across multiple bot instances |
| **prometheus-client** | 0.20+ | Metrics export | If building advanced monitoring dashboard with Grafana |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Language | Python | Node.js | py-clob-client is official SDK, Python dominates quant/trading ecosystem, easier backtesting with pandas/numpy |
| HTTP Client | httpx | aiohttp | HTTPX has HTTP/2, cleaner API, sufficient performance for Polymarket scale |
| Blockchain | ethers.py | web3.py | py-clob-client handles chain interaction; ethers.py is simpler if direct calls needed |
| Database | SQLite | PostgreSQL | SQLite is zero-config, sufficient for <100 trades/day. Migrate to PostgreSQL when scaling |
| Deployment | Docker | PM2 | PM2 is Node.js-only. Docker works for any language + better isolation |
| Logging | Loguru | structlog | Loguru works out-of-box. Structlog needs configuration overhead |
## Installation
# Core dependencies
# HTTP + WebSocket
# Logging + Notifications
# Data + Database
# Dev dependencies (testing)
# Docker (system-level, not pip)
# curl -fsSL https://get.docker.com | sh
### requirements.txt
## Confidence Assessment
| Component | Confidence | Reason |
|-----------|------------|--------|
| py-clob-client | HIGH | Official Polymarket SDK, verified from docs.polymarket.com |
| Python runtime | HIGH | Industry standard for trading bots, confirmed via multiple 2025-2026 sources |
| httpx | HIGH | Benchmarked comparison sources, HTTP/2 advantage verified |
| websockets | HIGH | Standard Python WebSocket library, verified from PyPI + GitHub |
| SQLite | MEDIUM | Reasonable for scale, but may need upgrade path if write volume increases |
| Loguru | HIGH | Verified from Real Python + official docs, production-proven |
| Docker deployment | HIGH | Verified from multiple 2025-2026 VPS deployment guides |
## Sources
- [Polymarket CLOB Client SDKs](https://docs.polymarket.com/api-reference/clients-sdks)
- [Polymarket Python Client GitHub](https://github.com/Polymarket/py-clob-client)
- [Polymarket TypeScript Client GitHub](https://github.com/Polymarket/clob-client)
- [HTTPX vs AIOHTTP Benchmarks](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp)
- [WebSocket Libraries 2026](https://github.com/websockets/ws)
- [Python WebSockets Library](https://websockets.readthedocs.io/en/stable/project/changelog.html)
- [Time-Series DB Comparison](https://questdb.com/blog/scaling-trading-bot-with-time-series-database/)
- [VPS Deployment Best Practices](https://dev.to/propfirmkey/docker-containerization-for-trading-bots-best-practices-1gd6)
- [Loguru Documentation](https://loguru.org/)
- [Structlog Documentation](https://structlog.org/)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
