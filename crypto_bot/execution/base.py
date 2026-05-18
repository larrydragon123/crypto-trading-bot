from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OrderResult:
    success: bool
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    error: str = ""


class BaseBroker(ABC):

    @abstractmethod
    def get_balance(self, asset: str) -> dict:
        """Return {'free': float, 'used': float, 'total': float}"""
        ...

    @abstractmethod
    def market_buy(self, symbol: str, amount_usdt: float) -> OrderResult:
        ...

    @abstractmethod
    def market_sell(self, symbol: str, amount_coin: float) -> OrderResult:
        ...

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 300) -> list[list]:
        ...
