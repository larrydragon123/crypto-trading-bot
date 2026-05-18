import pandas as pd
from crypto_bot.strategy.indicators import compute_indicators
from crypto_bot.strategy.signals import check_entry, check_exit


class BacktestResult:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []
        self.starting_balance: float = 0
        self.ending_balance: float = 0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades) if self.trades else 0

    @property
    def total_pnl(self) -> float:
        return sum(t["pnl"] for t in self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0
        peak = self.equity_curve[0]
        max_dd = 0
        for v in self.equity_curve:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    def summary(self) -> str:
        return (
            f"Trades: {self.total_trades} | Win rate: {self.win_rate:.1%} | "
            f"Total PnL: {self.total_pnl:.2f} USDT | "
            f"Max DD: {self.max_drawdown:.1%} | "
            f"Final: {self.ending_balance:.2f} USDT"
        )


def run_backtest(df_1h: pd.DataFrame, df_4h: pd.DataFrame, symbol: str, cfg: dict, initial_balance: float = 5000) -> BacktestResult:
    """Walk-forward backtest on historical data."""
    df_1h = compute_indicators(df_1h.copy(), cfg)
    df_4h = compute_indicators(df_4h.copy(), cfg)

    result = BacktestResult()
    result.starting_balance = initial_balance

    balance_usdt = initial_balance
    position: dict | None = None
    equity = [initial_balance]

    min_len = 250
    for i in range(min_len, min(len(df_1h), len(df_4h) * 6)):
        window_1h = df_1h.iloc[:i + 1]
        window_4h = df_4h.iloc[:i // 6 + 1]
        price = df_1h.iloc[i]["close"]

        if position:
            unrealized = (price - position["entry_price"]) * position["qty"]
            equity.append(balance_usdt + unrealized)
        else:
            equity.append(balance_usdt)

        if position:
            exit_signal = check_exit(position, window_1h, cfg)
            if exit_signal:
                pnl = (price - position["entry_price"]) * position["qty"]
                pnl_pct = (price / position["entry_price"] - 1) * 100
                fee = price * position["qty"] * 0.001 * 2
                balance_usdt += pnl - fee
                result.trades.append({
                    "entry_time": position["entry_time"],
                    "exit_time": df_1h.index[i],
                    "symbol": symbol,
                    "entry_price": position["entry_price"],
                    "exit_price": price,
                    "qty": position["qty"],
                    "pnl": pnl - fee,
                    "pnl_pct": pnl_pct,
                    "reason": exit_signal.reason,
                })
                position = None

        if not position and balance_usdt > initial_balance * 0.30:
            entry_signal = check_entry(window_1h, window_4h, symbol, cfg)
            if entry_signal:
                size = balance_usdt * 0.15
                qty = size / price
                position = {
                    "entry_price": price,
                    "qty": qty,
                    "entry_time": df_1h.index[i],
                    "symbol": symbol,
                }

    if position:
        price = df_1h.iloc[-1]["close"]
        pnl = (price - position["entry_price"]) * position["qty"]
        balance_usdt += pnl
        result.trades.append({
            "entry_time": position["entry_time"],
            "exit_time": df_1h.index[-1],
            "symbol": symbol,
            "entry_price": position["entry_price"],
            "exit_price": price,
            "qty": position["qty"],
            "pnl": pnl,
            "pnl_pct": (price / position["entry_price"] - 1) * 100,
            "reason": "end_of_data",
        })

    result.ending_balance = balance_usdt
    result.equity_curve = equity
    return result
