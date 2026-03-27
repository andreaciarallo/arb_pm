# Domain Pitfalls

**Domain:** Polymarket Cross-Market Arbitrage Bot
**Researched:** 2026-03-27

## Critical Pitfalls

Mistakes that cause rewrites or major losses.

### Pitfall 1: Latency Infrastructure Underestimation

**What goes wrong:** Building arbitrage logic without co-located infrastructure. Opportunities disappear in 2-3 seconds (sometimes milliseconds), but home internet + public RPC = 4-8 second confirmation times.

**Why it happens:**
- Developers prototype on local machines assuming production will "just be faster"
- Public RPC endpoints are 200ms+ behind co-located validators
- Competition runs from AWS eu-west-2 (London) with 5-12ms latency vs 130-150ms from US East

**Consequences:**
- Bot detects opportunities but never captures them (someone else is always first)
- 78% of crypto bot traders lose money due to infrastructure gaps
- Strategy appears sound in backtesting but produces zero executable trades in production

**Prevention:**
- Budget $200-400/month for dedicated RPC nodes from day one
- Deploy VPS in same region as Polymarket's CLOB (London eu-west-2)
- Use Geyser gRPC subscriptions instead of WebSocket polling (sub-50ms vs 100-300ms)
- Prototype in Python, but plan production execution path in Rust/C++

**Detection:**
- Track "opportunity detected" vs "opportunity captured" ratio
- If ratio < 10% after 1000 detections, infrastructure is the bottleneck
- Monitor latency from detection to order submission (target: <50ms)

**Phase to address:** Phase 1 (Infrastructure Setup)

---

### Pitfall 2: Silent API Failures and State Desync

**What goes wrong:** Polymarket's CLOB API has multiple failure modes that appear successful but don't execute. Bot thinks it's trading but isn't.

**Why it happens:**
- `create_order()` creates local object only; `create_and_post_order()` actually submits
- `update_balance_allowance()` overwrites CLOB internal state (use `get_balance_allowance()` instead)
- Signature type mismatches (Type 0 EOA vs Type 1 POLY_PROXY vs Type 2 GNOSIS_SAFE) cause silent rejections
- Binance WebSocket drops 2-3 times per 24 hours, sometimes without notification

**Consequences:**
- "Zombie positions" from lost fill notifications during connection hiccups
- CLOB internal state doesn't sync with REST API balance reports
- Bot attempts to trade with stale balance assumptions, causing cascading failures

**Prevention:**
- Always use `create_and_post_order()` for actual submissions
- Implement dual-verification: confirm every order via REST after WebSocket fill notification
- Cache signature type at startup and validate before each trade
- Build heartbeat monitoring for WebSocket connections with auto-reconnect

**Detection:**
- Reconcile local position state with API-reported positions every 60 seconds
- Alert on any state mismatch > $10
- Log all API responses, not just errors

**Phase to address:** Phase 2 (Core Trading Logic)

---

### Pitfall 3: Oracle/Resolution Risk on Large Positions

**What goes wrong:** Markets resolve adversarially due to UMA oracle manipulation. In March 2025, a $7M Polymarket market was flipped by whale voting despite clear "no" outcome.

**Why it happens:**
- UMA token holders vote on disputed outcomes (48-96 hour window)
- 1% of UMA holders control 95% of voting power as of February 2026
- Single whale controlled 25% of votes in the March 2025 incident
- Penalty for incorrect voting is only 0.05%—economically rational to manipulate when position profits exceed penalty

**Consequences:**
- Correct bets resolved as losses
- No recourse—Polymarket refused refunds, stating it wasn't a "system failure"
- Arbitrage positions held overnight exposed to resolution manipulation

**Prevention:**
- Avoid holding positions across resolution windows on markets with < $100k liquidity
- Check voter concentration before entering: avoid if top 10 voters control >60%
- Monitor for large UMA transfers (>1M UMA) preceding dispute windows
- Prefer markets with multi-source resolution (multiple journalists/outlets) over single-source

**Detection:**
- Track "markets approaching resolution" daily
- Alert on any position held within 48 hours of liveness expiration
- Monitor UMA whale wallet movements for coordinated voting signals

**Phase to address:** Phase 4 (Risk Management)

---

### Pitfall 4: Fee Illusion and Negative Expected Value

**What goes wrong:** Apparent arbitrage spread disappears after accounting for all fees. Bot executes "profitable" trades that lose money.

**Why it happens:**
```
Visible Spread:        0.5%
Minus Taker Fees (2x): -0.2%
Minus Gas (Polygon):   -0.15%
Minus Withdrawal Fee:  -0.1%
Minus Slippage:        -0.15%
─────────────────────────────
Actual Profit:        -0.10% (LOSS)
```

**Consequences:**
- Bot appears to have positive win rate but negative PnL
- One production bot spent $8,400 on failed transactions in worst month
- Only 0.006% of 2.4M scanned opportunities were profitable after fees

**Prevention:**
- Calculate "true spread" in real-time including all fees before execution
- Implement minimum profit threshold (e.g., 0.5% after all costs)
- Use maker orders where possible to reduce taker fees
- Track gas prices and pause during congestion spikes

**Detection:**
- Daily reconciliation: gross profit vs net profit after fees
- Alert if fee-to-profit ratio exceeds 30%
- Track failed transaction gas spend separately

**Phase to address:** Phase 2 (Core Trading Logic)

---

### Pitfall 5: API Key Security and Credential Exposure

**What goes wrong:** API keys leaked through `.env` files, browser extensions, or supply chain attacks. Attacker gains trading access or drains funds.

**Why it happens:**
- 81% surge in AI-service credential leaks in 2025 (29M secrets exposed on GitHub)
- Malicious Chrome extensions steal API keys during creation (MEXC API Automator still live on Chrome Web Store)
- AI agents binding to 0.0.0.0 with no authentication
- `.env` files committed to version control or exposed via infostealer malware

**Consequences:**
- Unauthorized trades executed from attacker's location
- API keys used for prompt injection attacks on connected AI systems
- In worst case: withdrawal permissions exploited to drain funds

**Prevention:**
- **Never** store API keys in `.env` files—use runtime injection only
- Create trade-only keys with **no withdrawal permissions**
- Bind all services to 127.0.0.1, never 0.0.0.0
- Enable IP whitelisting on Polymarket API keys
- Rotate keys monthly and audit access logs weekly

**Detection:**
- Monitor for API access from unexpected IP addresses
- Alert on any withdrawal permission attempts
- Use GitGuardian or similar to scan for leaked credentials

**Phase to address:** Phase 1 (Infrastructure Setup)

---

## Moderate Pitfalls

### Pitfall 6: Rate Limit Mismanagement

**What goes wrong:** Bot gets throttled or banned during critical market movements due to aggressive polling.

**Why it happens:**
- Polymarket International API: 15,000 req/10s overall, but trading endpoints have dual limits (burst + sustained)
- `POST /order`: 3,500 req/10s burst, 36,000 req/10min sustained
- Sliding window limits reset unpredictably
- Matching engine restarts return `425 Too Early`

**Consequences:**
- Orders rejected during high-volatility opportunities (exactly when you need execution)
- Exponential backoff during opportunities = missed captures

**Prevention:**
- Use WebSockets for real-time data instead of REST polling
- Implement request queue with rate limit awareness
- Cache reference data (market metadata) with 300s TTL
- Build exponential backoff retry logic for 429/425 responses

**Phase to address:** Phase 2 (Core Trading Logic)

---

### Pitfall 7: Slippage Miscalculation on Order Book Depth

**What goes wrong:** Bot sees $40 spread but order book only has $200 depth. Execution slips through liquidity tiers, erasing profit.

**Why it happens:**
- Bots calculate spread using top-of-book prices only
- Don't account for available volume at each price level
- Larger orders exhaust liquidity and move price against you

**Consequences:**
- "True spread" after slippage is negative even when top-of-book looks profitable
- One-legged trades: buy executes, sell slips through book, left with naked position

**Prevention:**
- Calculate true spread with depth adjustment:
```python
def calculate_true_spread(bid_price_a, ask_price_b, depth_a, depth_b):
    adjusted_a = bid_price_a * (1 - (1 / depth_a))
    adjusted_b = ask_price_b * (1 + (1 / depth_b))
    true_spread = (adjusted_b - adjusted_a) / adjusted_a
    return true_spread
```
- Implement minimum order book depth thresholds per trade size
- Pause trading during volatility spikes when depth evaporates

**Phase to address:** Phase 2 (Core Trading Logic)

---

### Pitfall 8: No Circuit Breakers for Black Swan Events

**What goes wrong:** Bot continues trading during market crashes, API outages, or anomalous spreads—compounding losses instead of pausing.

**Why it happens:**
- Open-source bots prioritize strategy code over risk management
- No daily loss limits or kill switches
- Bot doesn't recognize when "normal" market conditions have broken

**Consequences:**
- One tested bot blew up during volatility spike (no circuit breaker)
- Max daily loss observed: -$380 on $30-50K capital without pause
- Cascading failures from stale data during outages

**Prevention:**
- Implement hard daily loss limit (e.g., -$200 or -2% of capital)
- Build kill switch accessible via Telegram/Discord command
- Pause on API error rate > 10% in 5-minute window
- Halt trading during Polygon network congestion alerts

**Phase to address:** Phase 4 (Risk Management)

---

## Minor Pitfalls

### Pitfall 9: Data Loss from Rotated Log Files

**What goes wrong:** Months of trade history, metrics, and debugging data lost when log files rotate or VPS crashes.

**Prevention:**
- Log everything to a database (PostgreSQL/SQLite) from day one
- Never rely on text files for critical audit trails
- Implement daily database backups to S3 or similar

**Phase to address:** Phase 3 (Observability)

---

### Pitfall 10: Strategy Obsolescence Without Adaptation

**What goes wrong:** Spreads compress over time (1.8% → 0.7% in 6 months for one successful bot). Strategy that worked at launch becomes unprofitable.

**Prevention:**
- Track average spread captured per trade weekly
- Monitor competition level via opportunity capture rate
- Build modular strategy components that can be swapped without full rewrite

**Phase to address:** Phase 5 (Optimization)

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Infrastructure Setup | Latency underestimation, API key exposure | Budget for co-location from day one; runtime secret injection |
| Core Trading Logic | Silent API failures, fee illusion, slippage | Dual-verification on orders; true spread calculation |
| Observability | Data loss to log rotation | Database-backed logging from start |
| Risk Management | No circuit breakers, oracle risk | Daily loss limits; resolution window monitoring |
| Optimization | Strategy obsolescence | Weekly spread tracking; modular architecture |

## Sources

- [Solana arbitrage bot setup: why most fail before they start](https://medium.com/@yavorovych/solana-arbitrage-bot-setup-why-most-fail-before-they-start-1c24d8d72593)
- [Crypto Bot Mistakes Losing You Money 2026](https://xcryptobot.com/blog/crypto-bot-mistakes-losing-you-money-2026)
- [The Arbitrage Bot Arms Race: What We Learned Running FlashArb in Production](https://dev.to/chronocoders/the-arbitrage-bot-arms-race-what-we-learned-running-flasharb-in-production-10ij)
- [Automated Trading Bots for Low-Latency Crypto Arbitrage: 7 Brutal Lessons](https://cc.imporinfo.com/2026/02/automated-trading-bots-for-low-latency.html)
- [Polymarket Has a Bot Problem](https://medium.com/@0xicaruss/polymarket-has-a-bot-problem-i-spent-2-weeks-figuring-out-whos-actually-human-b8aeef1980b2)
- [Before you run a Polymarket bot, read this](https://runtimenotes.com/blog/before-you-run-a-polymarket-bot/)
- [How a Polymarket Arbitrage Bot Made $150K: A Deep Dive](https://agentbets.ai/blog/polymarket-arbitrage-bot-case-study/)
- [Polymarket API Rate Limits Documentation](https://docs.polymarket.com/api-reference/rate-limits)
- [Crypto Tools Under Attack as Apifox Breach Exposes Sensitive Data](https://www.cryptotimes.io/2026/03/26/crypto-tools-under-attack-as-apifox-breach-exposes-sensitive-data/)
- [OpenClaw's 2026 Security Crisis](https://www.apistronghold.com/blog/openclaw-2026-security-crisis-credential-leaks-prompt-injection)
- [Polymarket encounters oracle manipulation attacks](https://www.aicoin.com/en/article/449974)
- [Inside UMA Optimistic Oracle: Resolution Risk Guide](https://settlerisk.com/blog/uma-optimistic-oracle-resolution-risk-guide)
- [Crypto Slippage Explained](https://medium.com/@swaphunt/slippage-in-crypto-swaps-why-your-arbitrage-bot-keeps-crying-and-what-i-did-about-it-e561c0603e86)
