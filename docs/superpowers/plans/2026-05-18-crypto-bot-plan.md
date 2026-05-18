# Crypto Trading Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated mean-reversion trading bot for BTC/ETH spot on OKX with paper/live dual mode.

**Architecture:** Modular pipeline: Data Feed -> Signal Engine -> Risk Manager -> Execution Broker. Async main loop runs every 1 minute. PaperBroker and LiveBroker share a common interface for seamless mode switching.

**Tech Stack:** Python 3.11+, CCXT 4.x, Pandas + pandas-ta, APScheduler, SQLite, python-telegram-bot, Docker

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `crypto_bot/requirements.txt`
- Create: `crypto_bot/config.yaml`
- Create: `crypto_bot/config.py`
- Create: `crypto_bot/__init__.py`
- Create: `crypto_bot/data/__init__.py`
- Create: `crypto_bot/strategy/__init__.py`
- Create: `crypto_bot/risk/__init__.py`
- Create: `crypto_bot/execution/__init__.py`
- Create: `crypto_bot/notify/__init__.py`
- Create: `crypto_bot/backtest/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```txt
ccxt>=4.0.0
pandas>=2.0.0
pandas-ta>=0.3.14b
pyyaml>=6.0
python-telegram-bot>=20.0
apscheduler>=3.10.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: Create config.yaml**

```yaml
mode: paper  # paper | live

exchange:
  name: okx
  testnet: true  # true for paper mode testnet

trading:
  symbols:
    - BTC/USDT
    - ETH/USDT
  timeframe: 1h
  trend_timeframe: 4h

strategy:
  bb_period: 20
  bb_std: 2.0
  rsi_period: 14
  rsi_oversold: 35
  rsi_overbought: 55
  ema_period: 200
  atr_period: 14
  atr_stop_multiplier: 2.0
  volume_ratio_threshold: 1.2
  max_hold_hours: 72

risk:
  position_size_min: 0.10
  position_size_max: 0.20
  max_positions: 2
  daily_loss_limit: 0.05
  consecutive_stop_limit: 3
  cooldown_hours: 4
  min_usdt_ratio: 0.30
  slippage_max: 0.003
  extreme_volatility_threshold: 0.10

notify:
  telegram:
    enabled: false
    token: ""
    chat_id: ""
```

- [ ] **Step 3: Create config.py**

```python
import os
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config

def get_config() -> dict:
    cfg = load_config()
    # Override from environment
    cfg["exchange"]["api_key"] = os.getenv("OKX_API_KEY", "")
    cfg["exchange"]["secret"] = os.getenv("OKX_SECRET", "")
    cfg["exchange"]["password"] = os.getenv("OKX_PASSWORD", "")
    cfg["notify"]["telegram"]["token"] = os.getenv("TG_BOT_TOKEN", cfg["notify"]["telegram"]["token"])
    cfg["notify"]["telegram"]["chat_id"] = os.getenv("TG_CHAT_ID", cfg["notify"]["telegram"]["chat_id"])
    return cfg
```

- [ ] **Step 4: Create all __init__.py files (empty)**

Run: `touch crypto_bot/__init__.py crypto_bot/data/__init__.py crypto_bot/strategy/__init__.py crypto_bot/risk/__init__.py crypto_bot/execution/__init__.py crypto_bot/notify/__init__.py crypto_bot/backtest/__init__.py`

- [ ] **Step 5: Install dependencies and verify config loads**

Run: `pip install -r crypto_bot/requirements.txt && python -c "from crypto_bot.config import get_config; print(get_config()['mode'])"`
Expected: prints `paper`

- [ ] **Step 6: Commit**

```bash
git add crypto_bot/
git commit -m "feat: project scaffold with config and dependencies"
```

---

### Task 2: SQLite storage layer

**Files:**
- Create: `crypto_bot/data/storage.py`

- [ ] **Step 1: Write storage module**

```python
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "trading.db"

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
```

- [ ] **Step 2: Verify storage works**

Run: `python -c "from crypto_bot.data.storage import init_db; init_db(); print('DB OK')"`
Expected: prints `DB OK` and creates `crypto_bot/trading.db`

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/data/storage.py crypto_bot/.gitignore
echo "trading.db" >> crypto_bot/.gitignore
git add crypto_bot/.gitignore
git commit -m "feat: SQLite storage layer for trades, signals, balances"
```

---

### Task 3: Technical indicators

**Files:**
- Create: `crypto_bot/strategy/indicators.py`

- [ ] **Step 1: Write indicators module**

```python
import pandas as pd
import pandas_ta as ta


def compute_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Compute all indicators on OHLCV DataFrame. Destructive — adds columns in-place."""
    strat = cfg["strategy"]
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]

    bb = ta.bbands(close, length=strat["bb_period"], std=strat["bb_std"])
    df["bb_lower"] = bb[f"BBL_{strat['bb_period']}_{strat['bb_std']}"]
    df["bb_mid"] = bb[f"BBM_{strat['bb_period']}_{strat['bb_std']}"]
    df["bb_upper"] = bb[f"BBU_{strat['bb_period']}_{strat['bb_std']}"]

    df["rsi"] = ta.rsi(close, length=strat["rsi_period"])
    df["ema"] = ta.ema(close, length=strat["ema_period"])
    df["atr"] = ta.atr(high, low, close, length=strat["atr_period"])
    df["vol_sma"] = vol.rolling(window=20).mean()
    df["vol_ratio"] = vol / df["vol_sma"]

    df["price_change_1h"] = close.pct_change(periods=1)

    return df
```

- [ ] **Step 2: Quick smoke test**

Run:
```python
python -c "
import pandas as pd
import numpy as np
from crypto_bot.strategy.indicators import compute_indicators

np.random.seed(42)
df = pd.DataFrame({
    'open': np.linspace(100, 110, 200),
    'high': np.linspace(102, 112, 200) + np.random.randn(200)*0.5,
    'low': np.linspace(98, 108, 200) - np.random.randn(200)*0.5,
    'close': np.linspace(100, 110, 200) + np.random.randn(200),
    'volume': np.random.uniform(100, 1000, 200),
})
cfg = {'strategy': {'bb_period': 20, 'bb_std': 2.0, 'rsi_period': 14, 'ema_period': 200, 'atr_period': 14}}
result = compute_indicators(df, cfg)
print('Columns:', list(result.columns))
print('Last RSI:', result['rsi'].iloc[-1])
"
```
Expected: prints all column names and a valid RSI value

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/strategy/indicators.py
git commit -m "feat: technical indicators (BB, RSI, EMA, ATR)"
```

---

### Task 4: Signal engine

**Files:**
- Create: `crypto_bot/strategy/signals.py`

- [ ] **Step 1: Write signals module**

```python
from dataclasses import dataclass
from datetime import datetime, timezone
import pandas as pd


@dataclass
class Signal:
    symbol: str
    direction: str  # "buy" | "sell"
    price: float
    reason: str
    indicators: dict


def check_entry(df_1h: pd.DataFrame, df_4h: pd.DataFrame, symbol: str, cfg: dict) -> Signal | None:
    """Check entry conditions on latest candle. Returns Signal or None."""
    if len(df_1h) < 201 or len(df_4h) < 201:
        return None

    row = df_1h.iloc[-1]
    row_4h = df_4h.iloc[-1]

    price = row["close"]
    indicators = {
        "bb_lower": row["bb_lower"],
        "bb_mid": row["bb_mid"],
        "rsi": row["rsi"],
        "ema_4h": row_4h["ema"],
        "vol_ratio": row["vol_ratio"],
    }

    # Condition 1: Oversold
    if not (price <= row["bb_lower"] and row["rsi"] < cfg["strategy"]["rsi_oversold"]):
        return None

    # Condition 2: Trend filter (4h close > EMA 200)
    if not (row_4h["close"] > row_4h["ema"]):
        return None

    # Condition 3: Volume confirmation
    if not (row["vol_ratio"] > cfg["strategy"]["volume_ratio_threshold"]):
        return None

    return Signal(
        symbol=symbol,
        direction="buy",
        price=price,
        reason="entry_oversold",
        indicators=indicators,
    )


def check_exit(trade: dict, df_1h: pd.DataFrame, cfg: dict) -> Signal | None:
    """Check exit conditions for an open trade. Returns Signal or None."""
    if len(df_1h) < 201:
        return None

    row = df_1h.iloc[-1]
    price = row["close"]
    entry_price = trade["entry_price"]
    entry_time = datetime.fromisoformat(trade["entry_time"])

    # Stop loss
    stop_price = entry_price - cfg["strategy"]["atr_stop_multiplier"] * row["atr"]
    if price <= stop_price:
        return Signal(
            symbol=trade["symbol"],
            direction="sell",
            price=price,
            reason="stop_loss",
            indicators={"stop_price": stop_price, "atr": row["atr"]},
        )

    # Take profit
    if price >= row["bb_mid"] and row["rsi"] > cfg["strategy"]["rsi_overbought"]:
        return Signal(
            symbol=trade["symbol"],
            direction="sell",
            price=price,
            reason="take_profit",
            indicators={"bb_mid": row["bb_mid"], "rsi": row["rsi"]},
        )

    # Time stop
    hours_held = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
    if hours_held > cfg["strategy"]["max_hold_hours"]:
        return Signal(
            symbol=trade["symbol"],
            direction="sell",
            price=price,
            reason="time_stop",
            indicators={"hours_held": hours_held},
        )

    return None
```

- [ ] **Step 2: Smoke test entry/exit logic**

Run:
```python
python -c "
import pandas as pd
import numpy as np
from crypto_bot.strategy.indicators import compute_indicators
from crypto_bot.strategy.signals import check_entry, check_exit

cfg = {'strategy': {'bb_period': 20, 'bb_std': 2.0, 'rsi_period': 14, 'rsi_oversold': 35, 'rsi_overbought': 55, 'ema_period': 200, 'atr_period': 14, 'atr_stop_multiplier': 2.0, 'volume_ratio_threshold': 1.2, 'max_hold_hours': 72}}

# Build 1h data with a dip
close = np.concatenate([np.linspace(100, 90, 150), np.linspace(90, 85, 50)])
high = close + np.random.uniform(1, 3, 200)
low = close - np.random.uniform(1, 3, 200)
df_1h = pd.DataFrame({'open': close, 'high': high, 'low': low, 'close': close, 'volume': np.random.uniform(500, 1000, 200)})
df_1h = compute_indicators(df_1h, cfg)

# 4h data trending up
close_4h = np.linspace(90, 110, 210)
df_4h = pd.DataFrame({'open': close_4h, 'high': close_4h*1.02, 'low': close_4h*0.98, 'close': close_4h, 'volume': np.random.uniform(500, 2000, 210)})
df_4h = compute_indicators(df_4h, cfg)

# Force oversold on last candle
df_1h.loc[df_1h.index[-1], 'close'] = df_1h.loc[df_1h.index[-1], 'bb_lower'] - 0.5
df_1h.loc[df_1h.index[-1], 'rsi'] = 25
df_1h.loc[df_1h.index[-1], 'vol_ratio'] = 1.5
df_4h.loc[df_4h.index[-1], 'close'] = df_4h.loc[df_4h.index[-1], 'ema'] + 1

signal = check_entry(df_1h, df_4h, 'BTC/USDT', cfg)
print('Entry signal:', signal)
# Should be non-None
assert signal is not None
assert signal.direction == 'buy'
print('Entry test PASSED')

# Test exit
df_1h.loc[df_1h.index[-1], 'close'] = df_1h.loc[df_1h.index[-1], 'bb_mid'] + 1
df_1h.loc[df_1h.index[-1], 'rsi'] = 60
from datetime import datetime, timezone, timedelta
trade = {'symbol': 'BTC/USDT', 'entry_price': 86.0, 'entry_time': (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()}
exit_signal = check_exit(trade, df_1h, cfg)
assert exit_signal is not None
assert exit_signal.reason == 'take_profit'
print('Exit test PASSED')
"
```
Expected: `Entry test PASSED` and `Exit test PASSED`

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/strategy/signals.py
git commit -m "feat: signal engine with entry/exit logic"
```

---

### Task 5: Risk manager

**Files:**
- Create: `crypto_bot/risk/manager.py`

- [ ] **Step 1: Write risk manager**

```python
from datetime import datetime, timezone, timedelta
from crypto_bot.data.storage import get_open_trades, get_recent_stops, get_risk_state, set_risk_state


def can_open_position(symbol: str, balance_usdt: float, cfg: dict) -> tuple[bool, str]:
    """Check all risk constraints. Returns (allowed, reason)."""
    risk = cfg["risk"]

    # Check max positions
    open_trades = get_open_trades()
    if len(open_trades) >= risk["max_positions"]:
        return False, "max_positions_reached"

    # Check same symbol already open
    for t in open_trades:
        if t["symbol"] == symbol:
            return False, "symbol_already_open"

    # Check daily loss limit
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl_key = f"daily_pnl_{today_str}"
    daily_pnl = float(get_risk_state(daily_pnl_key) or 0)
    if daily_pnl <= -balance_usdt * risk["daily_loss_limit"]:
        return False, "daily_loss_limit"

    # Check cooldown
    cooldown_until = get_risk_state("cooldown_until")
    if cooldown_until:
        if datetime.now(timezone.utc) < datetime.fromisoformat(cooldown_until):
            return False, "cooldown_active"

    # Check min USDT reserve
    used = sum(t["entry_price"] * t["quantity"] for t in open_trades)
    if balance_usdt - used < balance_usdt * risk["min_usdt_ratio"]:
        return False, "min_usdt_reserve"

    return True, "ok"


def calculate_position_size(symbol: str, balance_usdt: float, price: float, atr: float, cfg: dict) -> float:
    """Calculate position size in quote currency, scaled by ATR volatility."""
    risk = cfg["risk"]
    # Base size at midpoint of min/max
    base_ratio = (risk["position_size_min"] + risk["position_size_max"]) / 2
    # Scale down when ATR is high relative to price
    vol_ratio = atr / price
    if vol_ratio > 0.05:
        scale = 0.5
    elif vol_ratio > 0.03:
        scale = 0.75
    else:
        scale = 1.0
    ratio = base_ratio * scale
    ratio = max(risk["position_size_min"], min(risk["position_size_max"], ratio))
    return balance_usdt * ratio


def check_extreme_volatility(df_1h: pd.DataFrame, cfg: dict) -> bool:
    """Check if last hour price change exceeds extreme threshold."""
    if len(df_1h) < 2:
        return False
    change = abs(df_1h.iloc[-1]["price_change_1h"])
    return change > cfg["risk"]["extreme_volatility_threshold"]


def handle_stop_loss(trade_id: int, symbol: str):
    """Record stop loss and check cooldown trigger."""
    stops = get_recent_stops(symbol, limit=10)
    if len(stops) >= 3:
        is_consecutive = True
        # Check if last 3 exit times are within recent cooldown window
        for s in stops[:3]:
            exit_time = datetime.fromisoformat(s["exit_time"])
            if (datetime.now(timezone.utc) - exit_time).total_seconds() > 86400:
                is_consecutive = False
                break
        if is_consecutive:
            cooldown_until = datetime.now(timezone.utc) + timedelta(hours=4)
            set_risk_state("cooldown_until", cooldown_until.isoformat())


def record_daily_pnl(pnl: float):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"daily_pnl_{today_str}"
    current = float(get_risk_state(key) or 0)
    set_risk_state(key, str(current + pnl))
```

- [ ] **Step 2: Smoke test risk manager**

Run:
```python
python -c "
from crypto_bot.data.storage import init_db, open_trade
from crypto_bot.risk.manager import can_open_position, calculate_position_size, check_extreme_volatility
import pandas as pd

init_db()

cfg = {'risk': {'position_size_min': 0.10, 'position_size_max': 0.20, 'max_positions': 2, 'daily_loss_limit': 0.05, 'consecutive_stop_limit': 3, 'cooldown_hours': 4, 'min_usdt_ratio': 0.30, 'slippage_max': 0.003, 'extreme_volatility_threshold': 0.10}}

# Test 1: Can open with no positions
ok, reason = can_open_position('BTC/USDT', 5000, cfg)
assert ok, f'Should allow: {reason}'
print('Test 1 PASSED: Can open with no positions')

# Test 2: Position size calculation
size = calculate_position_size('BTC/USDT', 5000, 90000, 1800, cfg)
assert 500 <= size <= 1000, f'Size {size} out of range'
print(f'Test 2 PASSED: Position size = {size:.2f} USDT')

# Test 3: Extreme volatility check
df = pd.DataFrame({'price_change_1h': [0.0, -0.15]})
assert check_extreme_volatility(df, cfg)
print('Test 3 PASSED: Extreme volatility detected')
"
```
Expected: All 3 tests PASSED

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/risk/manager.py
git commit -m "feat: risk manager with position sizing and cooldown"
```

---

### Task 6: Broker base class and PaperBroker

**Files:**
- Create: `crypto_bot/execution/base.py`
- Create: `crypto_bot/execution/paper.py`

- [ ] **Step 1: Write base class**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderResult:
    success: bool
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    error: str = ""


class BaseBroker(ABC):

    @abstractmethod
    def get_balance(self, asset: str) -> dict:
        """Return {'free': float, 'used': float, 'total': float}"""
        ...

    @abstractmethod
    def market_buy(self, symbol: str, amount_usdt: float) -> OrderResult:
        ...

    @abstractmethod
    def market_sell(self, symbol: str, amount_coin: float) -> OrderResult:
        ...

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[list]:
        ...
```

- [ ] **Step 2: Write PaperBroker**

```python
import time
from crypto_bot.execution.base import BaseBroker, OrderResult
from crypto_bot.data.storage import record_balance


class PaperBroker(BaseBroker):
    """Simulated broker using real market prices."""

    def __init__(self, initial_balance: float = 5000):
        self.balances = {
            "USDT": {"free": initial_balance, "used": 0, "total": initial_balance},
            "BTC": {"free": 0, "used": 0, "total": 0},
            "ETH": {"free": 0, "used": 0, "total": 0},
        }
        self._prices: dict[str, float] = {}
        self._order_counter = 0
        self._exchange = None  # will be set for price fetch

    def set_exchange(self, exchange):
        self._exchange = exchange

    def update_price(self, symbol: str, price: float):
        self._prices[symbol] = price

    def get_balance(self, asset: str) -> dict:
        return self.balances.get(asset, {"free": 0, "used": 0, "total": 0})

    def market_buy(self, symbol: str, amount_usdt: float) -> OrderResult:
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "buy", 0, 0, 0, "no price data")

        usdt_bal = self.balances["USDT"]["free"]
        if amount_usdt > usdt_bal:
            amount_usdt = usdt_bal

        fee_rate = 0.001  # Taker fee
        gross = amount_usdt / price
        fee = gross * fee_rate
        net = gross - fee

        self.balances["USDT"]["free"] -= amount_usdt
        self.balances["USDT"]["total"] = self.balances["USDT"]["free"] + self.balances["USDT"]["used"]
        self.balances[base]["free"] += net
        self.balances[base]["total"] = self.balances[base]["free"] + self.balances[base]["used"]

        self._order_counter += 1
        record_balance("USDT", self.balances["USDT"]["free"], self.balances["USDT"]["used"])
        record_balance(base, self.balances[base]["free"], self.balances[base]["used"])

        return OrderResult(True, f"paper_{self._order_counter}", symbol, "buy", price, net, fee * price)

    def market_sell(self, symbol: str, amount_coin: float | None = None) -> OrderResult:
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "sell", 0, 0, 0, "no price data")

        coin_bal = self.balances[base]["free"]
        if amount_coin is None or amount_coin > coin_bal:
            amount_coin = coin_bal

        fee_rate = 0.001
        gross = amount_coin * price
        fee = gross * fee_rate
        net = gross - fee

        self.balances[base]["free"] -= amount_coin
        self.balances[base]["total"] = self.balances[base]["free"] + self.balances[base]["used"]
        self.balances["USDT"]["free"] += net
        self.balances["USDT"]["total"] = self.balances["USDT"]["free"] + self.balances["USDT"]["used"]

        self._order_counter += 1
        record_balance("USDT", self.balances["USDT"]["free"], self.balances["USDT"]["used"])
        record_balance(base, self.balances[base]["free"], self.balances[base]["used"])

        return OrderResult(True, f"paper_{self._order_counter}", symbol, "sell", price, amount_coin, fee)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[list]:
        if self._exchange:
            return self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return []
```

- [ ] **Step 3: Smoke test PaperBroker**

Run:
```python
python -c "
from crypto_bot.execution.paper import PaperBroker
from crypto_bot.data.storage import init_db

init_db()
broker = PaperBroker(initial_balance=5000)
broker.update_price('BTC/USDT', 90000)

result = broker.market_buy('BTC/USDT', 500)
assert result.success, f'Buy failed: {result.error}'
print(f'Bought {result.quantity:.6f} BTC at {result.price}')

bal = broker.get_balance('USDT')
print(f'USDT remaining: {bal[\"free\"]:.2f}')

result2 = broker.market_sell('BTC/USDT')
assert result2.success
print(f'Sold {result2.quantity:.6f} BTC')
print('PaperBroker test PASSED')
"
```
Expected: prints buy/sell confirmations and PASSED

- [ ] **Step 4: Commit**

```bash
git add crypto_bot/execution/base.py crypto_bot/execution/paper.py
git commit -m "feat: broker base class and paper trading broker"
```

---

### Task 7: Live broker (OKX via CCXT)

**Files:**
- Create: `crypto_bot/execution/live.py`

- [ ] **Step 1: Write LiveBroker**

```python
import ccxt
from crypto_bot.execution.base import BaseBroker, OrderResult


class LiveBroker(BaseBroker):
    """Real OKX trading via CCXT."""

    def __init__(self, cfg: dict):
        ex = cfg["exchange"]
        self._exchange = ccxt.okx({
            "apiKey": ex.get("api_key", ""),
            "secret": ex.get("secret", ""),
            "password": ex.get("password", ""),
            "enableRateLimit": True,
        })
        if ex.get("testnet"):
            self._exchange.set_sandbox_mode(True)
        self._exchange.load_markets()
        self._slippage_max = cfg["risk"]["slippage_max"]

    def get_balance(self, asset: str) -> dict:
        try:
            bal = self._exchange.fetch_balance()
            t = bal.get(asset, {})
            return {"free": t.get("free", 0), "used": t.get("used", 0), "total": t.get("total", 0)}
        except Exception:
            return {"free": 0, "used": 0, "total": 0}

    def market_buy(self, symbol: str, amount_usdt: float) -> OrderResult:
        try:
            ticker = self._exchange.fetch_ticker(symbol)
            price = ticker["last"]
            amount = amount_usdt / price
            order = self._exchange.create_market_buy_order(symbol, amount)
            fee = order.get("fee", {}).get("cost", amount * price * 0.001)
            return OrderResult(True, order["id"], symbol, "buy", order["average"] or price, order["filled"], fee)
        except Exception as e:
            return OrderResult(False, "", symbol, "buy", 0, 0, 0, str(e))

    def market_sell(self, symbol: str, amount_coin: float) -> OrderResult:
        try:
            order = self._exchange.create_market_sell_order(symbol, amount_coin)
            fee = order.get("fee", {}).get("cost", 0)
            return OrderResult(True, order["id"], symbol, "sell", order["average"] or 0, order["filled"], fee)
        except Exception as e:
            return OrderResult(False, "", symbol, "sell", 0, 0, 0, str(e))

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[list]:
        return self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    @property
    def exchange(self):
        return self._exchange
```

- [ ] **Step 2: Commit**

```bash
git add crypto_bot/execution/live.py
git commit -m "feat: live broker via CCXT for OKX"
```

---

### Task 8: OKX data feed

**Files:**
- Create: `crypto_bot/data/feed.py`

- [ ] **Step 1: Write data feed module**

```python
import asyncio
import logging
import pandas as pd
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DataFeed:
    """Fetches OHLCV data from OKX via REST for backtesting and live trading."""

    def __init__(self, exchange):
        self._exchange = exchange
        self._cache: dict[str, dict[str, pd.DataFrame]] = {}

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
        """Fetch OHLCV and return as DataFrame with computed indicators."""
        raw = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)
        return df

    def get_dataframe(self, symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
        return self.fetch_ohlcv(symbol, timeframe, limit=limit)

    def get_latest_price(self, symbol: str) -> float:
        ticker = self._exchange.fetch_ticker(symbol)
        return ticker["last"]


async def fetch_with_retry(exchange, symbol: str, timeframe: str, limit: int = 300, max_retries: int = 3) -> pd.DataFrame:
    """Fetch OHLCV with exponential backoff retry."""
    delay = 5
    for attempt in range(max_retries):
        try:
            raw = await asyncio.to_thread(exchange.fetch_ohlcv, symbol, timeframe, limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df.astype(float)
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
    raise RuntimeError(f"Failed to fetch OHLCV after {max_retries} attempts")
```

- [ ] **Step 2: Commit**

```bash
git add crypto_bot/data/feed.py
git commit -m "feat: OKX data feed with retry logic"
```

---

### Task 9: Telegram notification

**Files:**
- Create: `crypto_bot/notify/telegram.py`

- [ ] **Step 1: Write Telegram notifier**

```python
import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading alerts via Telegram bot."""

    def __init__(self, cfg: dict):
        tg = cfg["notify"]["telegram"]
        self._enabled = tg.get("enabled", False)
        self._token = tg.get("token", "")
        self._chat_id = tg.get("chat_id", "")

    async def send(self, message: str) -> bool:
        if not self._enabled or not self._token:
            logger.info(f"[TG] {message}")
            return False
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def notify_trade_open(self, symbol: str, price: float, quantity: float, reason: str):
        msg = (
            f"🟢 <b>开仓</b> #{symbol}\n"
            f"价格: {price:.2f}\n"
            f"数量: {quantity:.6f}\n"
            f"信号: {reason}"
        )
        await self.send(msg)

    async def notify_trade_close(self, symbol: str, price: float, pnl: float, pnl_pct: float, reason: str):
        emoji = "🟢" if pnl > 0 else "🔴"
        msg = (
            f"{emoji} <b>平仓</b> #{symbol}\n"
            f"价格: {price:.2f}\n"
            f"盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)\n"
            f"原因: {reason}"
        )
        await self.send(msg)

    async def notify_daily_summary(self, date: str, starting_balance: float, ending_balance: float, pnl: float, pnl_pct: float, trades: int, wins: int, losses: int):
        msg = (
            f"📊 <b>每日汇总</b> {date}\n"
            f"起始余额: {starting_balance:.2f} USDT\n"
            f"最终余额: {ending_balance:.2f} USDT\n"
            f"净盈亏: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n"
            f"交易: {trades}笔 | 胜{wins} | 负{losses}"
        )
        await self.send(msg)

    async def notify_error(self, error: str):
        await self.send(f"⚠️ <b>异常</b>\n{error}")
```

- [ ] **Step 2: Commit**

```bash
git add crypto_bot/notify/telegram.py
git commit -m "feat: Telegram notification module"
```

---

### Task 10: Main loop and entry point

**Files:**
- Create: `crypto_bot/main.py`

- [ ] **Step 1: Write main.py**

```python
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

import ccxt

from crypto_bot.config import get_config
from crypto_bot.data.storage import (
    init_db, open_trade, close_trade, get_open_trades, record_balance,
    set_risk_state, update_daily_stats
)
from crypto_bot.data.feed import fetch_with_retry
from crypto_bot.strategy.indicators import compute_indicators
from crypto_bot.strategy.signals import check_entry, check_exit
from crypto_bot.risk.manager import (
    can_open_position, calculate_position_size, check_extreme_volatility, handle_stop_loss, record_daily_pnl
)
from crypto_bot.execution.paper import PaperBroker
from crypto_bot.execution.live import LiveBroker
from crypto_bot.notify.telegram import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

SHUTDOWN = False


def on_shutdown(signum, frame):
    global SHUTDOWN
    logger.info("Shutdown signal received, finishing current loop...")
    SHUTDOWN = True


async def main():
    global SHUTDOWN
    signal.signal(signal.SIGINT, on_shutdown)
    signal.signal(signal.SIGTERM, on_shutdown)

    cfg = get_config()
    init_db()

    # Create broker
    if cfg["mode"] == "live":
        # Safety check
        import os
        if os.getenv("PAPER_TRADING_ONLY", "true").lower() != "false":
            logger.error("Refusing live mode: PAPER_TRADING_ONLY env not set to 'false'")
            return
        broker = LiveBroker(cfg)
        logger.info("Using LIVE broker — REAL MONEY")
    else:
        broker = PaperBroker(initial_balance=5000)
        # Use CCXT for price data even in paper mode
        ex_cfg = cfg["exchange"]
        exchange = ccxt.okx({
            "enableRateLimit": True,
        })
        if ex_cfg.get("testnet"):
            exchange.set_sandbox_mode(True)
        exchange.load_markets()
        broker.set_exchange(exchange)
        broker._exchange = exchange
        logger.info("Using PAPER broker — simulated trading")

    tg = TelegramNotifier(cfg)

    symbols = cfg["trading"]["symbols"]
    tf_main = cfg["trading"]["timeframe"]
    tf_trend = cfg["trading"]["trend_timeframe"]

    starting_balance = broker.get_balance("USDT")["total"]
    logger.info(f"Starting balance: {starting_balance:.2f} USDT | Mode: {cfg['mode']}")

    while not SHUTDOWN:
        try:
            await run_loop(broker, tg, symbols, tf_main, tf_trend, cfg)
        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            await tg.notify_error(str(e))

        await asyncio.sleep(60)


async def run_loop(broker, tg, symbols, tf_main, tf_trend, cfg):
    """Execute one iteration of the trading loop."""
    exchange = getattr(broker, '_exchange', None) or broker.exchange

    for symbol in symbols:
        # Fetch data
        df_1h = await fetch_with_retry(exchange, symbol, tf_main, limit=300)
        df_4h = await fetch_with_retry(exchange, symbol, tf_trend, limit=300)
        df_1h = compute_indicators(df_1h, cfg)
        df_4h = compute_indicators(df_4h, cfg)

        # Update paper broker price
        if isinstance(broker, PaperBroker):
            broker.update_price(symbol, df_1h.iloc[-1]["close"])

        # Check extreme volatility — skip entries if triggered
        if check_extreme_volatility(df_1h, cfg):
            logger.warning(f"Extreme volatility detected for {symbol}, skipping entries")
            continue

        # Check exits for open trades
        for trade in get_open_trades():
            if trade["symbol"] != symbol:
                continue
            exit_signal = check_exit(trade, df_1h, cfg)
            if exit_signal:
                base = symbol.split("/")[0]
                coin_balance = broker.get_balance(base)["free"]
                if coin_balance > 0:
                    result = broker.market_sell(symbol, coin_balance)
                    if result.success:
                        close_trade(trade["id"], result.price, exit_signal.reason)
                        t = trade
                        pnl = (result.price - t["entry_price"]) * result.quantity
                        pnl_pct = (result.price / t["entry_price"] - 1) * 100
                        record_daily_pnl(pnl)
                        await tg.notify_trade_close(symbol, result.price, pnl, pnl_pct, exit_signal.reason)
                        if exit_signal.reason == "stop_loss":
                            handle_stop_loss(trade["id"], symbol)
                        logger.info(f"Exit: {symbol} @ {result.price:.2f} reason={exit_signal.reason}")

        # Check entry
        bal = broker.get_balance("USDT")
        balance_usdt = bal["total"]
        can_enter, reason = can_open_position(symbol, balance_usdt, cfg)
        if can_enter:
            signal = check_entry(df_1h, df_4h, symbol, cfg)
            if signal:
                atr = df_1h.iloc[-1]["atr"]
                size_usdt = calculate_position_size(symbol, balance_usdt, signal.price, atr, cfg)
                result = broker.market_buy(symbol, size_usdt)
                if result.success:
                    trade_id = open_trade(symbol, result.price, result.quantity, "buy")
                    await tg.notify_trade_open(symbol, result.price, result.quantity, signal.reason)
                    logger.info(f"Entry: {symbol} @ {result.price:.2f} size={size_usdt:.2f} USDT")

    # Record balances
    bal = broker.get_balance("USDT")
    record_balance("USDT", bal["free"], bal["used"])
    for symbol in symbols:
        base = symbol.split("/")[0]
        b = broker.get_balance(base)
        record_balance(base, b["free"], b["used"])


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Test paper mode loop runs**

Run: `timeout 65 python -m crypto_bot.main` (Ctrl+C after 1 cycle)
Expected: log output showing fetch, indicator calculation, "no signal" messages, clean shutdown

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/main.py
git commit -m "feat: main loop with full pipeline integration"
```

---

### Task 11: Backtest engine

**Files:**
- Create: `crypto_bot/backtest/engine.py`

- [ ] **Step 1: Write backtest engine**

```python
import pandas as pd
from datetime import datetime, timezone, timedelta
from crypto_bot.strategy.indicators import compute_indicators
from crypto_bot.strategy.signals import check_entry, check_exit


class BacktestResult:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []
        self.starting_balance: float = 0
        self.ending_balance: float = 0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades) if self.trades else 0

    @property
    def total_pnl(self) -> float:
        return sum(t["pnl"] for t in self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0
        peak = self.equity_curve[0]
        max_dd = 0
        for v in self.equity_curve:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def summary(self) -> str:
        return (
            f"Trades: {self.total_trades} | Win rate: {self.win_rate:.1%} | "
            f"Total PnL: {self.total_pnl:.2f} USDT | "
            f"Max DD: {self.max_drawdown:.1%} | "
            f"Final: {self.ending_balance:.2f} USDT"
        )


def run_backtest(df_1h: pd.DataFrame, df_4h: pd.DataFrame, symbol: str, cfg: dict, initial_balance: float = 5000) -> BacktestResult:
    """Walk-forward backtest on historical data."""
    df_1h = compute_indicators(df_1h.copy(), cfg)
    df_4h = compute_indicators(df_4h.copy(), cfg)

    result = BacktestResult()
    result.starting_balance = initial_balance

    balance_usdt = initial_balance
    position: dict | None = None
    equity = [initial_balance]

    min_len = 250
    for i in range(min_len, min(len(df_1h), len(df_4h) * 6)):
        window_1h = df_1h.iloc[:i + 1]
        window_4h = df_4h.iloc[:i // 6 + 1]
        price = df_1h.iloc[i]["close"]

        # Update equity for drawdown calculation
        if position:
            unrealized = (price - position["entry_price"]) * position["qty"]
            equity.append(balance_usdt + unrealized)
        else:
            equity.append(balance_usdt)

        # Check exit
        if position:
            exit_signal = check_exit(position, window_1h, cfg)
            if exit_signal:
                pnl = (price - position["entry_price"]) * position["qty"]
                pnl_pct = (price / position["entry_price"] - 1) * 100
                fee = price * position["qty"] * 0.001 * 2  # round-trip
                balance_usdt += pnl - fee
                result.trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": df_1h.index[i],
                    "symbol": symbol,
                    "entry_price": position["entry_price"],
                    "exit_price": price,
                    "qty": position["qty"],
                    "pnl": pnl - fee,
                    "pnl_pct": pnl_pct,
                    "reason": exit_signal.reason,
                })
                position = None

        # Check entry (simplified risk: max 1 position, 20% per trade)
        if not position and balance_usdt > initial_balance * 0.30:
            entry_signal = check_entry(window_1h, window_4h, symbol, cfg)
            if entry_signal:
                size = balance_usdt * 0.15
                qty = size / price
                position = {
                    "entry_price": price,
                    "qty": qty,
                    "entry_time": df_1h.index[i],
                    "symbol": symbol,
                }

    # Close any remaining position at last price
    if position:
        price = df_1h.iloc[-1]["close"]
        pnl = (price - position["entry_price"]) * position["qty"]
        balance_usdt += pnl
        result.trades.append({
            "entry_time": position["entry_time"],
            "exit_time": df_1h.index[-1],
            "symbol": symbol,
            "entry_price": position["entry_price"],
            "exit_price": price,
            "qty": position["qty"],
            "pnl": pnl,
            "pnl_pct": (price / position["entry_price"] - 1) * 100,
            "reason": "end_of_data",
        })

    result.ending_balance = balance_usdt
    result.equity_curve = equity
    return result
```

- [ ] **Step 2: Run backtest smoke test**

Run:
```python
python -c "
import pandas as pd
import numpy as np
from crypto_bot.backtest.engine import run_backtest

np.random.seed(42)
n = 500
close = np.concatenate([
    np.linspace(90000, 85000, 100),
    np.linspace(85000, 88000, 100),
    np.linspace(88000, 86000, 100),
    np.linspace(86000, 91000, 100),
    np.linspace(91000, 89000, 100),
])
df_1h = pd.DataFrame({
    'open': close * 0.999, 'high': close * 1.01, 'low': close * 0.99,
    'close': close, 'volume': np.random.uniform(500, 2000, n),
})
df_1h.index = pd.date_range('2024-01-01', periods=n, freq='1h', tz='UTC')

close_4h = close[::6][:len(df_1h)//6+1]
n4 = len(close_4h)
df_4h = pd.DataFrame({
    'open': close_4h * 0.998, 'high': close_4h * 1.02, 'low': close_4h * 0.98,
    'close': close_4h, 'volume': np.random.uniform(2000, 8000, n4),
})
df_4h.index = pd.date_range('2024-01-01', periods=n4, freq='4h', tz='UTC')

cfg = {
    'strategy': {'bb_period': 20, 'bb_std': 2.0, 'rsi_period': 14, 'rsi_oversold': 35, 'rsi_overbought': 55,
                 'ema_period': 200, 'atr_period': 14, 'atr_stop_multiplier': 2.0, 'volume_ratio_threshold': 1.2, 'max_hold_hours': 72},
    'risk': {'daily_loss_limit': 0.05, 'min_usdt_ratio': 0.30}
}
result = run_backtest(df_1h, df_4h, 'BTC/USDT', cfg)
print(result.summary())
"
```
Expected: prints backtest summary with trade count, win rate, PnL, drawdown

- [ ] **Step 3: Commit**

```bash
git add crypto_bot/backtest/engine.py
git commit -m "feat: historical backtest engine"
```

---

### Task 12: Docker deployment

**Files:**
- Create: `crypto_bot/Dockerfile`
- Create: `crypto_bot/.env.example`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "crypto_bot.main"]
```

- [ ] **Step 2: Write .env.example**

```env
OKX_API_KEY=your_api_key_here
OKX_SECRET=your_secret_here
OKX_PASSWORD=your_passphrase_here
TG_BOT_TOKEN=your_telegram_bot_token
TG_CHAT_ID=your_telegram_chat_id
PAPER_TRADING_ONLY=true
```

- [ ] **Step 3: Add .gitignore entries**

Append to `crypto_bot/.gitignore`:
```
.env
trading.db
__pycache__/
*.pyc
```

- [ ] **Step 4: Build and verify Docker image**

Run: `docker build -t crypto-bot -f crypto_bot/Dockerfile crypto_bot/`
Expected: image builds successfully

- [ ] **Step 5: Commit**

```bash
git add crypto_bot/Dockerfile crypto_bot/.env.example crypto_bot/.gitignore
git commit -m "feat: Docker deployment and env template"
```

---

### Task 13: Integration test — paper mode end-to-end

- [ ] **Step 1: Run full paper mode for 5 minutes, verify all modules work together**

Run: `timeout 300 python -m crypto_bot.main`
- Check that data is fetched
- Check that signals are logged to SQLite
- Check that no exceptions occur
- Check that balance records are written

- [ ] **Step 2: Verify SQLite has data**

Run:
```bash
python -c "
from crypto_bot.data.storage import get_conn
conn = get_conn()
signals = conn.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
balances = conn.execute('SELECT COUNT(*) FROM balances').fetchone()[0]
print(f'Signals: {signals}, Balances: {balances}')
"
```
Expected: non-zero counts for both tables

- [ ] **Step 3: Commit if any config adjustments needed**

```bash
git add -A && git commit -m "test: integration test verification" || true
```
```

---

Now let me do the self-review before saving.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="Read">
<｜｜DSML｜｜parameter name="file_path" string="true">C:\Users\drago\Desktop\量化交易\docs\superpowers\plans\2026-05-18-crypto-bot-plan.md