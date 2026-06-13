import aiohttp
import logging

from config import BINANCE_FUTURES_TICKER_URL, BINANCE_FUTURES_KLINES_URL

logger = logging.getLogger(__name__)


class BinanceClient:
    """Клиент для получения данных с Binance Futures (публичный API)."""

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_all_futures_tickers(self) -> dict[str, str]:
        """
        Получить цены всех USDT фьючерсных пар.
        Возвращает {символ: цена_строкой}.
        """
        session = await self._get_session()
        try:
            async with session.get(BINANCE_FUTURES_TICKER_URL) as resp:
                if resp.status != 200:
                    logger.error("Binance API вернул статус %s", resp.status)
                    return {}
                data = await resp.json()
                # Фильтруем только USDT пары
                return {
                    item["symbol"]: item["price"]
                    for item in data
                    if item["symbol"].endswith("USDT")
                }
        except Exception as e:
            logger.error("Ошибка получения тикеров: %s", e)
            return {}

    async def get_price(self, symbol: str) -> float | None:
        """Получить текущую цену конкретного фьючерсного контракта."""
        session = await self._get_session()
        params = {"symbol": symbol}
        try:
            async with session.get(
                BINANCE_FUTURES_TICKER_URL, params=params
            ) as resp:
                if resp.status != 200:
                    logger.error(
                        "Binance API вернул статус %s для %s", resp.status, symbol
                    )
                    return None
                data = await resp.json()
                return float(data["price"])
        except Exception as e:
            logger.error("Ошибка получения цены для %s: %s", symbol, e)
            return None
