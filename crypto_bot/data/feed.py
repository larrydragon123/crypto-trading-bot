import asyncio
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataFeed:
    """Fetches OHLCV data from OKX via REST."""

    def __init__(self, exchange):
        self._exchange = exchange
        self._cache: dict[str, dict[str, pd.DataFrame]] = {}

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> pd.DataFrame:
        raw = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df.astype(float)

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
