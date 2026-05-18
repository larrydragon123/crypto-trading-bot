from crypto_bot.execution.base import BaseBroker, OrderResult
from crypto_bot.data.storage import record_balance


class PaperBroker(BaseBroker):
    """Simulated broker using real market prices."""

    def __init__(self, initial_balance: float = 5000):
        self.balances: dict[str, dict[str, float]] = {}
        self._ensure_asset("USDT", initial_balance)
        self._prices: dict[str, float] = {}
        self._order_counter = 0
        self._exchange = None

    def _ensure_asset(self, asset: str, initial: float = 0):
        if asset not in self.balances:
            self.balances[asset] = {"free": initial, "used": 0, "total": initial}

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

        fee_rate = 0.001
        gross = amount_usdt / price
        fee = gross * fee_rate
        net = gross - fee

        self._ensure_asset(base)
        self.balances["USDT"]["free"] -= amount_usdt
        self.balances["USDT"]["total"] = self.balances["USDT"]["free"] + self.balances["USDT"]["used"]
        self.balances[base]["free"] += net
        self.balances[base]["total"] = self.balances[base]["free"] + self.balances[base]["used"]

        self._order_counter += 1
        record_balance("USDT", self.balances["USDT"]["free"], self.balances["USDT"]["used"])
        record_balance(base, self.balances[base]["free"], self.balances[base]["used"])

        return OrderResult(True, f"paper_{self._order_counter}", symbol, "buy", price, net, fee * price)

    def market_sell(self, symbol: str, amount_coin: float) -> OrderResult:
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "sell", 0, 0, 0, "no price data")

        self._ensure_asset(base)
        coin_bal = self.balances[base]["free"]
        if amount_coin > coin_bal:
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
