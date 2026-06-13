import aiohttp
import logging

from config import BINANCE_FUTURES_TICKER_URL, BINANCE_FUTURES_TICKER_24H_URL, BINANCE_FUTURES_KLINES_URL

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

    async def get_top_volatile(self, limit: int = 15) -> list[dict]:
        """
        Получить топ-15 самых волатильных USDT фьючерсов за 24ч.
        Волатильность = (High - Low) / Low * 100%.
        Возвращает список словарей: symbol, volatility, price, direction.
        """
        session = await self._get_session()
        try:
            async with session.get(BINANCE_FUTURES_TICKER_24H_URL) as resp:
                if resp.status != 200:
                    logger.error("Binance 24h ticker вернул статус %s", resp.status)
                    return []
                data = await resp.json()

                results = []
                for item in data:
                    symbol = item.get("symbol", "")
                    if not symbol.endswith("USDT"):
                        continue
                    try:
                        high = float(item.get("highPrice", 0))
                        low = float(item.get("lowPrice", 0))
                        price = float(item.get("lastPrice", 0))
                        if low <= 0 or price <= 0:
                            continue
                        volatility = (high - low) / low * 100
                        direction = "📈" if price >= (high + low) / 2 else "📉"
                        results.append({
                            "symbol": symbol,
                            "volatility": round(volatility, 2),
                            "price": price,
                            "direction": direction,
                        })
                    except (ValueError, TypeError):
                        continue

                results.sort(key=lambda x: x["volatility"], reverse=True)
                return results[:limit]
        except Exception as e:
            logger.error("Ошибка получения 24h тикеров: %s", e)
            return []

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
