from crypto_bot.execution.base import BaseBroker, OrderResult
from crypto_bot.data.storage import record_balance


class PaperBroker(BaseBroker):
    """Simulated broker supporting long and short positions."""

    def __init__(self, initial_balance: float = 5000):
        self.balances: dict[str, dict[str, float]] = {}
        self._ensure_asset("USDT", initial_balance)
        self._prices: dict[str, float] = {}
        self._order_counter = 0
        self._exchange = None
        self._short_positions: dict[str, dict] = {}  # symbol -> {qty, entry_price}

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
        """Buy spot (open long or close short)."""
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "buy", 0, 0, 0, "no price data")

        usdt_bal = self.balances["USDT"]["free"]
        if amount_usdt > usdt_bal:
            amount_usdt = usdt_bal
        if amount_usdt <= 0:
            return OrderResult(False, "", symbol, "buy", 0, 0, 0, "insufficient USDT")

        fee_rate = 0.001
        gross = amount_usdt / price
        fee = gross * fee_rate
        net = gross - fee

        # If we have a short position, closing it first
        short = self._short_positions.get(symbol)
        if short:
            # Buying back to cover short
            if net >= short["qty"]:
                # Full close
                close_qty = short["qty"]
                pnl = (short["entry_price"] - price) * close_qty
                usdt_gain = close_qty * price - fee * price
                self.balances["USDT"]["free"] += usdt_gain - (close_qty * price) + pnl
                # Actually, simpler: net = amount_usdt/price - fee
                # We're buying back close_qty coins
                cost = close_qty * price
                fee_cost = cost * fee_rate
                pnl = (short["entry_price"] - price) * close_qty
                self.balances["USDT"]["free"] -= (cost + fee_cost)
                self.balances["USDT"]["total"] = self.balances["USDT"]["free"] + self.balances["USDT"]["used"]
                self._order_counter += 1
                del self._short_positions[symbol]
                record_balance("USDT", self.balances["USDT"]["free"], self.balances["USDT"]["used"])
                return OrderResult(True, f"paper_{self._order_counter}", symbol, "buy", price, close_qty, fee_cost)
            else:
                # Partial close not supported, just ignore for now
                pass

        # Normal spot buy
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
        """Sell spot (close long)."""
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "sell", 0, 0, 0, "no price data")

        self._ensure_asset(base)
        coin_bal = self.balances[base]["free"]
        if amount_coin > coin_bal:
            amount_coin = coin_bal
        if amount_coin <= 0:
            return OrderResult(False, "", symbol, "sell", 0, 0, 0, "no coins to sell")

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

    def open_short(self, symbol: str, amount_usdt: float) -> OrderResult:
        """Open a short position by selling borrowed coins."""
        base = symbol.split("/")[0]
        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "sell_short", 0, 0, 0, "no price data")

        fee_rate = 0.001
        gross_qty = amount_usdt / price
        fee = gross_qty * price * fee_rate
        net_qty = gross_qty - (fee / price)

        # Record short position (negative coin balance tracked separately)
        self._short_positions[symbol] = {
            "qty": net_qty,
            "entry_price": price,
        }

        self._order_counter += 1
        return OrderResult(True, f"paper_{self._order_counter}", symbol, "sell_short", price, net_qty, fee)

    def close_short(self, symbol: str) -> OrderResult | None:
        """Close an open short position."""
        short = self._short_positions.get(symbol)
        if not short:
            return None

        price = self._prices.get(symbol, 0)
        if price <= 0:
            return OrderResult(False, "", symbol, "buy_cover", 0, 0, 0, "no price data")

        qty = short["qty"]
        entry_price = short["entry_price"]
        fee_rate = 0.001
        cost = qty * price
        fee = cost * fee_rate
        pnl = (entry_price - price) * qty

        self.balances["USDT"]["free"] += pnl - fee
        self.balances["USDT"]["total"] = self.balances["USDT"]["free"] + self.balances["USDT"]["used"]

        self._order_counter += 1
        del self._short_positions[symbol]

        record_balance("USDT", self.balances["USDT"]["free"], self.balances["USDT"]["used"])
        return OrderResult(True, f"paper_{self._order_counter}", symbol, "buy_cover", price, qty, fee)

    def get_short_position(self, symbol: str) -> dict | None:
        return self._short_positions.get(symbol)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[list]:
        if self._exchange:
            return self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return []
