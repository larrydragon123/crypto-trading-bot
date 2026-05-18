import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "trading.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL,
            reason TEXT,
            indicators_json TEXT
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity REAL NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            exit_reason TEXT,
            pnl REAL,
            pnl_pct REAL
        );

        CREATE TABLE IF NOT EXISTS balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            asset TEXT NOT NULL,
            free REAL NOT NULL,
            used REAL NOT NULL,
            total REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            starting_balance REAL,
            ending_balance REAL,
            pnl REAL,
            pnl_pct REAL,
            num_trades INTEGER,
            win_trades INTEGER,
            loss_trades INTEGER
        );

        CREATE TABLE IF NOT EXISTS risk_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()
    conn.close()


def insert_signal(symbol: str, direction: str, price: float, reason: str, indicators: dict):
    conn = get_conn()
    conn.execute(
        "INSERT INTO signals (timestamp, symbol, direction, price, reason, indicators_json) VALUES (?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), symbol, direction, price, reason, json.dumps(indicators))
    )
    conn.commit()
    conn.close()


def open_trade(symbol: str, entry_price: float, quantity: float, side: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO trades (symbol, entry_time, entry_price, quantity, side, status) VALUES (?, ?, ?, ?, ?, 'open')",
        (symbol, datetime.now(timezone.utc).isoformat(), entry_price, quantity, side)
    )
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def close_trade(trade_id: int, exit_price: float, exit_reason: str):
    conn = get_conn()
    trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if not trade:
        conn.close()
        return
    pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
    pnl_pct = (exit_price / trade["entry_price"] - 1) * 100
    conn.execute(
        "UPDATE trades SET exit_time=?, exit_price=?, exit_reason=?, pnl=?, pnl_pct=?, status='closed' WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), exit_price, exit_reason, pnl, pnl_pct, trade_id)
    )
    conn.commit()
    conn.close()


def get_open_trades() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade(trade_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_stops(symbol: str, limit: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE symbol=? AND exit_reason='stop_loss' ORDER BY exit_time DESC LIMIT ?",
        (symbol, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_balance(asset: str, free: float, used: float):
    conn = get_conn()
    conn.execute(
        "INSERT INTO balances (timestamp, asset, free, used, total) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), asset, free, used, free + used)
    )
    conn.commit()
    conn.close()


def update_daily_stats(starting_balance: float):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_conn()
    trades = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) as losses FROM trades WHERE date(exit_time)=? AND status='closed'",
        (today,)
    ).fetchone()
    pnl_row = conn.execute("SELECT COALESCE(SUM(pnl),0) as total_pnl FROM trades WHERE date(exit_time)=? AND status='closed'", (today,)).fetchone()
    conn.execute(
        "INSERT OR REPLACE INTO daily_stats (date, starting_balance, ending_balance, pnl, pnl_pct, num_trades, win_trades, loss_trades) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (today, starting_balance, starting_balance + pnl_row["total_pnl"], pnl_row["total_pnl"], (pnl_row["total_pnl"]/starting_balance)*100 if starting_balance else 0, trades["cnt"], trades["wins"], trades["losses"])
    )
    conn.commit()
    conn.close()


def set_risk_state(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO risk_state (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_risk_state(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT value FROM risk_state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None
