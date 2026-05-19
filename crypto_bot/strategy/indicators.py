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
    if bb is None:
        raise ValueError(f"BBands returned None — need at least {strat['bb_period']} candles")
    bb_cols = {c.split("_")[0]: c for c in bb.columns}
    df["bb_lower"] = bb[bb_cols["BBL"]]
    df["bb_mid"] = bb[bb_cols["BBM"]]
    df["bb_upper"] = bb[bb_cols["BBU"]]

    df["rsi"] = ta.rsi(close, length=strat["rsi_period"])
    df["ema"] = ta.ema(close, length=strat["ema_period"])
    df["atr"] = ta.atr(high, low, close, length=strat["atr_period"])
    df["vol_sma"] = vol.rolling(window=strat["bb_period"]).mean()
    df["vol_ratio"] = vol / df["vol_sma"]

    df["price_change_1h"] = close.pct_change(periods=1)

    return df


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ADX columns in-place (Wilder's method)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_ = tr.ewm(span=period, adjust=False).mean()

    up = high - high.shift(1)
    down = low.shift(1) - low
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up
    minus_dm[(down > up) & (down > 0)] = down

    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr_)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr_)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 0.0001)
    adx = dx.ewm(span=period, adjust=False).mean()

    df["adx"] = adx
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    return df


def is_ranging(df: pd.DataFrame, percentile: int = 40) -> bool:
    """Check if current ADX is in bottom percentile of recent window."""
    adx_series = df["adx"].dropna()
    if len(adx_series) < 50:
        return True  # not enough data, allow trading
    current = adx_series.iloc[-1]
    rank = (adx_series.iloc[-168:] < current).mean() * 100  # % of last week below current
    return rank < percentile
