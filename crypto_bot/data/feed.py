import asyncio
import functools
import logging
import pandas as pd

logger = logging.getLogger(__name__)


async def fetch_with_retry(exchange, symbol: str, timeframe: str, limit: int = 300, max_retries: int = 3) -> pd.DataFrame:
    """Fetch OHLCV with exponential backoff retry."""
    delay = 5
    loop = asyncio.get_running_loop()
    for attempt in range(max_retries):
        try:
            fetch_fn = functools.partial(
                exchange.fetch_ohlcv, symbol, timeframe, limit=limit
            )
            raw = await loop.run_in_executor(None, fetch_fn)
            if not raw or len(raw) == 0:
                raise ValueError(f"Empty response from exchange for {symbol} {timeframe}")
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            df = df.astype(float)
            logger.info(f"Fetched {len(df)} candles for {symbol} {timeframe}")
            return df
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Fetch attempt {attempt + 1}/{max_retries} for {symbol} {timeframe}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
    raise RuntimeError(f"Failed to fetch OHLCV for {symbol} {timeframe} after {max_retries} attempts")
