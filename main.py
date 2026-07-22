import asyncio
import html
import json
import logging
import os
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

D = "━━━━━━━━━━━━━━━━"
DB_PATH = os.getenv("TRACKING_DB_PATH", "price_tracking.db")
CHECK_INTERVAL_SECONDS = 6 * 60 * 60

MAIN_TEXT = (
    f"💎 **Добро пожаловать!**\n\n"
    f"🔥 **Лучшие скидки каждый день**\n\n"
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
        f"🔥 **Горячие скидки**\n\n"
        f"{D}\n\n"
        f"💥 Пока свежих скидок нет.\n\n"
        f"⏳ Скоро здесь появятся лучшие предложения.\n\n"
        f"{D}\n\n"
        f"🔔 Заходи чаще — обновляем каждый день!"
    ),
    "wb": (
        f"🛒 **Wildberries**\n\n"
        f"{D}\n\n"
        f"💜 Лучшие скидки на Wildberries появятся здесь.\n\n"
        f"⏳ Раздел скоро наполнится горячими предложениями.\n\n"
        f"{D}\n\n"
        f"🔔 Следи за обновлениями!"
    ),
    "ozon": (
        f"🟣 **Ozon**\n\n"
        f"{D}\n\n"
        f"🛍 Скидки и акции Ozon скоро здесь.\n\n"
        f"⏳ Раздел в процессе наполнения.\n\n"
        f"{D}\n\n"
        f"🔔 Возвращайся за лучшими предложениями!"
    ),
    "ali": (
        f"🟡 **AliExpress**\n\n"
        f"{D}\n\n"
        f"🌏 Лучшие предложения AliExpress — скоро здесь.\n\n"
        f"⏳ Ищем для тебя самые выгодные скидки.\n\n"
        f"{D}\n\n"
        f"🔔 Следи за обновлениями!"
    ),
    "games": (
        f"🎮 **Игры**\n\n"
        f"{D}\n\n"
        f"🕹 Скидки на игры в Steam, PSN, Xbox и других магазинах.\n\n"
        f"⏳ Раздел скоро наполнится горячими предложениями.\n\n"
        f"{D}\n\n"
        f"🔔 Заходи — обновляем ежедневно!"
    ),
    "promo": (
        f"🎁 **Промокоды**\n\n"
        f"{D}\n\n"
        f"🏷 Активные промокоды появятся здесь.\n\n"
        f"⏳ Собираем лучшие коды специально для тебя.\n\n"
        f"{D}\n\n"
        f"🔔 Возвращайся за скидками!"
    ),
    "favorites": (
        f"⭐ **Избранное**\n\n"
        f"{D}\n\n"
        f"📌 Здесь будут сохраняться твои любимые скидки.\n\n"
        f"⏳ Функция в разработке — уже скоро!\n\n"
        f"{D}\n\n"
        f"💎 Следи за обновлениями!"
    ),
    "about": (
        f"ℹ️ **О боте**\n\n"
        f"{D}\n\n"
        f"💎 **Скидки и Промокоды** — твой личный охотник за выгодой.\n\n"
        f"📦 Wildberries · Ozon · AliExpress\n"
        f"🎮 Игры · 🎁 Промокоды · 🔥 Акции\n\n"
        f"Мы отбираем только лучшие предложения,\n"
        f"чтобы ты экономил каждый день.\n\n"
        f"{D}\n\n"
        f"🚀 Версия 1.0"
    ),
}

STORES = {
    "ozon": {
        "name": "Ozon",
        "button": "🟣 Ozon",
        "domains": ("ozon.ru",),
    },
    "wildberries": {
        "name": "Wildberries",
        "button": "🟪 Wildberries",
        "domains": ("wildberries.ru",),
    },
    "yandex_market": {
        "name": "Яндекс Маркет",
        "button": "🟡 Яндекс Маркет",
        "domains": ("market.yandex.ru",),
    },
    "dns": {
        "name": "DNS",
        "button": "⚪ DNS",
        "domains": ("dns-shop.ru",),
    },
    "mvideo": {
        "name": "М.Видео",
        "button": "🔵 М.Видео",
        "domains": ("mvideo.ru",),
    },
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS price_trackings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                store TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                price INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_trackings_user_id "
            "ON price_trackings(user_id)"
        )


def add_tracking(
    user_id: int,
    chat_id: int,
    store: str,
    url: str,
    title: str,
    price: int,
) -> tuple[int, bool]:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM price_trackings WHERE user_id = ? AND url = ?",
            (user_id, url),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE price_trackings
                SET chat_id = ?, store = ?, title = ?, price = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (chat_id, store, title, price, existing["id"]),
            )
            return int(existing["id"]), False

        cursor = connection.execute(
            """
            INSERT INTO price_trackings
                (user_id, chat_id, store, url, title, price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, store, url, title, price),
        )
        return int(cursor.lastrowid), True


def get_user_trackings(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, user_id, chat_id, store, url, title, price
            FROM price_trackings
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()


def get_tracking(tracking_id: int, user_id: int | None = None) -> sqlite3.Row | None:
    with get_connection() as connection:
        if user_id is None:
            return connection.execute(
                """
                SELECT id, user_id, chat_id, store, url, title, price
                FROM price_trackings WHERE id = ?
                """,
                (tracking_id,),
            ).fetchone()
        return connection.execute(
            """
            SELECT id, user_id, chat_id, store, url, title, price
            FROM price_trackings WHERE id = ? AND user_id = ?
            """,
            (tracking_id, user_id),
        ).fetchone()


def get_all_trackings() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, user_id, chat_id, store, url, title, price
            FROM price_trackings
            ORDER BY id
            """
        ).fetchall()


def update_tracking_price(tracking_id: int, title: str, price: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE price_trackings
            SET title = ?, price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, price, tracking_id),
        )


def delete_tracking(tracking_id: int, user_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM price_trackings WHERE id = ? AND user_id = ?",
            (tracking_id, user_id),
        )
        return cursor.rowcount > 0


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
            [
                InlineKeyboardButton(
                    "📦 Отслеживание цен", callback_data="price_tracking"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📦 Мои отслеживания", callback_data="my_trackings"
                ),
            ],
        ]
    )


def build_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
    )


def build_stores_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(store["button"], callback_data=f"store:{store_key}")]
        for store_key, store in STORES.items()
    ]
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def build_cancel_tracking_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Назад", callback_data="price_tracking")]]
    )


def build_trackings_keyboard(trackings: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tracking in trackings:
        tracking_id = int(tracking["id"])
        rows.append(
            [
                InlineKeyboardButton(
                    "🔄 Проверить сейчас",
                    callback_data=f"tracking_check:{tracking_id}",
                ),
                InlineKeyboardButton(
                    "🗑 Удалить",
                    callback_data=f"tracking_delete:{tracking_id}",
                ),
            ]
        )
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def is_valid_store_url(url: str, store_key: str) -> bool:
    store = STORES.get(store_key)
    if not store:
        return False

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower().rstrip(".")
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in store["domains"]
    )


def clean_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    title = re.sub(r"\s+", " ", value).strip()
    if not title:
        return None
    return title[:500]


def parse_price_value(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return None

    cleaned = re.sub(r"[^\d,.-]", "", text)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        integer_part, decimal_part = cleaned.rsplit(",", 1)
        if len(decimal_part) in {1, 2}:
            cleaned = integer_part.replace(",", "") + "." + decimal_part
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    elif "." in cleaned:
        integer_part, decimal_part = cleaned.rsplit(".", 1)
        if len(decimal_part) not in {1, 2}:
            cleaned = cleaned.replace(".", "")

    try:
        price = int(Decimal(cleaned).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        return None

    return price if price > 0 else None


def iter_json_objects(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_objects(child)


def extract_json_ld_product(soup: BeautifulSoup) -> tuple[str | None, int | None]:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in iter_json_objects(data):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "Product" not in types:
                continue

            title = clean_title(item.get("name"))
            offers = item.get("offers")
            offer_items = offers if isinstance(offers, list) else [offers]
            for offer in offer_items:
                if not isinstance(offer, dict):
                    continue
                price = parse_price_value(
                    offer.get("price")
                    or offer.get("lowPrice")
                    or offer.get("highPrice")
                )
                if title and price:
                    return title, price
    return None, None


def first_meta_content(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def first_text(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag:
            value = tag.get("content") or tag.get_text(" ", strip=True)
            if value:
                return str(value).strip()
    return None


def extract_product_data(page_html: str, store_key: str) -> tuple[str, int]:
    soup = BeautifulSoup(page_html, "html.parser")

    title, price = extract_json_ld_product(soup)

    if not title:
        title = clean_title(
            first_meta_content(
                soup,
                [
                    'meta[property="og:title"]',
                    'meta[name="twitter:title"]',
                    'meta[itemprop="name"]',
                ],
            )
            or first_text(soup, ["h1"])
        )

    price_selectors = {
        "ozon": [
            '[data-widget="webPrice"] span',
            '[data-widget="webSale"] span',
        ],
        "wildberries": [
            "ins.price-block__final-price",
            ".price-block__final-price",
        ],
        "yandex_market": [
            '[data-auto="snippet-price-current"]',
            '[data-auto="price-value"]',
        ],
        "dns": [
            ".product-buy__price",
            ".product-card-top__price-current",
        ],
        "mvideo": [
            ".price__main-value",
            ".product-price__sum-rubles",
        ],
    }

    if not price:
        price = parse_price_value(
            first_meta_content(
                soup,
                [
                    'meta[property="product:price:amount"]',
                    'meta[itemprop="price"]',
                    'meta[name="price"]',
                ],
            )
        )

    if not price:
        price = parse_price_value(
            first_text(soup, price_selectors.get(store_key, []))
        )

    if not price:
        patterns = [
            r'"(?:finalPrice|salePrice|currentPrice|price)"\s*:\s*"?(\d{1,9}(?:[.,]\d{1,2})?)"?',
            r'"price"\s*:\s*\{[^{}]{0,500}?"value"\s*:\s*"?(\d{1,9}(?:[.,]\d{1,2})?)"?',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_html, flags=re.IGNORECASE)
            if match:
                price = parse_price_value(match.group(1))
                if price:
                    break

    if not title or not price:
        raise ValueError("Не удалось получить название или цену товара.")

    return title, price


def fetch_product(url: str, store_key: str) -> tuple[str, int]:
    response = requests.get(
        url,
        headers=REQUEST_HEADERS,
        timeout=(10, 25),
        allow_redirects=True,
    )
    response.raise_for_status()

    if not is_valid_store_url(response.url, store_key):
        raise ValueError("Магазин перенаправил ссылку на другой сайт.")

    return extract_product_data(response.text, store_key)


def format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ") + " ₽"


def format_trackings_text(trackings: list[sqlite3.Row]) -> str:
    if not trackings:
        return (
            f"📦 <b>Мои отслеживания</b>\n\n"
            f"{D}\n\n"
            f"У вас пока нет отслеживаемых товаров.\n\n"
            f"Добавьте товар через раздел «📦 Отслеживание цен».\n\n"
            f"{D}"
        )

    parts = [f"📦 <b>Мои отслеживания</b>\n\n{D}"]
    for index, tracking in enumerate(trackings, start=1):
        store_name = STORES.get(tracking["store"], {}).get(
            "name", tracking["store"]
        )
        parts.append(
            f"\n\n<b>{index}. {html.escape(str(tracking['title']))}</b>\n"
            f"🏪 {html.escape(str(store_name))}\n"
            f"💰 {format_price(int(tracking['price']))}"
        )
    parts.append(f"\n\n{D}\n\nВыберите действие ниже 👇")
    return "".join(parts)


def format_price_change_message(title: str, old_price: int, new_price: int) -> str:
    difference = abs(old_price - new_price)
    if new_price < old_price:
        return (
            f"📉 <b>Цена снизилась</b>\n\n"
            f"📦 {html.escape(title)}\n\n"
            f"Было\n\n{format_price(old_price)}\n\n"
            f"Стало\n\n{format_price(new_price)}\n\n"
            f"Экономия\n\n{format_price(difference)} 🎉"
        )
    return (
        f"📈 <b>Цена выросла</b>\n\n"
        f"📦 {html.escape(title)}\n\n"
        f"Было\n\n{format_price(old_price)}\n\n"
        f"Стало\n\n{format_price(new_price)}\n\n"
        f"Разница\n\n{format_price(difference)}"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("tracking_store", None)
    await update.message.reply_text(
        text=MAIN_TEXT,
        parse_mode="HTML",
        reply_markup=build_main_keyboard(),
    )


async def show_main_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("tracking_store", None)
    await query.edit_message_text(
        text=MAIN_TEXT,
        parse_mode="HTML",
        reply_markup=build_main_keyboard(),
    )


async def show_tracking_stores(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("tracking_store", None)
    await query.edit_message_text(
        text=(
            f"📦 <b>Отслеживание цен</b>\n\n"
            f"{D}\n\n"
            f"Выберите магазин 👇\n\n"
            f"{D}"
        ),
        parse_mode="HTML",
        reply_markup=build_stores_keyboard(),
    )


async def show_my_trackings(query, user_id: int) -> None:
    trackings = get_user_trackings(user_id)
    await query.edit_message_text(
        text=format_trackings_text(trackings),
        parse_mode="HTML",
        reply_markup=build_trackings_keyboard(trackings),
        disable_web_page_preview=True,
    )


async def check_one_tracking(
    tracking: sqlite3.Row,
) -> tuple[str, int, int, bool]:
    title, new_price = await asyncio.to_thread(
        fetch_product, tracking["url"], tracking["store"]
    )
    old_price = int(tracking["price"])
    changed = new_price != old_price
    update_tracking_price(int(tracking["id"]), title, new_price)
    return title, old_price, new_price, changed


async def handle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data == "back":
        await show_main_menu(query, context)
        return

    if data == "price_tracking":
        await show_tracking_stores(query, context)
        return

    if data == "my_trackings":
        context.user_data.pop("tracking_store", None)
        await show_my_trackings(query, query.from_user.id)
        return

    if data.startswith("store:"):
        store_key = data.split(":", 1)[1]
        store = STORES.get(store_key)
        if not store:
            await query.answer("Магазин не найден.", show_alert=True)
            return

        context.user_data["tracking_store"] = store_key
        await query.edit_message_text(
            text=(
                f"{D}\n\n"
                f"🔗 <b>Отправьте ссылку на товар.</b>\n\n"
                f"Например:\n\n"
                f"https://www.{store['domains'][0]}/...\n\n"
                f"{D}"
            ),
            parse_mode="HTML",
            reply_markup=build_cancel_tracking_keyboard(),
            disable_web_page_preview=True,
        )
        return

    if data.startswith("tracking_check:"):
        try:
            tracking_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Некорректный товар.", show_alert=True)
            return

        tracking = get_tracking(tracking_id, query.from_user.id)
        if not tracking:
            await query.answer("Товар не найден.", show_alert=True)
            return

        await query.answer("Проверяю цену…")
        try:
            title, old_price, new_price, changed = await check_one_tracking(tracking)
        except (requests.RequestException, ValueError) as error:
            logger.warning("Не удалось проверить товар %s: %s", tracking_id, error)
            await query.message.reply_text(
                text=(
                    f"⚠️ <b>Не удалось проверить цену.</b>\n\n"
                    f"Магазин временно не отдал данные. Попробуйте позже."
                ),
                parse_mode="HTML",
            )
            return

        if changed:
            await query.message.reply_text(
                text=format_price_change_message(title, old_price, new_price),
                parse_mode="HTML",
            )
        else:
            await query.message.reply_text(
                text=(
                    f"✅ <b>Цена не изменилась.</b>\n\n"
                    f"📦 {html.escape(title)}\n\n"
                    f"💰 {format_price(new_price)}"
                ),
                parse_mode="HTML",
            )
        await show_my_trackings(query, query.from_user.id)
        return

    if data.startswith("tracking_delete:"):
        try:
            tracking_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Некорректный товар.", show_alert=True)
            return

        if delete_tracking(tracking_id, query.from_user.id):
            await query.answer("Товар удалён.")
        else:
            await query.answer("Товар не найден.", show_alert=True)
        await show_my_trackings(query, query.from_user.id)
        return

    text = PAGES.get(data)
    if text:
        context.user_data.pop("tracking_store", None)
        await query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=build_back_keyboard(),
        )


async def handle_tracking_link(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    store_key = context.user_data.get("tracking_store")
    if not store_key:
        await handle_unknown(update, context)
        return

    store = STORES.get(store_key)
    url = (update.message.text or "").strip()

    if not is_valid_store_url(url, store_key):
        await update.message.reply_text(
            text=(
                f"❌ <b>Ссылка не подходит.</b>\n\n"
                f"Отправьте ссылку на товар магазина "
                f"<b>{html.escape(store['name'])}</b>.\n\n"
                f"Проверьте адрес и попробуйте ещё раз."
            ),
            parse_mode="HTML",
            reply_markup=build_cancel_tracking_keyboard(),
            disable_web_page_preview=True,
        )
        return

    wait_message = await update.message.reply_text("⏳ Получаю название и цену товара…")
    try:
        title, price = await asyncio.to_thread(fetch_product, url, store_key)
    except requests.Timeout:
        await wait_message.edit_text(
            text=(
                f"⚠️ <b>Магазин отвечает слишком долго.</b>\n\n"
                f"Попробуйте отправить ссылку ещё раз немного позже."
            ),
            parse_mode="HTML",
            reply_markup=build_cancel_tracking_keyboard(),
        )
        return
    except (requests.RequestException, ValueError) as error:
        logger.warning("Не удалось добавить товар %s: %s", url, error)
        await wait_message.edit_text(
            text=(
                f"⚠️ <b>Не удалось получить данные товара.</b>\n\n"
                f"Убедитесь, что ссылка открывает карточку товара, "
                f"и попробуйте ещё раз."
            ),
            parse_mode="HTML",
            reply_markup=build_cancel_tracking_keyboard(),
        )
        return

    add_tracking(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        store=store_key,
        url=url,
        title=title,
        price=price,
    )
    context.user_data.pop("tracking_store", None)

    await wait_message.edit_text(
        text=(
            f"✅ <b>Товар добавлен.</b>\n\n"
            f"📦 {html.escape(title)}\n\n"
            f"💰 {format_price(price)}\n\n"
            f"🔔 Теперь я автоматически сообщу, если цена изменится."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📦 Мои отслеживания", callback_data="my_trackings"
                    )
                ],
                [InlineKeyboardButton("🔙 Назад", callback_data="back")],
            ]
        ),
        disable_web_page_preview=True,
    )


async def check_all_prices(context: ContextTypes.DEFAULT_TYPE) -> None:
    trackings = get_all_trackings()
    logger.info("Плановая проверка цен: %s товаров", len(trackings))

    for tracking in trackings:
        try:
            title, old_price, new_price, changed = await check_one_tracking(tracking)
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                "Плановая проверка товара %s не удалась: %s",
                tracking["id"],
                error,
            )
            continue
        except Exception:
            logger.exception(
                "Непредвиденная ошибка проверки товара %s", tracking["id"]
            )
            continue

        if not changed:
            continue

        try:
            await context.bot.send_message(
                chat_id=int(tracking["chat_id"]),
                text=format_price_change_message(title, old_price, new_price),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Не удалось отправить уведомление пользователю %s",
                tracking["user_id"],
            )

        await asyncio.sleep(1)


async def handle_unknown(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.message.reply_text(
        text=(
            "❓ **Неизвестная команда.**\n\n"
            "Нажми /start чтобы открыть главное меню."
        ),
        parse_mode="HTML",
    )


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Ошибка при обработке обновления:", exc_info=context.error)


def main() -> None:
    token = os.environ["BOT_TOKEN"]
    init_database()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tracking_link)
    )
    app.add_error_handler(handle_error)

    if app.job_queue is None:
        raise RuntimeError(
            "JobQueue недоступен. Установите python-telegram-bot[job-queue]."
        )
    app.job_queue.run_repeating(
        check_all_prices,
        interval=CHECK_INTERVAL_SECONDS,
        first=CHECK_INTERVAL_SECONDS,
        name="price_check_every_6_hours",
    )

    logger.info("Бот запущен. Long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
