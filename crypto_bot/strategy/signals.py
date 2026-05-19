from dataclasses import dataclass
import pandas as pd
from crypto_bot.strategy.indicators import is_ranging


@dataclass
class Signal:
    symbol: str
    direction: str  # "long" | "short" | "close_long" | "close_short"
    price: float
    reason: str
    indicators: dict


def check_entry(df_1h: pd.DataFrame, symbol: str, cfg: dict) -> Signal | None:
    """Check entry conditions on latest candle. Returns Signal or None.

    V3 strategy: ADX regime filter, asymmetric entries.
    - Long: BB oversold + RSI oversold + volume + ADX ranging
    - Short: BB overbought + RSI overbought + volume + ADX ranging
    """
    if len(df_1h) < 200:
        return None

    strat = cfg["strategy"]
    row = df_1h.iloc[-1]
    price = row["close"]

    # Regime filter: only trade in ranging markets
    if not is_ranging(df_1h, percentile=strat.get("adx_percentile", 40)):
        return None

    indicators = {
        "bb_lower": row["bb_lower"],
        "bb_mid": row["bb_mid"],
        "bb_upper": row["bb_upper"],
        "rsi": row["rsi"],
        "adx": row["adx"],
        "vol_ratio": row["vol_ratio"],
    }

    # Long entry: oversold
    if (price <= row["bb_lower"]
            and row["rsi"] < strat["rsi_oversold"]
            and row["vol_ratio"] > strat["volume_ratio_threshold"]):
        return Signal(
            symbol=symbol,
            direction="long",
            price=price,
            reason="entry_oversold",
            indicators=indicators,
        )

    # Short entry: overbought
    if (price >= row["bb_upper"]
            and row["rsi"] > strat["rsi_overbought"]
            and row["vol_ratio"] > strat["volume_ratio_threshold"]):
        return Signal(
            symbol=symbol,
            direction="short",
            price=price,
            reason="entry_overbought",
            indicators=indicators,
        )

    return None


def check_exit(trade: dict, df_1h: pd.DataFrame, cfg: dict) -> Signal | None:
    """Check exit conditions for an open trade. Returns Signal or None.

    V3 strategy: asymmetric stops and take-profits.
    - Long stop: 2.0 × ATR (tighter, drops accelerate)
    - Short stop: 3.0 × ATR (wider, rallies are choppy)
    - Long TP: BB mid (conservative, high hit rate)
    - Short TP: BB lower (faster mean reversion down)
    """
    if len(df_1h) < 200:
        return None

    strat = cfg["strategy"]
    row = df_1h.iloc[-1]
    price = row["close"]
    entry_price = trade["entry_price"]

    sl_long_mult = strat.get("sl_long_mult", 2.0)
    sl_short_mult = strat.get("sl_short_mult", 3.0)
    max_hold = strat.get("max_hold_hours", 24)

    from datetime import datetime, timezone
    entry_time = datetime.fromisoformat(trade["entry_time"])
    hours_held = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600

    if trade.get("side") == "short" or trade.get("direction") == "short":
        # Short exit checks
        stop_price = entry_price + sl_short_mult * row["atr"]
        if price >= stop_price:
            return Signal(
                symbol=trade["symbol"],
                direction="close_short",
                price=price,
                reason="stop_loss",
                indicators={"stop_price": stop_price, "atr": row["atr"]},
            )

        if price <= row["bb_lower"]:
            return Signal(
                symbol=trade["symbol"],
                direction="close_short",
                price=price,
                reason="take_profit",
                indicators={"bb_lower": row["bb_lower"]},
            )

        if hours_held > max_hold:
            return Signal(
                symbol=trade["symbol"],
                direction="close_short",
                price=price,
                reason="time_stop",
                indicators={"hours_held": hours_held},
            )
    else:
        # Long exit checks
        stop_price = entry_price - sl_long_mult * row["atr"]
        if price <= stop_price:
            return Signal(
                symbol=trade["symbol"],
                direction="close_long",
                price=price,
                reason="stop_loss",
                indicators={"stop_price": stop_price, "atr": row["atr"]},
            )

        if price >= row["bb_mid"] and row["rsi"] > 55:
            return Signal(
                symbol=trade["symbol"],
                direction="close_long",
                price=price,
                reason="take_profit",
                indicators={"bb_mid": row["bb_mid"], "rsi": row["rsi"]},
            )

        if hours_held > max_hold:
            return Signal(
                symbol=trade["symbol"],
                direction="close_long",
                price=price,
                reason="time_stop",
                indicators={"hours_held": hours_held},
            )

    return None
