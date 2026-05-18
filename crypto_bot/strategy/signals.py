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
    if len(df_1h) < 200 or len(df_4h) < 200:
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
    if len(df_1h) < 200:
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
