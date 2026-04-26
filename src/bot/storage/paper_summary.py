"""
Paper trade summary query functions.

Pure functions accepting sqlite3.Connection, returning dicts.
All aggregation is by paper_arb_id (D-14) to count complete arb
attempts, not individual legs.
"""
import sqlite3


def get_total_pnl(conn: sqlite3.Connection) -> dict:
    """
    Aggregate total gross P&L, fees, net P&L, and trade count.

    Returns: {"trade_count": int, "total_net_pnl": float,
              "total_fees": float, "total_gross_pnl": float}
    """
    row = conn.execute("""
        SELECT
            COUNT(DISTINCT paper_arb_id) as trade_count,
            COALESCE(SUM(net_pnl_usd), 0.0) as total_net_pnl,
            COALESCE(SUM(estimated_fees_usd), 0.0) as total_fees
        FROM paper_trades
    """).fetchone()
    trade_count = row[0] or 0
    total_net_pnl = round(row[1], 4)
    total_fees = round(row[2], 4)
    return {
        "trade_count": trade_count,
        "total_net_pnl": total_net_pnl,
        "total_fees": total_fees,
        "total_gross_pnl": round(total_net_pnl + total_fees, 4),
    }


def get_win_rate(conn: sqlite3.Connection) -> dict:
    """
    Win rate by opportunity_type.
    A win = paper_arb_id group where sum(net_pnl_usd) > 0 (D-14).

    Returns: {"yes_no": {"total": N, "wins": N, "win_rate": float},
              "cross_market": {...}}
    """
    rows = conn.execute("""
        SELECT
            opportunity_type,
            COUNT(*) as total,
            SUM(CASE WHEN arb_pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM (
            SELECT paper_arb_id, opportunity_type,
                   SUM(net_pnl_usd) as arb_pnl
            FROM paper_trades
            GROUP BY paper_arb_id, opportunity_type
        )
        GROUP BY opportunity_type
    """).fetchall()
    result = {}
    for opp_type, total, wins in rows:
        result[opp_type] = {
            "total": total,
            "wins": wins,
            "win_rate": round(wins / total, 4) if total > 0 else 0.0,
        }
    return result


def get_avg_spread(conn: sqlite3.Connection) -> dict:
    """
    Average net spread captured per arb, grouped by category.

    Computes per-arb net P&L (sum across legs) then averages by category.

    Returns: {"politics": {"avg_spread": float, "arb_count": int}, ...}
    """
    rows = conn.execute("""
        SELECT
            category,
            COUNT(*) as arb_count,
            AVG(arb_pnl) as avg_spread
        FROM (
            SELECT paper_arb_id, category,
                   SUM(net_pnl_usd) as arb_pnl
            FROM paper_trades
            GROUP BY paper_arb_id, category
        )
        GROUP BY category
    """).fetchall()
    result = {}
    for cat, arb_count, avg_spread in rows:
        result[cat] = {
            "arb_count": arb_count,
            "avg_spread": round(avg_spread, 6),
        }
    return result


def get_category_breakdown(conn: sqlite3.Connection) -> list[dict]:
    """
    Per-category breakdown: count, total P&L, avg P&L, win rate.

    Returns: [{"category": str, "arb_count": int, "total_pnl": float,
               "avg_pnl": float, "win_rate": float}, ...]
    """
    rows = conn.execute("""
        SELECT
            category,
            COUNT(*) as arb_count,
            SUM(arb_pnl) as total_pnl,
            AVG(arb_pnl) as avg_pnl,
            SUM(CASE WHEN arb_pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM (
            SELECT paper_arb_id, category,
                   SUM(net_pnl_usd) as arb_pnl
            FROM paper_trades
            GROUP BY paper_arb_id, category
        )
        GROUP BY category
        ORDER BY total_pnl DESC
    """).fetchall()
    result = []
    for cat, arb_count, total_pnl, avg_pnl, wins in rows:
        result.append({
            "category": cat,
            "arb_count": arb_count,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl": round(avg_pnl, 6),
            "win_rate": round(wins / arb_count, 4) if arb_count > 0 else 0.0,
        })
    return result
