"""
SQLite schema for the Polymarket arbitrage bot opportunities log.

All detected opportunities are stored here during dry-run (Phase 2) and
live trading (Phase 3+). Schema is designed for easy post-run analysis.

Key columns indexed for fast querying (D-17):
- detected_at: time-range queries
- category: filter by market type
- opportunity_type: filter by arb strategy
"""
import sqlite3

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    opportunity_type TEXT NOT NULL,
    category TEXT NOT NULL,
    yes_ask REAL,
    no_ask REAL,
    gross_spread REAL NOT NULL,
    estimated_fees REAL NOT NULL,
    net_spread REAL NOT NULL,
    depth REAL NOT NULL,
    vwap_yes REAL,
    vwap_no REAL,
    confidence_score REAL,
    detected_at TEXT NOT NULL,
    source TEXT DEFAULT 'websocket'
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_detected_at ON opportunities(detected_at)",
    "CREATE INDEX IF NOT EXISTS idx_category ON opportunities(category)",
    "CREATE INDEX IF NOT EXISTS idx_opportunity_type ON opportunities(opportunity_type)",
]

_INSERT_OPPORTUNITY = """
INSERT INTO opportunities (
    market_id, market_question, opportunity_type, category,
    yes_ask, no_ask, gross_spread, estimated_fees, net_spread,
    depth, vwap_yes, vwap_no, confidence_score, detected_at, source
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """
    Initialize the SQLite database and return an open connection.

    Creates the opportunities table and indexes if they don't exist.
    Safe to call on an existing database — uses IF NOT EXISTS.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(_CREATE_TABLE)
    for idx_sql in _CREATE_INDEXES:
        conn.execute(idx_sql)
    conn.commit()
    return conn


def insert_opportunity(conn: sqlite3.Connection, opp) -> None:
    """Insert one ArbitrageOpportunity row into the opportunities table."""
    conn.execute(_INSERT_OPPORTUNITY, (
        opp.market_id,
        opp.market_question,
        opp.opportunity_type,
        opp.category,
        opp.yes_ask,
        opp.no_ask,
        opp.gross_spread,
        opp.estimated_fees,
        opp.net_spread,
        opp.depth,
        opp.vwap_yes,
        opp.vwap_no,
        opp.confidence_score,
        opp.detected_at.isoformat(),
        "websocket",
    ))
    conn.commit()


# ---------------------------------------------------------------------------
# Phase 3: Trades table — records every order attempt (success and failure)
# ---------------------------------------------------------------------------

_CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    leg TEXT NOT NULL,
    side TEXT NOT NULL,
    token_id TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    size_filled REAL NOT NULL DEFAULT 0.0,
    fees_usd REAL NOT NULL DEFAULT 0.0,
    net_pnl REAL,
    order_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    kelly_size REAL,
    vwap_price REAL,
    submitted_at TEXT NOT NULL,
    filled_at TEXT,
    error_msg TEXT
)
"""

_CREATE_TRADES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_market_id ON trades(market_id)",
    "CREATE INDEX IF NOT EXISTS idx_trades_submitted_at ON trades(submitted_at)",
    "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)",
]

_INSERT_TRADE = """
INSERT OR IGNORE INTO trades (
    trade_id, market_id, market_question, leg, side, token_id,
    price, size, size_filled, fees_usd, order_id, status,
    kelly_size, vwap_price, submitted_at, error_msg
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_trades_table(conn: sqlite3.Connection) -> None:
    """
    Create the trades table and indexes if they don't exist.
    Called from live_run.py init — safe on existing database.
    """
    conn.execute(_CREATE_TRADES_TABLE)
    for idx_sql in _CREATE_TRADES_INDEXES:
        conn.execute(idx_sql)
    conn.commit()


def insert_trade(
    conn: sqlite3.Connection,
    result,
    market_question: str,
    trade_id: str,
) -> None:
    """
    Insert one ExecutionResult into the trades table.
    Uses INSERT OR IGNORE to prevent duplicate trade_id constraint errors.
    Called for EVERY order attempt including failures (status='failed').
    """
    from datetime import datetime
    conn.execute(_INSERT_TRADE, (
        trade_id,
        result.market_id,
        market_question,
        result.leg,
        result.side,
        result.token_id,
        result.price,
        result.size,
        result.size_filled,
        0.0,                    # fees_usd — Phase 4 will compute actual fees
        result.order_id,
        result.status,
        result.kelly_size_usd,
        result.vwap_price,
        datetime.utcnow().isoformat(),
        result.error_msg,
    ))
    conn.commit()
