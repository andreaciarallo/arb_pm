# Feature Landscape

**Domain:** Polymarket Arbitrage Trading Bot
**Researched:** 2026-03-27

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Real-time market scanning via WebSocket | Opportunities close in milliseconds; manual scanning impossible | Medium | Must scan 1,500+ markets simultaneously; sub-200ms detection required |
| Automated trade execution | Arbitrage windows close in 15-50ms; manual execution too slow | High | Direct CLOB integration; parallel dual-leg execution |
| YES+NO arbitrage detection | Core Polymarket arbitrage strategy; combined price < $1.00 = guaranteed profit | Medium | Must calculate net profit after fees and gas |
| Fee-aware opportunity scoring | Trading fees (0.01%-0.20%) + gas can erase profits | Medium | Must factor taker/maker fees, Polygon gas, slippage |
| Non-custodial wallet integration | Users must maintain fund control; trust requirement | Medium | MetaMask/WalletConnect; funds stay in user's wallet |
| Position size limits | Prevents overexposure; 0.5-1.5% of capital per trade standard | Low | Configurable max position, max balance utilization (80%) |
| Stop-loss / loss limits | Prevents catastrophic drawdown; 5-8% daily loss limit standard | Low | Hard stops, daily loss circuit breaker |
| PnL tracking (realized/unrealized) | Users need to see performance; basic accountability | Medium | Real-time dashboard with equity, daily PnL, win rate |
| Trade history logging | Audit trail, performance analysis, tax reporting | Low | Timestamped records of all executions |
| Bot status monitoring (active/paused/error) | Users need to know if bot is running | Low | Health checks, auto-restart on failure |
| Telegram/Discord alerts | Industry standard for instant notifications | Low | Opportunity alerts, trade confirmations, error notifications |
| Dry-run / simulation mode | Critical for testing before risking capital | Medium | Must validate logic without live trades |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Sub-50ms detection latency | Outperforms 200ms+ competitors; captures more opportunities | High | Requires optimized RPC endpoints, co-located infrastructure |
| AI/ML opportunity filtering | Filters false positives; ranks high-probability arb opportunities | High | Pattern recognition, confidence scoring (98% accuracy claimed) |
| Cross-platform arbitrage (Polymarket + Kalshi) | Expands opportunity surface beyond single market | High | Multi-exchange integration; higher complexity |
| Momentum strategy engine | Exploits 2-15 second lag between Binance/Polymarket prices | High | Requires external price feed integration; medium risk |
| Market making mode | Place two-sided limit orders; capture bid-ask spread + LP rewards | High | Requires $3k+ capital; advanced strategy |
| Multi-wallet support | Manage multiple trading accounts; diversify execution | Medium | Useful for capital allocation across strategies |
| Gas optimization / tx batching | Smart transaction bundling; maximizes profit after fees | Medium | Polygon-specific optimization |
| 4-level drawdown heat system | Dynamic position sizing based on performance state | Medium | Green/Yellow/Orange/Red states; automatic de-risking |
| Kelly Criterion position sizing | Mathematically optimized sizing; fractional Kelly (0.25-0.35) | Low | More sophisticated than fixed % sizing |
| 15+ independent risk checks per trade | Prevents bad executions; comprehensive safety net | Medium | Liquidity thresholds, spread limits, evidence quality, timeline checks |
| Reactive/proactive hedging | Automatic opposite-side buying when positions move against | High | Cross-asset hedging (BTC/ETH/SOL); 25-35% hedge ratio |
| Custom RPC endpoints | Ultra-low latency; sub-10ms to Polygon blockchain | Medium | Alchemy/QuickNode integration; reduces infrastructure burden |
| Web dashboard with live metrics | Superior UX vs. Telegram-only bots; real-time visibility | Medium | Multi-bot deployment view, backtesting integration |
| REST API access | Programmatic control; webhook notifications | Medium | Enables third-party integrations, custom automation |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Multi-exchange arbitrage (v1) | Adds massive complexity; Polymarket-only focus per project constraints | Build Polymarket mastery first; expand later |
| Manual execution mode | Contradicts "fully automated" core value; slows capture | Fully automated from launch; manual oversight only |
| Serverless deployment | VPS deployment required for continuous 24/7 operation | Deploy to cloud VPS (e.g., AWS EC2, DigitalOcean) |
| Black-box closed source | Reduces trust; users can't verify logic | Open-source core; transparent opportunity detection |
| Overcomplicated strategies (v1) | Complex bots harder to debug; more failure points | Start simple: basic arb → stop-loss → position sizing → advanced |
| High leverage (>5x) | 10x leverage = 5% move wipes 50%; too risky for under $1k capital | No leverage or minimal leverage; focus on guaranteed arb |
| Withdrawal permissions on API keys | Security risk; users should never grant withdrawal access | Trade-only API permissions; funds stay in user wallet |
| Curve-fitted backtesting | Overfitting to historical data = live failure | Use walk-forward analysis; require 30+ days paper trading |
| Public RPC endpoints | Too slow; 100ms+ latency vs 2ms private nodes | Use dedicated RPC endpoints (Alchemy/QuickNode) |
| "Set and forget" design | Markets change, APIs update, liquidity shifts | Build in monitoring, alerts, and weekly review prompts |
| Hardcoded API keys | Security vulnerability; keys exposed in code/repos | Environment variables only; encrypted key storage |
| No rate limit handling | Exchanges throttle/ban IPs exceeding limits | Exponential backoff retry; respect rate limits |

## Feature Dependencies

```
Real-time market scanning → YES+NO arbitrage detection → Fee-aware opportunity scoring → Automated trade execution
                                                                  ↓
Position size limits + Stop-loss limits → Risk management layer → Trade execution safety
                                                                  ↓
Trade history logging → PnL tracking → Dashboard metrics
                                                                  ↓
Dry-run mode → (validates) → All execution logic → Live trading
                                                                  ↓
Telegram/Discord alerts ← (triggered by) → Trade execution + Errors
```

**Infrastructure dependencies:**
```
Dedicated RPC endpoints → Sub-50ms detection latency
Wallet integration → Non-custodial trading → Trade execution
VPS deployment → 24/7 operation → Continuous scanning
```

**Progression dependencies:**
```
Basic arbitrage (v1) → Position sizing (v1.1) → Stop-loss (v1.2) → AI filtering (v2.0)
```

## MVP Recommendation

Prioritize:
1. **Real-time market scanning via WebSocket** — Foundation; without this, no opportunities detected
2. **YES+NO arbitrage detection + fee-aware scoring** — Core value; identifies profitable opportunities
3. **Automated trade execution** — Core value; captures opportunities before they close
4. **Position size limits + stop-loss** — Risk management; prevents catastrophic loss
5. **PnL tracking + trade history** — Accountability; users need to see performance
6. **Dry-run mode** — Safety; validate logic before risking capital
7. **Telegram alerts** — User awareness; trade confirmations and errors

**Defer to v2:**
- **AI/ML filtering** — Adds complexity; basic detection works first
- **Momentum strategy** — Different strategy; focus on arbitrage mastery
- **Market making mode** — Requires $3k+ capital; out of scope for under $1k
- **Cross-platform arbitrage** — Polymarket-only per project constraints
- **REST API access** — Nice-to-have; not core to arbitrage capture
- **Multi-wallet support** — Power user feature; single wallet sufficient for v1
- **Reactive/proactive hedging** — Advanced risk management; adds complexity

## Sources

- [Polymarket Arbitrage Bot Guide 2026](https://www.polytrackhq.app/blog/polymarket-arbitrage-bot-guide)
- [Polymarket Trading Bot — Open Source Features](https://dev.to/benjamin_martin_749c1d57f/polymarket-trading-bot-real-time-arbitrage-momentum-strategies-and-production-features-open-17m1)
- [Risk Management for Polymarket Sniper Bot](https://dev.to/benjamin_martin_749c1d57f/surviving-the-chaos-risk-management-hedging-for-polymarkets-5-minute-endcycle-sniper-bot-4k5e)
- [Common Mistakes to Avoid When Using Crypto Arbitrage Bots](https://sdlccorp.com/post/common-mistakes-to-avoid-when-using-crypto-arbitrage-bots/)
- [Crypto Trading Bot Mistakes to Avoid — Coin Bureau](https://coinbureau.com/guides/crypto-trading-bot-mistakes-to-avoid/)
- [The Arbitrage Bot Arms Race — Production Lessons](https://dev.to/chronocoders/the-arbitrage-bot-arms-race-what-we-learned-running-flasharb-in-production-10ij)
- [Automated Trading Bots for Low-Latency Crypto Arbitrage](https://cc.imporinfo.com/2026/02/automated-trading-bots-for-low-latency.html)
- [Crypto Arbitrage Tools 2025](https://isbglasgow.com/news/crypto-arbitrage-tools-2025)
- [Hummingbot Dashboard](https://hummingbot.org/dashboard)
- [3Commas Grid Bot Statistics](https://help.3commas.io/en/articles/11388471-grid-bot-statistics-page)
- [Arbivex Dashboard Documentation](https://arbivex.com/documentation/understanding-the-arbivex-dashboard/)
