import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

D = "━━━━━━━━━━━━━━━━"

MAIN_TEXT = (
    f"💎 <b>Добро пожаловать!</b>\n\n"
    f"🔥 <b>Лучшие скидки каждый день</b>\n\n"
    f"{D}\n\n"
    f"🛒 Wildberries\n"
    f"🟣 Ozon\n"
    f"🟡 AliExpress\n"
    f"🎮 Steam\n"
    f"🎁 Промокоды\n"
    f"💸 Горячие акции\n\n"
    f"{D}\n\n"
    f"Выберите категорию ниже 👇"
)

PAGES = {
    "hot": (
        f"🔥 <b>Горячие скидки</b>\n\n"
        f"{D}\n\n"
        f"💥 Пока свежих скидок нет.\n\n"
        f"⏳ Скоро здесь появятся лучшие предложения.\n\n"
        f"{D}\n\n"
        f"🔔 Заходи чаще — обновляем каждый день!"
    ),
    "wb": (
        f"🛒 <b>Wildberries</b>\n\n"
        f"{D}\n\n"
        f"💜 Лучшие скидки на Wildberries появятся здесь.\n\n"
        f"⏳ Раздел скоро наполнится горячими предложениями.\n\n"
        f"{D}\n\n"
        f"🔔 Следи за обновлениями!"
    ),
    "ozon": (
        f"🟣 <b>Ozon</b>\n\n"
        f"{D}\n\n"
        f"🛍 Скидки и акции Ozon скоро здесь.\n\n"
        f"⏳ Раздел в процессе наполнения.\n\n"
        f"{D}\n\n"
        f"🔔 Возвращайся за лучшими предложениями!"
    ),
    "ali": (
        f"🟡 <b>AliExpress</b>\n\n"
        f"{D}\n\n"
        f"🌏 Лучшие предложения AliExpress — скоро здесь.\n\n"
        f"⏳ Ищем для тебя самые выгодные скидки.\n\n"
        f"{D}\n\n"
        f"🔔 Следи за обновлениями!"
    ),
    "games": (
        f"🎮 <b>Игры</b>\n\n"
        f"{D}\n\n"
        f"🕹 Скидки на игры в Steam, PSN, Xbox и других магазинах.\n\n"
        f"⏳ Раздел скоро наполнится горячими предложениями.\n\n"
        f"{D}\n\n"
        f"🔔 Заходи — обновляем ежедневно!"
    ),
    "promo": (
        f"🎁 <b>Промокоды</b>\n\n"
        f"{D}\n\n"
        f"🏷 Активные промокоды появятся здесь.\n\n"
        f"⏳ Собираем лучшие коды специально для тебя.\n\n"
        f"{D}\n\n"
        f"🔔 Возвращайся за скидками!"
    ),
    "favorites": (
        f"⭐ <b>Избранное</b>\n\n"
        f"{D}\n\n"
        f"📌 Здесь будут сохраняться твои любимые скидки.\n\n"
        f"⏳ Функция в разработке — уже скоро!\n\n"
        f"{D}\n\n"
        f"💎 Следи за обновлениями!"
    ),
    "about": (
        f"ℹ️ <b>О боте</b>\n\n"
        f"{D}\n\n"
        f"💎 <b>Скидки и Промокоды</b> — твой личный охотник за выгодой.\n\n"
        f"📦 Wildberries · Ozon · AliExpress\n"
        f"🎮 Игры · 🎁 Промокоды · 🔥 Акции\n\n"
        f"Мы отбираем только лучшие предложения,\n"
        f"чтобы ты экономил каждый день.\n\n"
        f"{D}\n\n"
        f"🚀 Версия 1.0"
    ),
}


def build_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔥 Горячие скидки", callback_data="hot"),
                InlineKeyboardButton("🛒 Wildberries", callback_data="wb"),
            ],
            [
                InlineKeyboardButton("🟣 Ozon", callback_data="ozon"),
                InlineKeyboardButton("🟡 AliExpress", callback_data="ali"),
            ],
            [
                InlineKeyboardButton("🎮 Игры", callback_data="games"),
                InlineKeyboardButton("🎁 Промокоды", callback_data="promo"),
            ],
            [
                InlineKeyboardButton("⭐ Избранное", callback_data="favorites"),
                InlineKeyboardButton("ℹ️ О боте", callback_data="about"),
            ],
        ]
    )


def build_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        text=MAIN_TEXT,
        parse_mode="HTML",
        reply_markup=build_main_keyboard(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "back":
        await query.edit_message_text(
            text=MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=build_main_keyboard(),
        )
        return

    text = PAGES.get(query.data)
    if text:
        await query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=build_back_keyboard(),
        )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        text=(
            "❓ <b>Неизвестная команда.</b>\n\n"
            "Нажми /start чтобы открыть главное меню."
        ),
        parse_mode="HTML",
    )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Ошибка при обработке обновления:", exc_info=context.error)


def main() -> None:
    token = os.environ["BOT_TOKEN"]

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))
    app.add_error_handler(handle_error)

    logger.info("Бот запущен. Long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
