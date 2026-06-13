import logging
import os

from twilio.rest import Client as TwilioClient

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_FROM,
    TWILIO_WHATSAPP_TO,
)

logger = logging.getLogger(__name__)

SOUND_FILE = os.path.join(os.path.dirname(__file__), "sounds", "alert.mp3")


class Notifier:
    """Отправка уведомлений через Telegram (текст + звук) и WhatsApp."""

    def __init__(self, telegram_bot=None):
        self.telegram_bot = telegram_bot
        self._twilio_client: TwilioClient | None = None
        self._has_sound = os.path.isfile(SOUND_FILE)
        if self._has_sound:
            logger.info("Звуковой файл найден: %s", SOUND_FILE)
        else:
            logger.warning(
                "Звуковой файл не найден: %s — уведомления будут текстовыми",
                SOUND_FILE,
            )

    def _get_twilio(self) -> TwilioClient | None:
        if self._twilio_client is None:
            if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
                logger.warning("Twilio не настроен — WhatsApp отключён")
                return None
            self._twilio_client = TwilioClient(
                TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
            )
        return self._twilio_client

    async def send_telegram_text(self, user_id: int, message: str):
        if not self.telegram_bot:
            return
        try:
            await self.telegram_bot.send_message(
                chat_id=user_id, text=message, parse_mode="HTML"
            )
        except Exception as e:
            logger.error("Ошибка Telegram текст: %s", e)

    async def send_telegram_audio(self, user_id: int):
        """Отправить звуковой файл alert.mp3 как аудио в Telegram."""
        if not self.telegram_bot or not self._has_sound:
            return
        try:
            with open(SOUND_FILE, "rb") as f:
                await self.telegram_bot.send_audio(
                    chat_id=user_id, audio=f, title="Alert"
                )
        except Exception as e:
            logger.error("Ошибка Telegram audio: %s", e)

    async def send_whatsapp(self, message: str):
        client = self._get_twilio()
        if not client:
            return
        try:
            client.messages.create(
                body=message,
                from_=TWILIO_WHATSAPP_FROM,
                to=TWILIO_WHATSAPP_TO,
            )
        except Exception as e:
            logger.error("Ошибка WhatsApp: %s", e)

    async def send_alert(
        self,
        user_id: int,
        symbol: str,
        target_price: float,
        current_price: float,
    ):
        message = (
            f"🚨 <b>ALERT!</b>\n\n"
            f"Фьючерс: <b>{symbol}</b>\n"
            f"Цель: <b>{target_price}</b>\n"
            f"Текущая цена: <b>{current_price}</b>\n\n"
            f"Алерт сработал и удалён."
        )

        # Звуковой файл (воспроизведёт звук даже в беззвучном режиме)
        await self.send_telegram_audio(user_id)
        # Текстовое уведомление
        await self.send_telegram_text(user_id, message)

        wa_message = (
            f"🚨 ALERT!\n\n"
            f"Фьючерс: {symbol}\n"
            f"Цель: {target_price}\n"
            f"Текущая цена: {current_price}\n\n"
            f"Алерт сработал и удалён."
        )
        await self.send_whatsapp(wa_message)
