"""Crypto Trading Bot Dashboard — FastAPI backend."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Crypto Bot Dashboard")

DB_PATH = Path("/app/data/trading.db")


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@app.get("/api/status")
async def get_status():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT timestamp FROM balances ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"running": False, "mode": "unknown", "last_update": None}

    last_time = datetime.fromisoformat(row["timestamp"])
    now = datetime.now(timezone.utc)
    seconds_ago = (now - last_time).total_seconds()
    running = seconds_ago < 90

    return {
        "running": running,
        "mode": "paper",
        "last_update": row["timestamp"],
        "seconds_ago": round(seconds_ago, 1),
    }


@app.get("/api/balances")
async def get_balances():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT asset, free, used, total
            FROM balances
            WHERE (asset, timestamp) IN (
                SELECT asset, MAX(timestamp) FROM balances GROUP BY asset
            )
        """).fetchall()

        latest = {
            r["asset"]: {
                "free": round(r["free"], 2),
                "used": round(r["used"], 2),
                "total": round(r["total"], 2),
            }
            for r in rows
        }

        history = conn.execute("""
            SELECT timestamp, total FROM balances
            WHERE asset = 'USDT'
            ORDER BY timestamp DESC LIMIT 200
        """).fetchall()
    finally:
        conn.close()

    return {
        "latest": latest,
        "history": [
            {"time": r["timestamp"], "value": round(r["total"], 2)}
            for r in reversed(history)
        ],
    }


@app.get("/api/trades")
async def get_trades(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
):
    conn = get_db()
    try:
        offset = (page - 1) * size
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, symbol, entry_time, exit_time, entry_price, exit_price,
                   quantity, side, status, exit_reason, pnl, pnl_pct
            FROM trades
            ORDER BY entry_time DESC
            LIMIT ? OFFSET ?
            """,
            (size, offset),
        ).fetchall()
    finally:
        conn.close()

    trades = []
    for r in rows:
        t = dict(r)
        if t["pnl"] is not None:
            t["pnl"] = round(t["pnl"], 2)
        if t["pnl_pct"] is not None:
            t["pnl_pct"] = round(t["pnl_pct"], 2)
        trades.append(t)

    return {"trades": trades, "total": total, "page": page, "size": size}


@app.get("/api/stats")
async def get_stats():
    conn = get_db()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_stats = conn.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (today,)
        ).fetchone()

        all_time = conn.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                COALESCE(SUM(pnl), 0) as total_pnl
            FROM trades WHERE status = 'closed'
        """).fetchone()
    finally:
        conn.close()

    total_trades = all_time["total_trades"] or 0
    wins = all_time["wins"] or 0

    return {
        "today": dict(today_stats) if today_stats else None,
        "all_time": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": total_trades - wins,
            "total_pnl": round(all_time["total_pnl"], 2),
            "win_rate": round(wins / total_trades * 100, 1) if total_trades else 0,
        },
    }


@app.get("/api/positions")
async def get_positions():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, symbol, entry_price, quantity, entry_time, side "
            "FROM trades WHERE status = 'open'"
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": r["id"],
            "symbol": r["symbol"],
            "entry_price": r["entry_price"],
            "quantity": r["quantity"],
            "entry_time": r["entry_time"],
            "side": r["side"],
        }
        for r in rows
    ]


static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
