import json
import os
import logging
from typing import Any

from config import ALERTS_FILE

logger = logging.getLogger(__name__)


class AlertManager:
    """Управление алертами: добавление, удаление, хранение."""

    def __init__(self):
        self.alerts: list[dict[str, Any]] = []
        self._load()

    def _load(self):
        """Загрузить алерты из JSON файла."""
        if os.path.exists(ALERTS_FILE):
            try:
                with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                    self.alerts = json.load(f)
                logger.info("Загружено %s алертов из файла", len(self.alerts))
            except (json.JSONDecodeError, IOError) as e:
                logger.error("Ошибка загрузки алертов: %s", e)
                self.alerts = []
        else:
            self.alerts = []

    def _save(self):
        """Сохранить алерты в JSON файл."""
        try:
            with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.alerts, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error("Ошибка сохранения алертов: %s", e)

    def add_alert(self, user_id: int, symbol: str, price: float) -> bool:
        """
        Добавить алерт.
        Возвращает True если алерт создан, False если уже существует.
        """
        # Проверяем дубликаты
        for alert in self.alerts:
            if (
                alert["user_id"] == user_id
                and alert["symbol"] == symbol
                and alert["price"] == price
            ):
                return False

        self.alerts.append(
            {
                "user_id": user_id,
                "symbol": symbol.upper(),
                "price": price,
                "triggered": False,
            }
        )
        self._save()
        logger.info(
            "Добавлен алерт: %s @ %s (user=%s)", symbol, price, user_id
        )
        return True

    def get_user_alerts(self, user_id: int) -> list[dict[str, Any]]:
        """Получить все активные алерты пользователя."""
        return [a for a in self.alerts if a["user_id"] == user_id]

    def delete_alert(self, user_id: int, symbol: str, price: float) -> bool:
        """
        Удалить конкретный алерт.
        Возвращает True если удалён, False если не найден.
        """
        for i, alert in enumerate(self.alerts):
            if (
                alert["user_id"] == user_id
                and alert["symbol"] == symbol.upper()
                and alert["price"] == price
            ):
                self.alerts.pop(i)
                self._save()
                logger.info(
                    "Удалён алерт: %s @ %s (user=%s)",
                    symbol,
                    price,
                    user_id,
                )
                return True
        return False

    def delete_user_alerts(self, user_id: int) -> int:
        """
        Удалить все алерты пользователя.
        Возвращает количество удалённых.
        """
        before = len(self.alerts)
        self.alerts = [a for a in self.alerts if a["user_id"] != user_id]
        removed = before - len(self.alerts)
        if removed:
            self._save()
            logger.info("Удалены все алерты user=%s: %s шт.", user_id, removed)
        return removed

    def remove_triggered(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """
        Удалить все алерты для символа, которые достигли цены.
        Возвращает список удалённых алертов (для отправки уведомлений).
        """
        triggered = []
        remaining = []
        for alert in self.alerts:
            if alert["symbol"] == symbol and alert["price"] == price:
                triggered.append(alert)
            else:
                remaining.append(alert)
        if triggered:
            self.alerts = remaining
            self._save()
            logger.info(
                "Сработало %s алертов для %s @ %s",
                len(triggered),
                symbol,
                price,
            )
        return triggered

    def get_all_active(self) -> list[dict[str, Any]]:
        """Получить все активные алерты."""
        return list(self.alerts)
