import asyncio
import logging
import re

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, CHECK_INTERVAL, LOG_FILE
from binance_client import BinanceClient
from alert_manager import AlertManager
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

binance = BinanceClient()
alert_mgr = AlertManager()
notifier: Notifier | None = None

user_states: dict[int, str] = {}

# Паттерн для распознавания ввода: "BTC 63500" / "btc 63500" / "Sol 150,5"
_ALERT_RE = re.compile(r"^[a-zA-Z]{2,10}\s+[\d]+[.,]?\d*$")


def _parse_price(raw: str) -> float | None:
    cleaned = raw.replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Мои алерты", callback_data="my_alerts"),
                InlineKeyboardButton("➕ Новый алерт", callback_data="new_alert"),
            ],
            [
                InlineKeyboardButton("🛑 Стоп все", callback_data="stop_all"),
            ],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 <b>Price Alert Bot</b>\n\n"
        "Мониторинг цен фьючерсов Binance.\n"
        "Алерт срабатывает, когда цена достигает заданного уровня.\n\n"
        "Просто введите: <b>BTC 63500</b> или <b>SOL 150,5</b>\n"
        "USDT добавится автоматически."
    )
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=_main_menu_keyboard()
    )


async def cmd_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = "waiting_alert_input"
    await update.message.reply_text(
        "Введите монету и цену. Например: <b>BTC 63500</b>",
        parse_mode="HTML",
    )


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _show_user_alerts(update.effective_user.id, update.message)


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Использование: /delete BTCUSDT 61000")
        return
    symbol = args[0].upper()
    price = _parse_price(args[1])
    if price is None:
        await update.message.reply_text("Цена должна быть числом.")
        return
    removed = alert_mgr.delete_alert(update.effective_user.id, symbol, price)
    if removed:
        await update.message.reply_text(f"Удалён алерт: {symbol} @ {price}")
    else:
        await update.message.reply_text(f"Алерт {symbol} @ {price} не найден.")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    removed = alert_mgr.delete_user_alerts(update.effective_user.id)
    await update.message.reply_text(f"Удалено алертов: {removed}")


async def _show_user_alerts(user_id: int, message):
    user_alerts = alert_mgr.get_user_alerts(user_id)
    if not user_alerts:
        await message.reply_text(
            "У вас нет активных алертов.", reply_markup=_main_menu_keyboard()
        )
        return
    lines = ["📋 Ваши алерты:\n"]
    for a in user_alerts:
        lines.append(f"• {a['symbol']} @ {a['price']}")
    await message.reply_text("\n".join(lines), reply_markup=_main_menu_keyboard())


async def _process_alert_input(update: Update, text: str):
    user_id = update.effective_user.id
    user_states.pop(user_id, None)

    parts = text.strip().split()
    if len(parts) != 2:
        await update.message.reply_text(
            "Неверный формат. Введите: BTC 63500",
            reply_markup=_main_menu_keyboard(),
        )
        return

    raw_symbol = parts[0].upper()
    if not raw_symbol.endswith("USDT"):
        symbol = raw_symbol + "USDT"
    else:
        symbol = raw_symbol

    price = _parse_price(parts[1])
    if price is None:
        await update.message.reply_text(
            "Цена должна быть числом (63500 или 150,5).",
            reply_markup=_main_menu_keyboard(),
        )
        return

    current_price = await binance.get_price(symbol)
    if current_price is None:
        await update.message.reply_text(
            f"Пара <b>{symbol}</b> не найдена на Binance Futures.",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
        return

    added = alert_mgr.add_alert(user_id, symbol, price)
    if added:
        await update.message.reply_text(
            f"✅ Алерт создан: <b>{symbol}</b> @ <b>{price}</b>\n"
            f"Текущая цена: <b>{current_price}</b>",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"⚠️ Алерт <b>{symbol}</b> @ <b>{price}</b> уже существует.",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Сначала проверяем ждём ли мы ввод от пользователя
    if user_states.get(user_id) == "waiting_alert_input":
        await _process_alert_input(update, text)
        return

    # Умное распознавание: "BTC 63500" / "btc 63500" / "Sol 150,5"
    if _ALERT_RE.match(text):
        await _process_alert_input(update, text)
        return

    await update.message.reply_text(
        "Используйте /start для навигации.",
        reply_markup=_main_menu_keyboard(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "my_alerts":
        user_alerts = alert_mgr.get_user_alerts(user_id)
        if not user_alerts:
            await query.edit_message_text(
                "У вас нет активных алертов.",
                reply_markup=_main_menu_keyboard(),
            )
            return
        lines = ["📋 Ваши алерты:\n"]
        for a in user_alerts:
            lines.append(f"• {a['symbol']} @ {a['price']}")
        await query.edit_message_text(
            "\n".join(lines), reply_markup=_main_menu_keyboard()
        )

    elif query.data == "new_alert":
        user_states[user_id] = "waiting_alert_input"
        await query.edit_message_text(
            "Введите монету и цену. Например: <b>BTC 63500</b>",
            parse_mode="HTML",
        )

    elif query.data == "stop_all":
        removed = alert_mgr.delete_user_alerts(user_id)
        await query.edit_message_text(
            f"Удалено алертов: {removed}",
            reply_markup=_main_menu_keyboard(),
        )


async def monitor_prices(app):
    logger.info("Запуск мониторинга цен (интервал %s сек)", CHECK_INTERVAL)
    tick_count = 0

    while True:
        try:
            alerts = alert_mgr.get_all_active()
            if not alerts:
                await asyncio.sleep(CHECK_INTERVAL)
                tick_count += 1
                continue

            symbols = list({a["symbol"] for a in alerts})
            prices = {}

            for symbol in symbols:
                price = await binance.get_price(symbol)
                if price is not None:
                    prices[symbol] = price

            tick_count += 1
            if tick_count * CHECK_INTERVAL >= 30:
                tick_count = 0
                for sym, p in prices.items():
                    logger.info("Текущая цена %s: %s", sym, p)

            for alert in list(alerts):
                symbol = alert["symbol"]
                target = alert["price"]
                current = prices.get(symbol)

                if current is None:
                    continue

                if current >= target:
                    triggered = alert_mgr.remove_triggered(symbol, target)
                    for t in triggered:
                        await notifier.send_alert(
                            t["user_id"], symbol, target, current
                        )

            await asyncio.sleep(CHECK_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Ошибка мониторинга: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)


async def post_init(app):
    global notifier
    notifier = Notifier(telegram_bot=app.bot)

    commands = [
        BotCommand("start", "Меню"),
        BotCommand("alert", "Новый алерт"),
        BotCommand("alerts", "Мои алерты"),
        BotCommand("delete", "Удалить алерт"),
        BotCommand("stop", "Стоп все"),
    ]
    await app.bot.set_my_commands(commands)
    asyncio.create_task(monitor_prices(app))
    logger.info("Бот запущен и готов к работе")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env")
        return

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("alert", cmd_alert))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Запуск бота...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
