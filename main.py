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

try:
    from curl_cffi import requests as browser_requests
except ImportError:
    browser_requests = None
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
PARSER_PROXY_URL = os.getenv("PARSER_PROXY_URL", "").strip()
CHECK_INTERVAL_SECONDS = 2 * 60 * 60

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
    database_directory = os.path.dirname(os.path.abspath(DB_PATH))
    os.makedirs(database_directory, exist_ok=True)
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
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
    found_title: str | None = None
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
            found_title = found_title or title
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
    return found_title, None


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


def extract_ruble_price(text: str | None) -> int | None:
    if not text:
        return None
    normalized = html.unescape(text).replace("\xa0", " ")
    patterns = (
        r"(?:от\s*)?(\d{1,3}(?:[\s\u202f]\d{3})+|\d{2,9})(?:[,.]\d{1,2})?\s*(?:₽|руб(?:\.|лей|ля)?)",
        r"(?:₽|руб(?:\.|лей|ля)?)\s*(\d{1,3}(?:[\s\u202f]\d{3})+|\d{2,9})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            price = parse_price_value(match.group(1))
            if price:
                return price
    return None


def extract_embedded_value(page_html: str, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        patterns = (
            rf'"{re.escape(key)}"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            rf'\\"{re.escape(key)}\\"\s*:\s*\\"(.*?)(?<!\\)\\"',
        )
        for pattern in patterns:
            match = re.search(pattern, page_html, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            value = match.group(1)
            try:
                value = json.loads(f'"{value}"')
            except (json.JSONDecodeError, TypeError):
                value = value.replace("\\u0026", "&").replace("\\/", "/")
            value = clean_title(html.unescape(value))
            if value:
                return value
    return None


def extract_embedded_price(page_html: str, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        patterns = (
            rf'"{re.escape(key)}"\s*:\s*"?([^",}}]{{1,40}})"?',
            rf'\\"{re.escape(key)}\\"\s*:\s*\\"([^\\"]{{1,40}})',
        )
        for pattern in patterns:
            for match in re.finditer(pattern, page_html, flags=re.IGNORECASE):
                raw = html.unescape(match.group(1)).replace("\\u00a0", " ")
                price = extract_ruble_price(raw) or parse_price_value(raw)
                if price and 1 <= price <= 1_000_000_000:
                    return price
    return None


def extract_product_data(page_html: str, store_key: str) -> tuple[str, int]:
    soup = BeautifulSoup(page_html, "html.parser")
    visible_text = soup.get_text(" ", strip=True).lower()
    blocked_markers = (
        "access denied",
        "captcha",
        "проверка, что вы не робот",
        "подтвердите, что вы не робот",
        "доступ ограничен",
    )
    if len(page_html) < 1000 or any(marker in visible_text for marker in blocked_markers):
        raise ValueError("Магазин включил защиту от автоматических запросов.")

    title, price = extract_json_ld_product(soup)

    title_selectors = {
        "ozon": ['[data-widget="webProductHeading"] h1', "h1"],
        "wildberries": ["h1.product-page__title", "h1"],
        "yandex_market": ['[data-auto="productCardTitle"]', "h1"],
        "dns": ["h1.product-card-top__title", "h1"],
        "mvideo": ["h1.title", "h1"],
    }
    if not title:
        title = clean_title(
            first_text(soup, title_selectors.get(store_key, ["h1"]))
            or first_meta_content(
                soup,
                [
                    'meta[property="og:title"]',
                    'meta[name="twitter:title"]',
                    'meta[itemprop="name"]',
                ],
            )
        )

    price_selectors = {
        "ozon": [
            '[data-widget="webPrice"]',
            '[data-widget="webSale"]',
            '[data-widget="webCurrentSeller"]',
        ],
        "wildberries": [
            "ins.price-block__final-price",
            ".price-block__final-price",
            ".price-block__wallet-price",
        ],
        "yandex_market": [
            '[data-auto="snippet-price-current"]',
            '[data-auto="price-value"]',
            '[data-auto="mainPrice"]',
        ],
        "dns": [
            ".product-buy__price",
            ".product-card-top__price-current",
            "[data-commerce-target=price]",
        ],
        "mvideo": [
            ".price__main-value",
            ".product-price__sum-rubles",
            "[itemprop=price]",
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
        for selector in price_selectors.get(store_key, []):
            value = first_text(soup, [selector])
            price = extract_ruble_price(value) or (
                parse_price_value(value) if value and len(value) < 50 else None
            )
            if price:
                break

    embedded_title_keys = {
        "ozon": ("title", "productName", "name"),
        "wildberries": ("name", "imt_name", "goodsName"),
        "yandex_market": ("title", "productName", "name"),
        "dns": ("name", "productName", "title"),
        "mvideo": ("name", "productName", "title"),
    }
    embedded_price_keys = {
        "ozon": (
            "cardPrice",
            "priceWithCard",
            "finalPrice",
            "salePrice",
            "currentPrice",
            "price",
        ),
        "wildberries": ("salePriceU", "salePrice", "price", "basicPriceU"),
        "yandex_market": ("currentPrice", "value", "price"),
        "dns": ("currentPrice", "finalPrice", "price"),
        "mvideo": ("salePrice", "currentPrice", "price"),
    }

    if not title:
        title = extract_embedded_value(page_html, embedded_title_keys[store_key])
    if not price:
        price = extract_embedded_price(page_html, embedded_price_keys[store_key])
        if store_key == "wildberries" and price and price > 10_000_000:
            price //= 100

    if not title or not price:
        logger.warning(
            "Парсер не нашёл данные: store=%s html_size=%s title=%s price=%s",
            store_key,
            len(page_html),
            bool(title),
            price,
        )
        raise ValueError("Не удалось получить название или текущую цену товара.")

    return title, price


class StoreAccessBlocked(ValueError):
    pass


def page_is_blocked(page_html: str) -> bool:
    text = BeautifulSoup(page_html, "html.parser").get_text(" ", strip=True).lower()
    markers = (
        "access denied",
        "captcha",
        "проверка, что вы не робот",
        "подтвердите, что вы не робот",
        "доступ ограничен",
        "похоже, нет соединения",
        "выключите vpn",
        "инцидент:",
        "abt-challenge",
    )
    return any(marker in text or marker in page_html.lower() for marker in markers)


def request_product_page(url: str, store_key: str) -> tuple[str, str]:
    last_error: Exception | None = None
    proxies = (
        {"http": PARSER_PROXY_URL, "https": PARSER_PROXY_URL}
        if PARSER_PROXY_URL
        else None
    )

    if store_key == "ozon" and not PARSER_PROXY_URL:
        logger.warning(
            "PARSER_PROXY_URL не задан. Ozon обычно блокирует IP облачных серверов."
        )

    if browser_requests is not None:
        for browser in ("chrome", "chrome124", "safari17_0"):
            try:
                response = browser_requests.get(
                    url,
                    headers=REQUEST_HEADERS,
                    cookies={"adult": "1"},
                    proxies=proxies,
                    timeout=35,
                    allow_redirects=True,
                    impersonate=browser,
                )
                if page_is_blocked(response.text):
                    last_error = StoreAccessBlocked(
                        "Магазин заблокировал IP сервера Railway."
                    )
                    continue
                if response.status_code < 400 and len(response.text) >= 1000:
                    return str(response.url), response.text
                last_error = ValueError(
                    f"HTTP {response.status_code}, размер {len(response.text)}"
                )
            except Exception as error:
                last_error = error

    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    session.cookies.update({"adult": "1"})
    try:
        response = session.get(
            url,
            proxies=proxies,
            timeout=(10, 35),
            allow_redirects=True,
        )
        if page_is_blocked(response.text):
            raise StoreAccessBlocked("Магазин заблокировал IP сервера Railway.")
        response.raise_for_status()
        return response.url, response.text
    except Exception as error:
        last_error = error

    if isinstance(last_error, StoreAccessBlocked):
        raise last_error
    raise ValueError(f"Не удалось загрузить страницу магазина: {last_error}")


def fetch_product(url: str, store_key: str) -> tuple[str, int]:
    final_url, page_html = request_product_page(url, store_key)

    if not is_valid_store_url(final_url, store_key):
        raise ValueError("Магазин перенаправил ссылку на другой сайт.")

    return extract_product_data(page_html, store_key)


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
    except StoreAccessBlocked as error:
        logger.warning("Магазин заблокировал запрос %s: %s", url, error)
        await wait_message.edit_text(
            text=(
                f"⚠️ <b>Ozon заблокировал подключение сервера.</b>\n\n"
                f"Ссылка правильная, но Ozon не показывает карточку товара "
                f"серверу Railway. Для Ozon требуется российский "
                f"резидентский прокси в переменной PARSER_PROXY_URL."
            ),
            parse_mode="HTML",
            reply_markup=build_cancel_tracking_keyboard(),
        )
        return
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

    if app.job_queue is not None:
        app.job_queue.run_repeating(
            check_all_prices,
            interval=CHECK_INTERVAL_SECONDS,
            first=60,
            name="price_check_every_2_hours",
        )
    else:
        logger.error(
            "JobQueue недоступен: автоматическая проверка цен отключена, "
            "но бот продолжит работать."
        )

    logger.info("Бот запущен. Long polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
