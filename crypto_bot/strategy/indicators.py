import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta


def compute_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Compute all indicators on OHLCV DataFrame. Adds columns in-place."""
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
