"""
ArbitrageOpportunity dataclass.

Represents a detected arbitrage opportunity before execution.
Structured for direct insertion into the SQLite opportunities table.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArbitrageOpportunity:
    market_id: str              # condition_id from CLOB API
    market_question: str
    opportunity_type: str       # "yes_no" | "cross_market"
    category: str               # "crypto" | "geopolitics" | "sports" | "politics" | "other"
    yes_ask: float              # CLOB ask price for YES token (D-05)
    no_ask: float               # CLOB ask price for NO token (D-05)
    gross_spread: float         # 1.0 - yes_ask - no_ask
    estimated_fees: float       # total fees both sides
    net_spread: float           # gross_spread - estimated_fees
    depth: float                # min(yes_depth, no_depth) USD
    vwap_yes: float             # VWAP ask for YES (= yes_ask for now, refined in Phase 3)
    vwap_no: float              # VWAP ask for NO
    confidence_score: float     # 0.0-1.0 quality proxy
    detected_at: datetime
