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
