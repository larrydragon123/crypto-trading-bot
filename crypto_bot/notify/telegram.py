import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends trading alerts via Telegram bot."""

    def __init__(self, cfg: dict):
        tg = cfg["notify"]["telegram"]
        self._enabled = tg.get("enabled", False)
        self._token = tg.get("token", "")
        self._chat_id = tg.get("chat_id", "")

    async def send(self, message: str) -> bool:
        if not self._enabled or not self._token:
            logger.info(f"[TG] {message}")
            return False
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }, timeout=10)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def notify_trade_open(self, symbol: str, price: float, quantity: float, reason: str):
        msg = (
            f"🟢 <b>开仓</b> #{symbol}\n"
            f"价格: {price:.2f}\n"
            f"数量: {quantity:.6f}\n"
            f"信号: {reason}"
        )
        await self.send(msg)

    async def notify_trade_close(self, symbol: str, price: float, pnl: float, pnl_pct: float, reason: str):
        emoji = "🟢" if pnl > 0 else "🔴"
        msg = (
            f"{emoji} <b>平仓</b> #{symbol}\n"
            f"价格: {price:.2f}\n"
            f"盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)\n"
            f"原因: {reason}"
        )
        await self.send(msg)

    async def notify_daily_summary(self, date: str, starting_balance: float, ending_balance: float, pnl: float, pnl_pct: float, trades: int, wins: int, losses: int):
        msg = (
            f"📊 <b>每日汇总</b> {date}\n"
            f"起始余额: {starting_balance:.2f} USDT\n"
            f"最终余额: {ending_balance:.2f} USDT\n"
            f"净盈亏: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n"
            f"交易: {trades}笔 | 胜{wins} | 负{losses}"
        )
        await self.send(msg)

    async def notify_error(self, error: str):
        await self.send(f"⚠️ <b>异常</b>\n{error}")
