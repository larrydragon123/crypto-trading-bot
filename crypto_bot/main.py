import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

import ccxt

from crypto_bot.config import get_config
from crypto_bot.data.storage import (
    init_db, open_trade, close_trade, get_open_trades, record_balance,
    update_daily_stats
)
from crypto_bot.data.feed import fetch_with_retry
from crypto_bot.strategy.indicators import compute_indicators
from crypto_bot.strategy.signals import check_entry, check_exit
from crypto_bot.risk.manager import (
    can_open_position, calculate_position_size, check_extreme_volatility,
    handle_stop_loss, record_daily_pnl
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

    if cfg["mode"] == "live":
        import os
        if os.getenv("PAPER_TRADING_ONLY", "true").lower() != "false":
            logger.error("Refusing live mode: PAPER_TRADING_ONLY env not set to 'false'")
            return
        broker = LiveBroker(cfg)
        logger.info("Using LIVE broker — REAL MONEY")
    else:
        broker = PaperBroker(initial_balance=5000)
        ex_cfg = cfg["exchange"]
        exchange = ccxt.okx({"enableRateLimit": True})
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
    exchange = getattr(broker, '_exchange', None) or broker.exchange

    for symbol in symbols:
        df_1h = await fetch_with_retry(exchange, symbol, tf_main, limit=300)
        df_4h = await fetch_with_retry(exchange, symbol, tf_trend, limit=300)
        df_1h = compute_indicators(df_1h, cfg)
        df_4h = compute_indicators(df_4h, cfg)

        if isinstance(broker, PaperBroker):
            broker.update_price(symbol, df_1h.iloc[-1]["close"])

        if check_extreme_volatility(df_1h, cfg):
            logger.warning(f"Extreme volatility detected for {symbol}, skipping entries")
            continue

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

    bal = broker.get_balance("USDT")
    record_balance("USDT", bal["free"], bal["used"])
    for symbol in symbols:
        base = symbol.split("/")[0]
        b = broker.get_balance(base)
        record_balance(base, b["free"], b["used"])


if __name__ == "__main__":
    asyncio.run(main())
