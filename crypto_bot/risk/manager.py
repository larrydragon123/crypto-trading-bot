import pandas as pd
from datetime import datetime, timezone, timedelta
from crypto_bot.data.storage import get_open_trades, get_recent_stops, get_risk_state, set_risk_state


def can_open_position(symbol: str, balance_usdt: float, cfg: dict) -> tuple[bool, str]:
    """Check all risk constraints. Returns (allowed, reason)."""
    risk = cfg["risk"]

    open_trades = get_open_trades()
    if len(open_trades) >= risk["max_positions"]:
        return False, "max_positions_reached"

    for t in open_trades:
        if t["symbol"] == symbol:
            return False, "symbol_already_open"

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_pnl_key = f"daily_pnl_{today_str}"
    daily_pnl = float(get_risk_state(daily_pnl_key) or 0)
    if daily_pnl <= -balance_usdt * risk["daily_loss_limit"]:
        return False, "daily_loss_limit"

    cooldown_until = get_risk_state("cooldown_until")
    if cooldown_until:
        if datetime.now(timezone.utc) < datetime.fromisoformat(cooldown_until):
            return False, "cooldown_active"

    used = sum(t["entry_price"] * t["quantity"] for t in open_trades)
    if balance_usdt - used < balance_usdt * risk["min_usdt_ratio"]:
        return False, "min_usdt_reserve"

    return True, "ok"


def calculate_position_size(symbol: str, balance_usdt: float, price: float, atr: float, cfg: dict) -> float:
    """Calculate position size in quote currency, scaled by ATR volatility."""
    risk = cfg["risk"]
    base_ratio = (risk["position_size_min"] + risk["position_size_max"]) / 2
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
