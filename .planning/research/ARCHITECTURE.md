# Architecture Patterns

**Domain:** Polymarket Cross-Market Arbitrage Bot
**Researched:** 2026-03-27

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              POLYMARKET APIs                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │    CLOB      │  │    Gamma     │  │     Data     │  │    Bridge    │    │
│  │  (Trading)   │  │  (Discovery) │  │  (History)   │  │  (Settlement)│    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DATA INGESTION LAYER                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  WebSocket Subscriptions (wss://ws-subscriptions-clob.polymarket.com)│   │
│  │  - Market data stream (prices, order book depth)                      │   │
│  │  - User stream (fills, position updates)                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  HTTP Polling Fallback (rate-limited)                                 │   │
│  │  - Gamma API: market metadata, watchlist                              │   │
│  │  - Data API: historical trades, positions                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NORMALIZATION LAYER                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Unified price format (binary outcome: YES/NO)                     │   │
│  │  • Timestamp alignment (within 1s window)                            │   │
│  │  • Data quality validation (stale data detection)                    │   │
│  │  • Order book aggregation                                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      OPPORTUNITY DETECTION ENGINE                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Cross-market spread calculation (YES+NO vs $1.00)                 │   │
│  │  • Fee-adjusted profitability (CLOB fees, slippage)                  │   │
│  │  • Liquidity depth filtering (minimum fill size)                     │   │
│  │  • Threshold checks (e.g., >0.5% net spread)                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RISK MANAGEMENT LAYER                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Maximum position size per trade                                   │   │
│  │  • Daily loss limit                                                  │   │
│  │  • Capital allocation guardrails (<$1k total)                        │   │
│  │  • Volatility pause triggers                                         │   │
│  │  • Emergency kill switch                                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXECUTION ENGINE                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Order placement (CLOB API via py-clob-client)                     │   │
│  │  • Order type selection (limit vs market)                            │   │
│  │  • Partial fill handling                                             │   │
│  │  • One-leg risk mitigation                                           │   │
│  │  • Stale order cancellation                                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       MONITORING & ALERTING                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  • Local dashboard (live PnL, execution metrics)                     │   │
│  │  • Telegram/Discord alerts                                           │   │
│  │  • Trade logging (S3/local storage)                                  │   │
│  │  • Connectivity health checks                                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Data Ingestion** | Fetch real-time market data from Polymarket APIs | Polymarket CLOB/Gamma/Data APIs (WebSocket + HTTP) |
| **Normalization** | Convert raw data to unified format, validate quality | Data Ingestion (input), Opportunity Engine (output) |
| **Opportunity Engine** | Detect cross-market mispricing, calculate profitability | Normalization (input), Risk Management (output) |
| **Risk Management** | Enforce trading limits, capital guardrails | Opportunity Engine (input), Execution Engine (output) |
| **Execution Engine** | Place/manage orders via CLOB API | Risk Management (input), Polymarket CLOB API, Monitoring |
| **Monitoring** | Dashboard, alerts, trade logging | Execution Engine (fills), All components (health) |

## Data Flow

**Direction:** Unidirectional pipeline with feedback loops

```
External APIs → Ingestion → Normalization → Opportunity → Risk → Execution → External APIs
                                      ↑                                        │
                                      └────────── Monitoring ←─────────────────┘
```

**Flow description:**

1. **Ingestion** pulls market data from Polymarket (WebSocket primary, HTTP fallback)
2. **Normalization** standardizes format and validates data freshness
3. **Opportunity Engine** scans for YES+NO price deviations from $1.00 parity
4. **Risk Management** validates against position limits and daily loss caps
5. **Execution Engine** places paired orders to capture spread
6. **Monitoring** receives fill confirmations and updates dashboard/alerts

**Feedback loops:**
- Execution fills → update internal position state → affects Risk Management calculations
- Connectivity errors → trigger pause in Opportunity Engine → resume on recovery

## Patterns to Follow

### Pattern 1: Async-First Data Ingestion

**What:** Use async I/O for all API calls to avoid blocking on slow responses

**When:** Always — Polymarket APIs have rate limits and variable latency

**Example:**
```python
async def fetch_market_data(session, market_id):
    async with session.get(f'{CLOB_URL}/book/{market_id}') as resp:
        return await resp.json()

# Concurrent fetching across multiple markets
tasks = [fetch_market_data(session, m) for m in watchlist]
results = await asyncio.gather(*tasks)
```

### Pattern 2: Conservative Profitability Calculation

**What:** Calculate net profit after ALL costs before executing

**When:** Every opportunity evaluation

**Example:**
```python
def calculate_net_spread(yes_price, no_price, taker_fee=0.005):
    gross_spread = 1.00 - (yes_price + no_price)
    round_trip_fee = 2 * taker_fee  # Buy YES + Buy NO
    slippage_estimate = 0.002  # Conservative 0.2%
    net_spread = gross_spread - round_trip_fee - slippage_estimate
    return net_spread
```

### Pattern 3: Circuit Breaker Risk Control

**What:** Auto-pause trading when error rates or losses exceed thresholds

**When:** Deploy in Risk Management layer

**Example:**
```python
class CircuitBreaker:
    def __init__(self, max_daily_loss=50, max_errors_per_minute=5):
        self.daily_loss = 0
        self.error_count = 0
        self.is_open = False

    def record_loss(self, amount):
        self.daily_loss += amount
        if self.daily_loss >= self.max_daily_loss:
            self.is_open = True  # Stop trading

    def record_error(self):
        self.error_count += 1
        if self.error_count >= self.max_errors_per_minute:
            self.is_open = True  # API instability detected
```

### Pattern 4: Dual-Mode Connectivity

**What:** WebSocket primary with HTTP polling fallback

**When:** Always — WebSocket disconnections are common

**Example:**
```python
class DataFeed:
    def __init__(self, ws_url, http_url, fallback_interval=5):
        self.ws_url = ws_url
        self.http_url = http_url
        self.fallback_interval = fallback_interval
        self.last_ws_message_time = None

    def is_fresh(self):
        if not self.last_ws_message_time:
            return False
        return (time.time() - self.last_ws_message_time) < self.fallback_interval

    def get_price(self, market_id):
        if self.is_fresh():
            return self.ws_cache[market_id]
        return self.http_poll(market_id)  # Fallback
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous API Calls in Hot Path

**What:** Blocking HTTP calls during opportunity scanning

**Why bad:** Adds 100-500ms latency per call — opportunities vanish in <2s

**Instead:** Use async I/O with connection pooling; pre-fetch watchlist data

### Anti-Pattern 2: Theoretical Profit Without Fee Adjustment

**What:** Calculating spread as `1.00 - (YES + NO)` without deducting fees

**Why bad:** CLOB taker fees (0.5% each side = 1% round-trip) erase apparent profits

**Instead:** Always calculate `net_spread = gross_spread - fees - slippage`

### Anti-Pattern 3: Single-Leg Execution

**What:** Executing YES buy without simultaneously executing NO buy

**Why bad:** Price moves on first fill, second leg becomes unprofitable

**Instead:** Submit both orders atomically or use IOC (immediate-or-cancel) pairs

### Anti-Pattern 4: No Stale Data Detection

**What:** Trading on WebSocket data that stopped updating

**Why bad:** Disconnected WebSocket appears healthy; trades on old prices

**Instead:** Track `last_message_timestamp`; switch to HTTP fallback if >5s stale

## Scalability Considerations

| Concern | At 10 markets | At 100 markets | At 1000 markets |
|---------|---------------|----------------|-----------------|
| **Data ingestion** | Single WebSocket subscription | Multiple WS connections + connection pooling | Shard by market category; dedicated ingestion service |
| **Opportunity scanning** | In-memory loop | Batch processing with asyncio | Stream processing (RisingWave/Flink) |
| **Order execution** | Sequential OK | Parallel with rate limit awareness | Queue-based with priority ordering |
| **State storage** | In-memory dict | Redis for shared state | Redis Cluster + PostgreSQL for persistence |

## Build Order Implications

**Recommended phase structure based on component dependencies:**

```
Phase 1: Data Foundation
├── Data Ingestion (WebSocket + HTTP)
└── Normalization Layer

Phase 2: Detection Core
├── Opportunity Engine
└── Basic profitability calculation

Phase 3: Risk & Execution
├── Risk Management (circuit breakers, limits)
└── Execution Engine (order placement)

Phase 4: Observability
├── Monitoring Dashboard
├── Alerting (Telegram/Discord)
└── Trade logging
```

**Rationale:**
- Cannot detect opportunities without reliable data (Phase 1 → Phase 2)
- Cannot execute safely without risk controls (Phase 2 → Phase 3)
- Observability is valuable but not blocking for core function (Phase 4 last)

## Sources

- [Polymarket API Guide - AgentBets.ai](https://agentbets.ai/guides/polymarket-api-guide/)
- [Polymarket Bot Quickstart - AgentBets.ai](https://agentbets.ai/guides/polymarket-bot-quickstart/)
- [Crypto Arbitrage Bot Architecture - Medium (Mar 2026)](https://medium.com/@john.galt_28062/crypto-arbitrage-bot-core-modules-and-development-steps-24376ba9f1fb)
- [Polymarket Arbitrage Case Study - AgentBets.ai](https://agentbets.ai/blog/polymarket-arbitrage-bot-case-study/)
- [15min BTC Polymarket Bot Architecture - DeepWiki](https://deepwiki.com/gabagool222/15min-btc-polymarket-trading-bot/5.1-main-bot-architecture)
- [Polymarket Arbitrage Trading Bot - GitHub](https://github.com/apechurch/polymarket-arbitrage-trading-bot/)
