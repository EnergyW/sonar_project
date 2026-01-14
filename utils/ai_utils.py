import os
import logging
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI
import httpx
from httpx_socks import AsyncProxyTransport
from utils.api_utils import get_store_products, get_ozon_product_attributes
import re
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
load_dotenv()

API_CLIENT: AsyncOpenAI = None
load_lock = asyncio.Lock()


async def init_ai_client():
    global API_CLIENT

    if API_CLIENT is not None:
        return API_CLIENT

    async with load_lock:
        if API_CLIENT is not None:
            return API_CLIENT

        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY не найден в переменных окружения")

            proxy_raw = os.getenv("PROXY")

            if proxy_raw:
                if not proxy_raw.startswith(("socks5://", "http://", "https://")):
                    proxy_url = f"socks5://{proxy_raw}"
                else:
                    proxy_url = proxy_raw

                logger.info(f"Используется прокси: {proxy_url}")

                transport = AsyncProxyTransport.from_url(proxy_url)

                http_client = httpx.AsyncClient(
                    transport=transport,
                    timeout=60.0
                )

                API_CLIENT = AsyncOpenAI(
                    api_key=api_key,
                    http_client=http_client
                )

                logger.info("✅ Async OpenAI клиент через SOCKS5 прокси")

            else:
                API_CLIENT = AsyncOpenAI(api_key=api_key)
                logger.info("⚠️ Async клиент без прокси (PROXY не указан)")

            return API_CLIENT

        except Exception as e:
            logger.exception(f"❌ Ошибка инициализации OpenAI клиента: {e}")
            API_CLIENT = AsyncOpenAI(api_key=api_key)
            logger.info("⚠️ Async клиент без прокси (fallback)")
            return API_CLIENT

def get_address_form(address_style: str) -> str:
    address_map = {
        'formal': 'Вы',
        'informal_vy': 'вы',
        'informal_ty': 'ты'
    }
    return address_map.get(address_style, 'Вы')

def build_minus_words_instruction(minus_words: list) -> str:
    if not minus_words or len(minus_words) == 0:
        return ""

    words_list = ", ".join([f"'{word}'" for word in minus_words])
    return (
        f"\n⚠️ ВАЖНО: НЕ используй следующие слова и фразы в ответе: {words_list}. "
        f"Найди синонимы или перефразируй, но избегай этих слов."
    )

async def generate_reply(
        review_text: str,
        rating: int,
        client_config: dict = None,
        store_products: list = None,
        product_name: str = None,
        supplier_article: str = None,
        sku: str = None,
        pros: str = None,
        cons: str = None,
        store_settings: dict = None,
        offer_id: str = None,
        product_id: str = None,
        reviewer_name: str = None
):

    logger.info("=" * 80)
    logger.info("🚀 НАЧАЛО ГЕНЕРАЦИИ ОТВЕТА НА ОТЗЫВ")
    logger.info(f"📝 Параметры функции:")
    logger.info(f"  - review_text: {review_text[:100]}..." if review_text else "  - review_text: None")
    logger.info(f"  - rating: {rating}")
    logger.info(f"  - product_name: {product_name}")
    logger.info(f"  - supplier_article: {supplier_article}")
    logger.info(f"  - sku: {sku}")
    logger.info(f"  - pros: {pros}")
    logger.info(f"  - cons: {cons}")
    logger.info(f"  - offer_id: {offer_id}")
    logger.info(f"  - product_id: {product_id}")
    logger.info(f"  - reviewer_name: {reviewer_name}")

    # ДОБАВЛЯЕМ ПОДРОБНОЕ ЛОГИРОВАНИЕ store_products
    logger.info("📊 АНАЛИЗ store_products:")
    logger.info(f"  - store_products передан: {store_products is not None}")
    if store_products is not None:
        logger.info(f"  - Тип: {type(store_products)}")
        logger.info(f"  - Длина: {len(store_products)}")
        if len(store_products) > 0:
            logger.info(f"  - Пример первого товара: {store_products[0][:100]}...")

    try:
        client = await init_ai_client()
        if not client:
            logger.error("❌ Не удалось инициализировать клиент OpenAI")
            return {
                "success": False,
                "error": "Не удалось инициализировать AI клиент"
            }

        # ---------- ПОЛУЧЕНИЕ НАСТРОЕК ----------
        platform = (client_config.get("platform") or "").lower() if client_config else "ozon"
        settings = store_settings or {}

        logger.info(f"📋 Получены настройки:")
        logger.info(f"  - platform: {platform}")
        logger.info(f"  - client_config keys: {list(client_config.keys()) if client_config else 'None'}")
        logger.info(f"  - store_settings keys: {list(settings.keys())}")

        # Параметры из БД
        address_style = settings.get('address_style', 'formal')
        use_name = settings.get('use_name', True)
        mention_product = settings.get('mention_product', True)
        response_length = settings.get('response_length', 'default')
        use_emojis = settings.get('use_emojis', True)
        delivery_method = settings.get('delivery_method', 'marketplace')
        tone = settings.get('tone', 'friendly')
        minus_words = settings.get('minus_words', [])

        logger.info(f"⚙️ Настройки магазина:")
        logger.info(f"  - address_style: {address_style}")
        logger.info(f"  - use_name: {use_name}")
        logger.info(f"  - mention_product: {mention_product}")
        logger.info(f"  - response_length: {response_length}")
        logger.info(f"  - use_emojis: {use_emojis}")
        logger.info(f"  - delivery_method: {delivery_method}")
        logger.info(f"  - tone: {tone}")
        logger.info(f"  - minus_words: {minus_words} (кол-во: {len(minus_words)})")

        if store_products is None and client_config:
            try:
                logger.info("📄 store_products не передан, получаем список товаров магазина...")
                store_products = await get_store_products(
                    client_config.get("client_id", ""),
                    client_config.get("api_key", ""),
                    client_config.get("platform", "Ozon")
                )
                logger.info(f"✅ Получено товаров через get_store_products: {len(store_products)}")
                if store_products and len(store_products) > 0:
                    logger.info(f"📦 Пример товара: {store_products[0][:150]}...")
                    logger.info(f"📦 Всего товаров: {len(store_products)}")
                else:
                    logger.warning("⚠️ Получен пустой список товаров!")
            except Exception as e:
                logger.error(f"❌ Ошибка при получении товаров магазина: {e}")
                logger.exception("Детали ошибки:")
                store_products = []
        else:
            logger.info(
                f"📦 Используем переданный список товаров (кол-во: {len(store_products) if store_products else 0})")

        address_form = get_address_form(address_style)
        logger.info(f"👤 Форма обращения: '{address_form}' (из address_style: {address_style})")

        logger.info(f"🛒 Платформа: {platform.upper()}")
        logger.info(f"📊 Детальные настройки: address_style={address_style} ({address_form}), "
                    f"response_length={response_length}, tone={tone}, use_name={use_name}")

        # ---------- БЛОК ДЛЯ WILDBERRIES ----------
        if platform == "wildberries":
            logger.info("🎯 Обработка для платформы WILDBERRIES")

            # 1. Настройки длины и тона
            length_desc = {
                'short': 'очень короткий (до 30 слов)',
                'default': 'короткий (до 70 слов)',
                'long': 'подробный (до 150 слов)'
            }.get(response_length, 'короткий (до 70 слов)')

            tone_desc = {
                'friendly': 'дружелюбный',
                'formal': 'формальный',
                'neutral': 'нейтральный'
            }.get(tone, 'дружелюбный')

            logger.info(f"📏 Длина ответа: {response_length} -> {length_desc}")
            logger.info(f"🎭 Тон ответа: {tone} -> {tone_desc}")

            # 2. Обработка имени клиента (только для WB)
            name_instruction = ""
            if use_name and reviewer_name:
                name_instruction = (
                    f"В начале ответа обратись к клиенту по имени: '{reviewer_name}'. "
                    f"Например: '{reviewer_name}, спасибо за отзыв!' или 'Здравствуйте, {reviewer_name}!'"
                )
                logger.info(f"👤 Использование имени клиента: ДА - '{reviewer_name}'")
                logger.info(f"   Инструкция: {name_instruction}")
            else:
                logger.info(f"👤 Использование имени клиента: НЕТ (use_name={use_name}, reviewer_name={reviewer_name})")

            # 3. Рекомендации товаров для WB
            recommendation_text = ""
            # ИСПРАВЛЕННАЯ ПРОВЕРКА: проверяем не просто наличие store_products, а что он не пустой
            if mention_product and store_products and len(store_products) > 0:
                logger.info(f"�️ Упоминание товаров: ДА, товаров получено: {len(store_products)}")

                short_products = []
                for i, prod in enumerate(store_products[:20]):
                    nm_match = re.search(r'\(nmID: (\d+)\)', prod)
                    nm_id = nm_match.group(1) if nm_match else ""
                    name_match = re.search(r'^([^(]+)', prod)
                    product_name_wb = name_match.group(1).strip() if name_match else prod
                    short_name = f"{product_name_wb} (Артикул: {nm_id})" if nm_id else product_name_wb
                    short_products.append(short_name)

                    if i < 3:  # Логируем только первые 3 для наглядности
                        logger.info(f"   Товар {i + 1}: {prod[:80]}...")

                products_list = "; ".join(short_products)
                recommendation_text = (
                    f"Сопутствующие товары: {products_list}. "
                    f"Если отзыв положительный и уместно — можешь ненавязчиво упомянуть один из них, "
                    f"но НЕ пиши 'выбран товар' и НЕ цитируй название полностью."
                )
                logger.info(f"📋 Текст рекомендаций сгенерирован ({len(recommendation_text)} символов)")
            else:
                recommendation_text = "Не упоминай другие товары."
                logger.info(f"�️ Упоминание товаров: НЕТ - mention_product={mention_product}, "
                            f"store_products существует: {store_products is not None}, "
                            f"длина store_products: {len(store_products) if store_products else 0}")

            # 4. Инструкция по запрещённым словам
            minus_words_instruction = build_minus_words_instruction(minus_words)
            if minus_words_instruction:
                logger.info(f"🚫 Запрещённые слова: {minus_words}")
                logger.info(f"   Инструкция: {minus_words_instruction[:200]}...")
            else:
                logger.info("🚫 Запрещённые слова: не указаны")

            # 5. Промпты для WB
            system_prompt = (
                f"Ты — вежливый и профессиональный помощник продавца на маркетплейсе Wildberries 🛒. "
                f"Твоя задача — написать {length_desc} {tone_desc} ответ на отзыв клиента. "
                f"Отвечай на русском, {'' if use_emojis else 'БЕЗ '}смайликов, естественно и по-человечески. "
                f"Используй обращение на '{address_form}'. "
                f"{name_instruction}\n"
                f"Если отзыв положительный (4—5): поблагодари, подчеркни плюсы и качество товара. "
                f"Если отзыв отрицательный (1—3): извинись, прояви заботу, предложи решение или помощь. "
                f"Не упоминай рейтинг явно. "
                f"ОБЯЗАТЕЛЬНО: упомяни в ответе название товара и его nmId (как 'Артикул'). "
                f"Supplier article можно указать в скобках. "
                f"Используй плюсы и минусы, если они есть, но не копируй дословно. "
                f"Не придумывай факты — только адаптируй отзыв в естественный ответ."
                f"{minus_words_instruction}"
            )

            logger.info(f"📋 SYSTEM PROMPT для WB:")
            logger.info(f"   Длина: {len(system_prompt)} символов")
            logger.info(f"   Начало: {system_prompt[:200]}...")

            user_prompt = (
                f"📦 Название товара: {product_name or 'Не указано'}\n"
                f"🔢 Артикул (nmId): {sku or 'Не указан'}\n"
                f"🏷️ Supplier Article: {supplier_article or 'Не указан'}\n"
                f"🌟 Оценка: {rating or 'Не указана'}\n"
                f"💬 Отзыв: {review_text or 'Без текста'}\n"
                f"➕ Плюсы: {pros or 'Не указано'}\n"
                f"➖ Минусы: {cons or 'Не указано'}\n"
            )

            if use_name and reviewer_name:
                user_prompt += f"👤 Имя клиента: {reviewer_name}\n"

            user_prompt += (
                f"🛒 {recommendation_text}\n\n"
                "Сформируй ответ продавца. "
                "Важно: обязательно вставь в текст название и артикул (nmId) товара, например: "
                "'Спасибо за отзыв о кресле (Артикул 466657417)!' "
                "Ответ должен быть естественным, дружелюбным, с заботой."
            )

            logger.info(f"👤 USER PROMPT для WB:")
            logger.info(f"   Длина: {len(user_prompt)} символов")
            logger.info(f"   Начало: {user_prompt[:300]}...")

            logger.info(f"📊 Детали товара WB:")
            logger.info(f"  - product_name: {product_name}")
            logger.info(f"  - sku: {sku}")
            logger.info(f"  - supplier_article: {supplier_article}")
            logger.info(f"  - reviewer_name: {reviewer_name}")

        # ---------- БЛОК ДЛЯ OZON ----------
        elif platform == "ozon":
            logger.info("🎯 Обработка для платформы OZON")

            product_attributes = {}
            product_description = ""
            characteristics_text = ""
            description_text = ""

            if client_config:
                try:
                    logger.info(f"🔍 Получение атрибутов товара Ozon...")
                    logger.info(f"   client_id: {client_config.get('client_id', '')[:10]}...")
                    logger.info(f"   offer_id: {offer_id}")
                    logger.info(f"   product_id: {product_id}")
                    logger.info(f"   sku: {sku}")

                    product_attributes = await get_ozon_product_attributes(
                        client_id=client_config.get("client_id", ""),
                        api_key=client_config.get("api_key", ""),
                        offer_id=offer_id,
                        product_id=product_id,
                        sku=sku
                    )
                    logger.info(f"✅ Получено атрибутов товара Ozon: {len(product_attributes)}")
                    logger.info(f"   Ключи атрибутов: {list(product_attributes.keys())}")

                    if product_attributes.get('description'):
                        product_description = product_attributes['description']
                        logger.info(f"📄 Описание товара получено: {len(product_description)} символов")

                        characteristics_text = await build_ozon_characteristics_text(product_attributes)
                        logger.info(f"📋 Характеристики сформированы: {len(characteristics_text)} символов")

                        clean_description = re.sub('<[^<]+?>', '', product_description)
                        clean_description = re.sub(r'\s+', ' ', clean_description).strip()
                        if len(clean_description) > 50:
                            description_text = clean_description[:200] + '...'
                        else:
                            description_text = clean_description

                        logger.info(f"🧹 Описание очищено: {len(description_text)} символов")

                except Exception as e:
                    logger.error(f"❌ Ошибка получения данных товара Ozon: {e}")
                    logger.exception("Детали ошибки:")
            else:
                logger.info("ℹ️ client_config не предоставлен, пропускаем получение атрибутов товара")

            length_desc = {
                'short': 'очень короткий (до 30 слов)',
                'default': 'короткий (до 70 слов)',
                'long': 'подробный (до 150 слов)'
            }.get(response_length, 'короткий (до 70 слов)')

            logger.info(f"📏 Длина ответа Ozon: {response_length} -> {length_desc}")

            recommendation_text = ""
            if mention_product and store_products and len(store_products) > 0:
                logger.info(f"🛒 Упоминание товаров Ozon: ДА, товаров получено: {len(store_products)}")

                short_products = []
                for i, prod in enumerate(store_products[:20]):
                    sku_match = re.search(r'\(sku: (\d+)\)', prod)
                    sku_prod = sku_match.group(1) if sku_match else ""
                    brand_match = re.search(r', ([A-Z]+[A-Za-z]*),', prod)
                    brand = brand_match.group(1) if brand_match else "Неизвестно"
                    name_parts = re.split(r', | \(', prod)[0].strip()
                    short_name = f"{name_parts} ({brand}, sku: {sku_prod})" if sku_prod and brand != "Неизвестно" else name_parts
                    short_products.append(short_name)

                    if i < 10:
                        logger.info(f"   Товар {i + 1}: {prod[:80]}...")

                products_list = "; ".join(short_products)

                if rating >= 4:
                    recommendation_text = (
                        f"📦 Сопутствующие товары магазина: {products_list}. "
                        f"ОБЯЗАТЕЛЬНО: Для положительного отзыва (4-5) порекомендуй один из этих товаров! "
                        f"Сделай это ненавязчиво, в контексте ответа. "
                        f"Пример: 'Также у нас есть массажное кресло для расслабления после работы' "
                        f"НЕ перечисляй все товары, НЕ пиши 'выбран товар', выбери ОДИН наиболее подходящий."
                    )
                    logger.info(f"📋 Явная инструкция на рекомендацию для рейтинга {rating}")
                else:
                    recommendation_text = "Не упоминай другие товары (отзыв отрицательный)."
                    logger.info(f"📋 Не рекомендуем товары для рейтинга {rating}")
            else:
                recommendation_text = "Не упоминай другие товары."
                logger.info(f"🛒 Упоминание товаров Ozon: НЕТ")

            minus_words_instruction = build_minus_words_instruction(minus_words)
            if minus_words_instruction:
                logger.info(f"🚫 Запрещённые слова Ozon: {minus_words}")
                logger.info(f"   Инструкция: {minus_words_instruction[:20]}...")
            else:
                logger.info("🚫 Запрещённые слова Ozon: не указаны")

            system_prompt = (
                f"Ты — живой, {tone} помощник продавца на Ozon {'😊' if use_emojis else ''} "
                f"Пиши естественно, по-человечески, не как робот. "
                f"Используй обращение на '{address_form}'. "
                f"Не упоминай конкретно какую оценку поставил пользователь. "
                f"Длинные официальные названия товаров НЕ используй — сокращай до понятных форм: "
                f"'кресле', 'матрас', 'массажёр', 'подушка' и т.п. "
                f"ВАЖНОЕ ПРАВИЛО: Если отзыв положительный (4-5 звёзд) — ОБЯЗАТЕЛЬНО порекомендуй один сопутствующий товар из списка. "
                f"Делай это мягко и уместно, например: 'Если хотите дополнить рабочее место, посмотрите наш массажёр для ног' "
                f"Отрицательный отзыв (1-3): извинись, прояви заботу и предложи написать в чат продавца. "
                f"Учитывай характеристики и описание товара при ответе, но не переписывай их явно. "
                f"Пиши {length_desc}, дружелюбно, {'с эмодзи' if use_emojis else 'БЕЗ эмодзи'}."
                f"{minus_words_instruction}"
            )

            logger.info(f"📋 SYSTEM PROMPT для Ozon:")
            logger.info(f"   Длина: {len(system_prompt)} символов")
            logger.info(f"   Начало: {system_prompt[:200]}...")

            user_prompt_parts = [
                f"📦 Название товара: {product_name or 'Не указано'}",
                f"🔢 sku: {sku or 'Не указан'}",
                f"⭐ Оценка: {rating or 'Не указана'}",
                f"💬 Отзыв: {review_text or 'Без текста'}"
            ]

            if characteristics_text:
                user_prompt_parts.append(f"📋 Характеристики товара: {characteristics_text[:500]}")
                logger.info(f"📊 Характеристики добавлены в промпт: {len(characteristics_text)} символов")

            if description_text:
                user_prompt_parts.append(f"📖 Описание товара: {description_text[:300]}")
                logger.info(f"📝 Описание добавлено в промпт: {len(description_text)} символов")

            user_prompt_parts.append(recommendation_text)
            user_prompt_parts.append(
                "Используй простое разговорное название товара, не длинное официальное. "
                "Учитывай характеристики и описание товара при формировании ответа, но не перечисляй их явно в ответе."
            )

            user_prompt = "\n".join(user_prompt_parts)

            logger.info(f"👤 USER PROMPT для Ozon:")
            logger.info(f"   Длина: {len(user_prompt)} символов")
            logger.info(f"   Начало: {user_prompt[:300]}...")

        else:
            logger.warning(f"⚠️ Неизвестная платформа: {platform}, используем общий шаблон")
            system_prompt = (
                f"Ты — вежливый помощник продавца. "
                f"Отвечай естественно, используя обращение на '{get_address_form(address_style)}'. "
                f"{'Используй эмодзи.' if use_emojis else 'Не используй эмодзи.'}"
            )
            user_prompt = f"Отзыв: {review_text}\nОценка: {rating}\nСформируй короткий вежливый ответ."

            logger.info(f"📋 SYSTEM PROMPT для неизвестной платформы:")
            logger.info(f"   {system_prompt}")
            logger.info(f"👤 USER PROMPT для неизвестной платформы:")
            logger.info(f"   {user_prompt}")

        # ---------- ОБЩАЯ ЧАСТЬ (для всех платформ) ----------
        logger.info("=" * 80)
        logger.info("🤖 ВЫЗОВ OPENAI API")
        logger.info(f"📊 Итоговые промпты:")
        logger.info(f"  - Системный промпт: {len(system_prompt)} символов")
        logger.info(f"  - Пользовательский промпт: {len(user_prompt)} символов")
        logger.info(f"  - Модель: gpt-5-nano-2025-08-07")
        logger.info(f"  - Макс. токенов: 3000")

        logger.info(f"🔍 Первые 500 символов user_prompt: {user_prompt[:500]}...")

        try:
            response = await client.chat.completions.create(
                model="gpt-5-nano-2025-08-07",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=50000,
            )

            logger.info("✅ Ответ от OpenAI получен")
            logger.info(f"📦 Структура ответа: {type(response)}")
            logger.info(f"🔑 Атрибуты ответа: {dir(response)[:20]}...")

            if not hasattr(response, "choices") or not response.choices:
                logger.warning("⚠️ API не вернул choices")
                return {
                    "success": False,
                    "error": "API вернул пустой ответ (нет choices)"
                }

            reply = response.choices[0].message.content.strip()

            logger.info("=" * 80)
            logger.info("📝 СГЕНЕРИРОВАН ОТВЕТ")
            logger.info(f"📊 Длина ответа: {len(reply)} символов")
            logger.info(f"📄 Ответ: {reply}")

            if not reply:
                logger.warning("⚠️ API не вернул текст")
                return {
                    "success": False,
                    "error": "API вернул пустой текст"
                }

            return {
                "success": True,
                "text": reply
            }

        except Exception as api_error:
            logger.error(f"❌ Ошибка при вызове OpenAI API: {api_error}")
            logger.exception("Детали ошибки API:")
            return {
                "success": False,
                "error": f"Ошибка OpenAI API: {str(api_error)}"
            }

    except Exception as e:
        logger.error(f"❌ Общая ошибка генерации ответа: {e}")
        logger.exception("Детали ошибки:")
        return {
            "success": False,
            "error": f"Ошибка генерации: {str(e)}"
        }

async def build_ozon_characteristics_text(product_attributes: Dict[str, Any]) -> str:
    try:
        characteristics = []

        if product_attributes.get('name'):
            characteristics.append(f"Название: {product_attributes['name']}")

        if product_attributes.get('offer_id'):
            characteristics.append(f"Артикул: {product_attributes['offer_id']}")

        dimensions = []
        if product_attributes.get('weight'):
            dimensions.append(f"вес: {product_attributes['weight']}{product_attributes.get('weight_unit', '')}")
        if product_attributes.get('width'):
            dimensions.append(f"ширина: {product_attributes['width']}{product_attributes.get('dimension_unit', '')}")
        if product_attributes.get('height'):
            dimensions.append(f"высота: {product_attributes['height']}{product_attributes.get('dimension_unit', '')}")
        if product_attributes.get('depth'):
            dimensions.append(f"глубина: {product_attributes['depth']}{product_attributes.get('dimension_unit', '')}")

        if dimensions:
            characteristics.append(f"Габариты: {', '.join(dimensions)}")

        attributes = product_attributes.get('attributes', [])
        important_attributes = []

        for attr in attributes:
            values = attr.get('values', [])
            if values:
                value_text = ", ".join([v.get('value', '') for v in values if v.get('value')])
                if value_text and value_text.lower() not in ['false', 'true', '']:
                    important_attributes.append(value_text)

        if important_attributes:
            characteristics.append(f"Основные характеристики: {', '.join(important_attributes[:10])}")

        if product_attributes.get('description'):
            clean_description = re.sub('<[^<]+?>', '', product_attributes['description'])
            clean_description = re.sub(r'\s+', ' ', clean_description).strip()
            if len(clean_description) > 300:
                clean_description = clean_description[:300] + '...'
            characteristics.append(f"Описание: {clean_description}")

        return ". ".join(characteristics)

    except Exception as e:
        logger.error(f"Ошибка формирования характеристик: {e}")
        return ""

async def generate_question_reply(
        question_text: str,
        sku: str = None,
        link: str = None,
        store_products: list = None,
        client_config: dict = None,
        product_name: str = None,
        supplier_article: str = None,
        store_settings: dict = None
):
    client = await init_ai_client()
    if not client:
        return "Спасибо за ваш вопрос! 😊 Мы постараемся ответить на него как можно скорее."

    try:
        platform = (client_config.get("platform") or "").lower() if client_config else "ozon"

        settings = store_settings or {}
        address_style = settings.get('address_style', 'formal')
        mention_product = settings.get('mention_product', True)
        response_length = settings.get('response_length', 'default')
        use_emojis = settings.get('use_emojis', True)
        tone = settings.get('tone', 'friendly')
        minus_words = settings.get('minus_words', [])

        address_form = get_address_form(address_style)

        logger.info(f"Используемые настройки магазина для вопроса: address_style={address_style} ({address_form}), "
                    f"response_length={response_length}, use_emojis={use_emojis}, tone={tone}")

        if store_products is None and client_config:
            try:
                store_products = await get_store_products(
                    client_config.get("client_id", ""),
                    client_config.get("api_key", ""),
                    client_config.get("platform", "Ozon")
                )
            except Exception as e:
                logger.error(f"Ошибка получения товаров для вопросов: {e}")
                store_products = []

        recommendation_text = ""
        if mention_product and store_products:
            if platform == "ozon":
                short_products = []
                for prod in store_products[:5]:
                    sku_match = re.search(r'\(sku: (\d+)\)', prod)
                    sku_prod = sku_match.group(1) if sku_match else ""
                    brand_match = re.search(r', ([A-Z]+[A-Za-z]*),', prod)
                    brand = brand_match.group(1) if brand_match else "Неизвестно"
                    name_parts = re.split(r', | \(', prod)[0].strip()
                    short_name = f"{name_parts} ({brand}, sku: {sku_prod})" if sku_prod and brand != "Неизвестно" else name_parts
                    short_products.append(short_name)
                products_list = "; ".join(short_products)
                recommendation_text = (
                    f"Сопутствующие товары: {products_list}. "
                    f"Если уместно — можешь ненавязчиво упомянуть один из них, "
                    f"но НЕ пиши 'выбран товар' и НЕ цитируй название полностью."
                )
            elif platform == "wildberries":
                short_products = []
                for prod in store_products[:5]:
                    nm_match = re.search(r'\(nmID: (\d+)\)', prod)
                    nm_id = nm_match.group(1) if nm_match else ""
                    name_match = re.search(r'^([^(]+)', prod)
                    product_name_wb = name_match.group(1).strip() if name_match else prod
                    short_name = f"{product_name_wb} (Артикул: {nm_id})" if nm_id else product_name_wb
                    short_products.append(short_name)

                products_list = "; ".join(short_products)
                recommendation_text = (
                    f"Сопутствующие товары: {products_list}. "
                    f"Если уместно — порекомендуй товар из списка, "
                    f"но НЕ пиши 'выбран товар' и НЕ цитируй название полностью."
                )
        else:
            recommendation_text = "Не упоминай другие товары."

        minus_words_instruction = build_minus_words_instruction(minus_words)

        if platform == "ozon":
            product_info_text = ""

            if sku and sku != "N/A":
                try:
                    from utils.api_utils import get_product_info

                    product_info = await get_product_info(
                        client_config.get("client_id", ""),
                        client_config.get("api_key", ""),
                        sku
                    )

                    if product_info and product_info.get("attributes"):
                        attributes = product_info["attributes"]
                        description_data = product_info.get("description", {})

                        product_info_parts = []

                        product_info_parts.append(f"📦 Основная информация:")
                        product_info_parts.append(f"   Название: {attributes.get('name', 'Не указано')}")
                        product_info_parts.append(f"   Артикул: {attributes.get('offer_id', 'Не указан')}")
                        product_info_parts.append(f"   SKU: {attributes.get('sku', 'Не указан')}")
                        product_info_parts.append(f"   ID: {attributes.get('id', 'Не указан')}")

                        if attributes.get('weight'):
                            product_info_parts.append(
                                f"   Вес: {attributes.get('weight')} {attributes.get('weight_unit', 'г')}")
                        if attributes.get('width') and attributes.get('height') and attributes.get('depth'):
                            product_info_parts.append(
                                f"   Габариты: {attributes.get('width')}×{attributes.get('height')}×{attributes.get('depth')} {attributes.get('dimension_unit', 'мм')}")

                        if attributes.get('barcodes'):
                            product_info_parts.append(f"   Штрихкоды: {', '.join(attributes.get('barcodes', []))}")

                        if attributes.get('attributes'):
                            product_info_parts.append(f"🔧 Характеристики:")
                            for attr in attributes.get('attributes', [])[:15]:
                                attr_id = attr.get('id', '')
                                values = attr.get('values', [])
                                if values:
                                    value_text = ", ".join([str(v.get('value', '')) for v in values if v.get('value')])
                                    if value_text and value_text not in ['false', 'true']:
                                        product_info_parts.append(f"   - {attr_id}: {value_text}")

                        if description_data and description_data.get('description'):
                            clean_description = re.sub('<[^<]+?>', '', description_data.get('description', ''))
                            clean_description = re.sub(r'\s+', ' ', clean_description).strip()
                            product_info_parts.append(f"📄 Описание: {clean_description[:400]}...")

                        product_info_text = "\n".join(product_info_parts)
                        logging.info(f"Получена информация о товаре Ozon SKU {sku}: {len(product_info_text)} символов")

                except Exception as e:
                    logger.error(f"Ошибка при получении информации о товаре Ozon: {e}")
                    product_info_text = "Не удалось загрузить информацию о товаре"

            length_descriptions = {
                'short': 'очень короткий (до 30 слов)',
                'default': 'короткий (до 70 слов)',
                'long': 'подробный (до 150 слов)'
            }
            length_desc = length_descriptions.get(response_length, 'короткий (до 70 слов)')

            system_prompt = (
                f"Ты — {tone} помощник продавца Ozon {'😊' if use_emojis else ''} "
                f"Пиши естественно, {length_desc}, без длинных названий. "
                f"Используй обращение на '{address_form}'. "
                f"Используй информацию о товаре для точного ответа. "
                f"Если вопрос о характеристиках — дай точную информацию из данных товара. "
                f"Если нужно уточнить размеры или другие параметры — попроси."
                f"{minus_words_instruction}"
            )

            user_prompt = (
                f"❓ Вопрос клиента: {question_text or 'Без текста'}\n"
                f"📦 Информация о товаре:\n{product_info_text}\n"
                f"🔗 Ссылка: {link or 'Не указана'}\n"
                f"{recommendation_text}\n\n"
                "Используй информацию о товаре для точного ответа. "
                "Если в данных товара есть ответ на вопрос — используй его. "
                "Отвечай мягко и аккуратно."
            )

        else:
            length_descriptions = {
                'short': 'очень короткий (до 30 слов)',
                'default': 'короткий (до 70 слов)',
                'long': 'подробный (до 150 слов)'
            }
            length_desc = length_descriptions.get(response_length, 'короткий (до 70 слов)')

            if platform == "wildberries":
                system_prompt = (
                    f"Ты — профессиональный помощник продавца Wildberries. "
                    f"Пиши {length_desc}, {tone}, {'с лёгкими эмайликами 😊' if use_emojis else 'БЕЗ эмайликов'}. "
                    f"Используй обращение на '{address_form}'. "
                    f"Упоминай название товара и nmID. "
                    f"Если нужны уточнения, спроси. "
                    f"Пиши по-человечески, не канцелярит."
                    f"{minus_words_instruction}"
                )

                user_prompt = (
                    f"❓ Вопрос клиента: {question_text or 'Без текста'}\n"
                    f"📦 Название товара: {product_name or 'Не указано'}\n"
                    f"🔢 Артикул (nmID): {sku or 'Не указан'}\n"
                    f"🏷️ Supplier Article: {supplier_article or 'Не указан'}\n"
                    f"🔗 Ссылка: {link or 'Не указана'}\n"
                    f"🛍️ {recommendation_text}\n\n"
                    "Дай чёткий и полезный ответ."
                )
            else:
                system_prompt = (
                    f"Ты — профессиональный помощник продавца. "
                    f"Пиши {length_desc}, {tone}, {'с лёгкими эмайликами 😊' if use_emojis else 'БЕЗ эмайликов'}. "
                    f"Используй обращение на '{address_form}'. "
                    f"Если нужны уточнения, спроси. "
                    f"Пиши по-человечески, не канцелярит."
                    f"{minus_words_instruction}"
                )

                user_prompt = (
                    f"❓ Вопрос клиента: {question_text or 'Без текста'}\n"
                    f"📦 Название товара: {product_name or 'Не указано'}\n"
                    f"🔢 Артикул: {sku or 'Не указан'}\n"
                    f"🔗 Ссылка: {link or 'Не указана'}\n"
                    f"🛍️ {recommendation_text}\n\n"
                    "Дай чёткий и полезный ответ."
                )

        logger.info(f"[{platform.upper()}] Промпт пользователя: {user_prompt[:300]}...")

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=3000,
        )

        if not hasattr(response, "choices") or not response.choices:
            logger.warning("API не вернул choices")
            return create_fallback_reply(platform, sku, link, product_name, store_settings)

        reply = response.choices[0].message.content.strip()
        if not reply:
            logger.warning("API не вернул текст")
            return create_fallback_reply(platform, sku, link, product_name, store_settings)

        return reply

    except Exception as e:
        logger.error(f"Ошибка генерации ответа на вопрос: {e}")
        return create_fallback_reply(platform, sku, link, product_name, store_settings)

def create_fallback_reply(
        platform: str,
        sku: str,
        link: str,
        product_name: str,
        store_settings: dict = None
) -> str:
    settings = store_settings or {}
    use_emojis = settings.get('use_emojis', True)
    emoji = "😊" if use_emojis else ""

    reply = f"Спасибо за ваш вопрос! {emoji} "

    if platform == "wildberries":
        if product_name:
            reply += f"По поводу '{product_name}' "
        if sku and sku != "N/A":
            reply += f"(Артикул: {sku}) "
    else:  # Ozon
        if product_name:
            reply += f"По поводу '{product_name}' "
        if sku and sku != "N/A":
            reply += f"(SKU: {sku}) "

    reply += "мы уточним детали и свяжемся с вами! 😊" if use_emojis else "мы уточним детали и свяжемся с вами!"

    if link and link != "N/A":
        reply += f" Подробности: {link}"

    return reply

def extract_text(response):
    logger.info(f"API response: {response}")
    try:
        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content.strip()
        else:
            logger.warning("No choices in API response")
            return None
    except Exception as e:
        logger.error(f"Error extracting text from response: {str(e)}")
        return None