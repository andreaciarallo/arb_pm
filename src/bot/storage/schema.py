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
    fees_usd: float = 0.0,
) -> None:
    """
    Insert one ExecutionResult into the trades table.
    Uses INSERT OR IGNORE to prevent duplicate trade_id constraint errors.
    Called for EVERY order attempt including failures (status='failed').

    fees_usd: Computed at fill time by caller using get_taker_fee() (D-13).
              Defaults to 0.0 for backwards compatibility.
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
        fees_usd,              # was: 0.0  — Phase 4 fix (D-13)
        result.order_id,
        result.status,
        result.kelly_size_usd,
        result.vwap_price,
        datetime.utcnow().isoformat(),
        result.error_msg,
    ))
    conn.commit()


# ---------------------------------------------------------------------------
# Phase 4: arb_pairs table — per-arb analytics after both legs confirmed (OBS-04)
# Row written ONLY after both YES and NO legs are confirmed filled (D-12).
# One-leg failures (hedge path) do NOT write here — stays in trades only.
# ---------------------------------------------------------------------------

_CREATE_ARB_PAIRS_TABLE = """
CREATE TABLE IF NOT EXISTS arb_pairs (
    arb_id TEXT PRIMARY KEY,
    yes_trade_id TEXT NOT NULL,
    no_trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    yes_entry_price REAL,
    no_entry_price REAL,
    size_usd REAL,
    gross_pnl REAL,
    fees_usd REAL,
    net_pnl REAL,
    entry_time TEXT,
    exit_time TEXT,
    hold_seconds REAL
)
"""

_CREATE_ARB_PAIRS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_arb_pairs_market_id ON arb_pairs(market_id)",
    "CREATE INDEX IF NOT EXISTS idx_arb_pairs_entry_time ON arb_pairs(entry_time)",
]

_INSERT_ARB_PAIR = """
INSERT OR IGNORE INTO arb_pairs (
    arb_id, yes_trade_id, no_trade_id, market_id, market_question,
    yes_entry_price, no_entry_price, size_usd, gross_pnl, fees_usd,
    net_pnl, entry_time, exit_time, hold_seconds
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def init_arb_pairs_table(conn: sqlite3.Connection) -> None:
    """
    Create the arb_pairs table and indexes if they don't exist.
    Called from live_run.py init alongside init_trades_table().
    Safe to call on existing database — uses IF NOT EXISTS.
    """
    conn.execute(_CREATE_ARB_PAIRS_TABLE)
    for idx_sql in _CREATE_ARB_PAIRS_INDEXES:
        conn.execute(idx_sql)
    conn.commit()


def insert_arb_pair(conn: sqlite3.Connection, pair: dict) -> None:
    """
    Insert one completed arb pair into the arb_pairs table.

    Called ONLY after both YES and NO legs are confirmed filled (D-12).
    One-leg failures (hedge path) must NOT call this function.

    pair dict must contain all 14 keys:
        arb_id, yes_trade_id, no_trade_id, market_id, market_question,
        yes_entry_price, no_entry_price, size_usd, gross_pnl, fees_usd,
        net_pnl, entry_time, exit_time, hold_seconds
    """
    conn.execute(_INSERT_ARB_PAIR, (
        pair["arb_id"],
        pair["yes_trade_id"],
        pair["no_trade_id"],
        pair["market_id"],
        pair["market_question"],
        pair["yes_entry_price"],
        pair["no_entry_price"],
        pair["size_usd"],
        pair["gross_pnl"],
        pair["fees_usd"],
        pair["net_pnl"],
        pair["entry_time"],
        pair["exit_time"],
        pair["hold_seconds"],
    ))
    conn.commit()
