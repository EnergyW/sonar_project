import time
import logging
import asyncio
import json
from db.database import AsyncDatabase, init_db, close_db
from utils.api_utils import get_reviews, post_review_answer, get_questions, post_question_answer, get_store_products
from utils.ai_utils import generate_reply, generate_question_reply

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


async def process_single_store(store_data):
    user, store = store_data
    store_id = store['store_id']
    store_name = store['store_name']
    store_type = store['type']
    client_id = store.get('client_id', '')
    api_key = store.get('api_key', '')

    logging.info(f"🔍 [STORE_START] Начало обработки магазина: {store_name} (ID: {store_id}, Тип: {store_type})")
    logging.debug(f"📋 [STORE_DATA] User ID: {user.get('account_id')}, Client ID: {client_id[:10]}... (обрезано)")

    async with AsyncDatabase() as db:
        logging.debug(f"🗄️ [DB] Запрос деталей магазина {store_id}...")
        store_details = await db.get_store_details(store_id)

        if not store_details:
            logging.error(f"❌ [DB_ERROR] Не удалось получить детали магазина {store_name} (store_id={store_id})")
            return

        logging.debug(
            f"✅ [DB_SUCCESS] Детали магазина получены: {json.dumps(store_details, ensure_ascii=False, default=str)[:200]}...")

        settings = {
            'reviews_enabled': store_details.get('reviews_enabled', False),
            'modes': store_details.get('modes', {str(i): 'manual' for i in range(1, 6)}),
            'templates': store_details.get('templates', {}),
            'questions_enabled': store_details.get('questions_enabled', False),
            'questions_mode': store_details.get('questions_mode', 'manual')
        }

        logging.info(f"⚙️ [SETTINGS] Настройки магазина {store_name}:")
        logging.info(f"   - Отзывы включены: {settings['reviews_enabled']}")
        logging.info(f"   - Режимы по рейтингам: {settings['modes']}")
        logging.info(f"   - Вопросы включены: {settings['questions_enabled']}, Режим: {settings['questions_mode']}")

        if not settings.get('reviews_enabled', False):
            logging.info(f"➖ [SKIP] Отзывы для магазина {store_name} отключены, пропускаем")
            return

        if not api_key.strip():
            logging.warning(f"⚠️ [API_KEY_MISSING] Отсутствует API-ключ для магазина {store_name}")
            return

        logging.info(f"🪐 [PROCESSING] Обработка магазина: {store_name} ({store_type})")

        logging.debug(f"🗄️ [DB] Запрос настроек ИИ для магазина {store_id}...")
        store_settings = await db.get_store_settings(store_id)
        logging.debug(
            f"✅ [DB_SUCCESS] Настройки ИИ получены: {json.dumps(store_settings, ensure_ascii=False, default=str)[:300]}...")

        sku_to_name = {}
        try:
            logging.debug(f"📦 [PRODUCTS] Запрос списка товаров для {store_name}...")
            products_list = await get_store_products(
                client_id=client_id,
                api_key=api_key,
                platform=store_type,
                include_archived=True
            )

            for product in products_list:
                if "(sku:" in product:
                    try:
                        name_part, sku_part = product.split("(sku:")
                        sku = sku_part.strip(" )")
                        sku_to_name[sku] = name_part.strip()
                    except Exception:
                        continue

            logging.info(f"✅ [PRODUCTS] Получено {len(sku_to_name)} товаров для сопоставления SKU")
            if sku_to_name:
                sample_items = list(sku_to_name.items())[:3]
                logging.debug(f"📋 [PRODUCTS_SAMPLE] Примеры товаров: {sample_items}")
        except Exception as e:
            logging.warning(f"⚠️ [PRODUCTS_ERROR] Не удалось загрузить список товаров: {e}")

        # ===== ОБРАБОТКА ОТЗЫВОВ =====
        try:
            logging.info(f"📝 [REVIEWS_START] Запрос необработанных отзывов для {store_name}...")

            reviews = await get_reviews(
                client_id=client_id if store_type == "Ozon" else "",
                api_key=api_key,
                platform=store_type,
                status="UNPROCESSED",
                limit=50,
                last_id=0
            )

            logging.info(
                f"🧪 [RAW_REVIEWS] type={type(reviews)}, value={str(reviews)[:500]}"
            )
            logging.info(f"📊 [REVIEWS_COUNT] Получено отзывов: {len(reviews)} для магазина {store_name}")

            if not reviews:
                logging.info(f"✅ [REVIEWS_EMPTY] Нет необработанных отзывов для {store_name}")

            processed_reviews = []
            for review in reviews:
                if store_type.lower() == "ozon":
                    sku = str(review.get("sku", review.get("product", {}).get("sku", "")))
                elif store_type.lower() == "wildberries":
                    sku = str(review.get("nmId", ""))
                else:
                    sku = "N/A"

                if not sku:
                    sku = "N/A"

                if store_type.lower() == "wildberries":
                    product_name = review.get("product_name", "Неизвестный товар")
                else:
                    product_name = sku_to_name.get(sku, "Неизвестный товар")

                review["product_name"] = product_name
                review["sku"] = sku
                processed_reviews.append(review)

            logging.info(f"✅ [REVIEWS_PROCESSED] Обработано {len(processed_reviews)} отзывов с названиями товаров")

            for idx, review in enumerate(processed_reviews, 1):
                review_id = review.get("id", "UNKNOWN")
                rating = review.get("rating", 0)
                text = review.get("text", "").strip()
                product_name = review.get("product_name", "Неизвестный товар")
                sku = review.get("sku", "N/A")

                logging.info(f"📄 [REVIEW_{idx}/{len(processed_reviews)}] ID: {review_id}, Рейтинг: {rating}⭐️")
                logging.info(f"📦 [PRODUCT] '{product_name}' (SKU: {sku})")
                logging.debug(f"💬 [REVIEW_TEXT] {text[:100]}{'...' if len(text) > 100 else ''}")

                mode = settings.get("modes", {}).get(str(rating), "manual")
                logging.info(f"🎯 [MODE] Режим для рейтинга {rating}: {mode}")

                if mode == "auto":
                    if not text:
                        logging.warning(f"⚠️ [SKIP] Отзыв {review_id} пропущен - пустой текст")
                        continue

                    try:
                        logging.info(f"🤖 [AI_START] Генерация ИИ-ответа для отзыва {review_id}...")

                        generate_reply_kwargs = {
                            "review_text": text,
                            "rating": rating,
                            "client_config": {
                                "client_id": client_id,
                                "api_key": api_key,
                                "platform": store_type
                            },
                            "store_settings": store_settings
                        }

                        if store_type.lower() == "wildberries":
                            base_product_name = review.get("product_name", "Товар")
                            supplier_article = review.get("supplierArticle", "")

                            if supplier_article and supplier_article != "N/A":
                                product_name = f"{base_product_name} ({supplier_article})"
                            else:
                                product_name = base_product_name

                            sku = review.get("nmId", "")

                            wb_params = {
                                "product_name": product_name,
                                "supplier_article": supplier_article,
                                "sku": sku,
                                "pros": review.get("pros", ""),
                                "cons": review.get("cons", "")
                            }
                            generate_reply_kwargs.update(wb_params)
                            logging.debug(
                                f"📦 [WB_PARAMS] Product: '{product_name}', SKU: {sku}, Article: {supplier_article}")

                        elif store_type.lower() == "ozon":
                            base_product_name = review.get("product_name", "Товар")
                            sku = review.get("sku", "")
                            offer_id = review.get("offer_id", "")
                            product_id = review.get("product_id", "")
                            product_name = base_product_name

                            ozon_params = {
                                "product_name": product_name,
                                "sku": sku,
                                "offer_id": offer_id,
                                "product_id": product_id
                            }
                            generate_reply_kwargs.update(ozon_params)
                            logging.debug(f"📦 [OZON_PARAMS] Product: '{product_name}', SKU: {sku}, Offer: {offer_id}")

                        logging.debug(
                            f"🔧 [AI_INPUT] Параметры для ИИ: {json.dumps({k: v for k, v in generate_reply_kwargs.items() if k != 'client_config'}, ensure_ascii=False, default=str)[:500]}...")

                        reply = await generate_reply(**generate_reply_kwargs)

                        logging.info(f"✅ [AI_SUCCESS] ИИ-ответ сгенерирован для отзыва {review_id}")
                        logging.debug(
                            f"💡 [AI_OUTPUT] Сгенерированный ответ ({len(reply)} символов): {reply[:200]}{'...' if len(reply) > 200 else ''}")

                        logging.info(f"📤 [API_SEND] Отправка ответа на отзыв {review_id}...")
                        success = await post_review_answer(
                            client_id=client_id,
                            api_key=api_key,
                            review_id=review_id,
                            answer_text=reply,
                            platform=store_type
                        )

                        if success:
                            logging.info(f"✅ [SUCCESS] Автоответ отправлен на отзыв {review_id} (рейтинг: {rating}⭐️)")
                        else:
                            logging.error(f"❌ [API_ERROR] Ошибка отправки ответа на отзыв {review_id}")

                    except Exception as e:
                        logging.error(
                            f"❌ [EXCEPTION] Ошибка генерации ответа для отзыва {review_id}: {type(e).__name__}: {str(e)}")
                        logging.debug(f"🔍 [TRACEBACK]", exc_info=True)

                elif mode == "template":
                    logging.info(f"📋 [TEMPLATE_MODE] Используем шаблон для рейтинга {rating}")

                    templates = settings.get("templates", {})
                    template = templates.get(str(rating))

                    if template:
                        logging.debug(
                            f"📝 [TEMPLATE_TEXT] Шаблон ({len(template)} символов): {template[:200]}{'...' if len(template) > 200 else ''}")
                        logging.info(f"📤 [API_SEND] Отправка шаблонного ответа на отзыв {review_id}...")

                        success = await post_review_answer(
                            client_id=client_id,
                            api_key=api_key,
                            review_id=review_id,
                            answer_text=template,
                            platform=store_type
                        )

                        if success:
                            logging.info(
                                f"✅ [SUCCESS] Ответ по шаблону отправлен на отзыв {review_id} (рейтинг: {rating}⭐️)")
                        else:
                            logging.error(f"❌ [API_ERROR] Ошибка отправки шаблонного ответа на отзыв {review_id}")
                    else:
                        logging.warning(
                            f"⚠️ [TEMPLATE_MISSING] Для отзыва {review_id} с рейтингом {rating} не найден шаблон")

                elif mode in ["semi", "manual"]:
                    logging.debug(f"➡️ [SKIP] Пропускаем отзыв {review_id} (режим: {mode})")
                    continue

            logging.info(f"✅ [REVIEWS_END] Обработка отзывов завершена для {store_name}")

        except Exception as e:
            logging.error(
                f"❌ [REVIEWS_EXCEPTION] Ошибка обработки отзывов для магазина {store_name}: {type(e).__name__}: {str(e)}")
            logging.debug(f"🔍 [TRACEBACK]", exc_info=True)

        # ===== ОБРАБОТКА ВОПРОСОВ =====
        try:
            if settings.get("questions_enabled", False) and settings.get("questions_mode", "manual") == "auto":
                logging.info(f"❓ [QUESTIONS_START] Запрос необработанных вопросов для {store_name}...")

                if store_type == "Wildberries":
                    questions_response = await get_questions(
                        client_id=client_id,
                        api_key=api_key,
                        platform=store_type,
                        status="UNPROCESSED",
                        limit=30
                    )
                else:
                    questions_response = await get_questions(
                        client_id=client_id,
                        api_key=api_key,
                        platform=store_type,
                        status="UNANSWERED",
                        limit=30
                    )

                questions = questions_response.get("questions", [])
                logging.info(f"📊 [QUESTIONS_COUNT] Получено вопросов: {len(questions)} для магазина {store_name}")

                if not questions:
                    logging.info(f"✅ [QUESTIONS_EMPTY] Нет необработанных вопросов для {store_name}")

                for idx, question in enumerate(questions, 1):
                    question_id = question.get("id", "UNKNOWN")
                    text = question.get("text", "").strip()

                    logging.info(f"❓ [QUESTION_{idx}/{len(questions)}] ID: {question_id}")
                    logging.debug(f"💬 [QUESTION_TEXT] {text[:100]}{'...' if len(text) > 100 else ''}")

                    if not text:
                        logging.warning(f"⚠️ [SKIP] Вопрос {question_id} пропущен - пустой текст")
                        continue

                    try:
                        logging.info(f"🤖 [AI_START] Генерация ИИ-ответа для вопроса {question_id}...")
                        logging.debug(f"🔧 [AI_INPUT] Текст вопроса: {text}")

                        reply = generate_question_reply(text)

                        logging.info(f"✅ [AI_SUCCESS] ИИ-ответ сгенерирован для вопроса {question_id}")
                        logging.debug(
                            f"💡 [AI_OUTPUT] Сгенерированный ответ ({len(reply)} символов): {reply[:200]}{'...' if len(reply) > 200 else ''}")

                        logging.info(f"📤 [API_SEND] Отправка ответа на вопрос {question_id}...")
                        success = await post_question_answer(
                            client_id=client_id,
                            api_key=api_key,
                            question=question,
                            answer_text=reply,
                            platform=store_type
                        )

                        if success:
                            logging.info(f"✅ [SUCCESS] Автоответ отправлен на вопрос {question_id}")
                        else:
                            logging.error(f"❌ [API_ERROR] Ошибка отправки ответа на вопрос {question_id}")

                    except Exception as e:
                        logging.error(
                            f"❌ [EXCEPTION] Ошибка обработки вопроса {question_id}: {type(e).__name__}: {str(e)}")
                        logging.debug(f"🔍 [TRACEBACK]", exc_info=True)

                logging.info(f"✅ [QUESTIONS_END] Обработка вопросов завершена для {store_name}")
            else:
                logging.debug(f"➖ [QUESTIONS_SKIP] Вопросы отключены или не в авто-режиме для {store_name}")

        except Exception as e:
            logging.error(
                f"❌ [QUESTIONS_EXCEPTION] Ошибка обработки вопросов для магазина {store_name}: {type(e).__name__}: {str(e)}")
            logging.debug(f"🔍 [TRACEBACK]", exc_info=True)

    logging.info(f"✅ [STORE_END] Обработка магазина {store_name} завершена\n" + "=" * 80)


async def process_all_stores():
    logging.info("=" * 80)
    logging.info(f"🌍 [CYCLE_START] Начало нового цикла обработки магазинов")
    logging.info("=" * 80)

    async with AsyncDatabase() as db:
        logging.debug(f"🗄️ [DB] Запрос всех пользователей с магазинами...")
        users = await db.get_all_users_with_stores()
        logging.info(f"👥 [USERS_COUNT] Получено пользователей: {len(users)}")

        stores_to_process = []
        for user_idx, user in enumerate(users, 1):
            user_id = user.get('account_id', 'UNKNOWN')
            logging.debug(f"👤 [USER_{user_idx}/{len(users)}] ID: {user_id}, Магазинов: {len(user.get('stores', []))}")

            for store in user['stores']:
                store_name = store.get('store_name', 'UNKNOWN')
                # Проверяем reviews_enabled вместо enabled
                reviews_enabled = store.get('reviews_enabled', False)
                questions_enabled = store.get('questions_enabled', False)

                # Магазин активен, если включены отзывы ИЛИ вопросы
                if reviews_enabled or questions_enabled:
                    stores_to_process.append((user, store))
                    logging.debug(
                        f"   ✅ [STORE_ENABLED] {store_name} добавлен в очередь (отзывы: {reviews_enabled}, вопросы: {questions_enabled})")
                else:
                    logging.debug(f"   ➖ [STORE_DISABLED] {store_name} отключен, пропускаем")

        if not stores_to_process:
            logging.info("🔭 [NO_STORES] Нет активных магазинов для обработки")
            logging.info("=" * 80)
            return

        logging.info(
            f"🔄 [PROCESSING_START] Начинаем обработку {len(stores_to_process)} магазинов в асинхронном режиме (макс. 3 одновременно)")
        logging.info("=" * 80 + "\n")

        semaphore = asyncio.Semaphore(3)

        async def process_with_semaphore(store_data):
            async with semaphore:
                await process_single_store(store_data)

        tasks = [process_with_semaphore(store_data) for store_data in stores_to_process]

        completed = 0
        failed = 0
        for task in asyncio.as_completed(tasks):
            try:
                await task
                completed += 1
                logging.debug(f"📈 [PROGRESS] Обработано магазинов: {completed}/{len(stores_to_process)}")
            except Exception as exc:
                failed += 1
                logging.error(f'❌ [TASK_EXCEPTION] Ошибка при обработке магазина: {type(exc).__name__}: {str(exc)}')
                logging.debug(f"🔍 [TRACEBACK]", exc_info=True)

        logging.info("\n" + "=" * 80)
        logging.info(f"✅ [CYCLE_END] Завершена обработка {completed}/{len(stores_to_process)} магазинов")
        if failed > 0:
            logging.warning(f"⚠️ [FAILED] Неудачных обработок: {failed}")
        logging.info("=" * 80 + "\n")


async def main_loop():
    logging.info("\n" + "🚀" * 40)
    logging.info("🚀 [SYSTEM_START] Запуск асинхронного цикла обработки...")
    logging.info("🚀" * 40 + "\n")

    logging.info("🗄️ [DB_INIT] Инициализация базы данных...")
    await init_db()
    logging.info("✅ [DB_READY] База данных готова к работе\n")

    cycle_number = 0

    try:
        while True:
            cycle_number += 1
            logging.info(f"🔄 [CYCLE #{cycle_number}] Начало цикла обработки")

            start_time = time.time()
            await process_all_stores()
            end_time = time.time()

            duration = end_time - start_time
            sleep_time = max(30 - duration, 5)

            logging.info(f"⏱️ [TIMING] Цикл #{cycle_number} выполнен за {duration:.2f} сек")
            logging.info(f"💤 [SLEEP] Следующая проверка через {sleep_time:.1f} сек...\n")

            await asyncio.sleep(sleep_time)

    except KeyboardInterrupt:
        logging.info("\n" + "⛔" * 40)
        logging.info("⛔ [SYSTEM_STOP] Остановлено пользователем (KeyboardInterrupt)")
        logging.info("⛔" * 40)
    except Exception as e:
        logging.error("\n" + "💥" * 40)
        logging.error(f"💥 [CRITICAL_ERROR] Критическая ошибка: {type(e).__name__}: {str(e)}")
        logging.error("💥" * 40)
        logging.debug(f"🔍 [TRACEBACK]", exc_info=True)
        logging.info("🔄 [RESTART] Перезапуск через 60 секунд...")
        await asyncio.sleep(60)
        await main_loop()
    finally:
        logging.info("\n🔒 [DB_CLOSE] Закрытие базы данных...")
        await close_db()
        logging.info("✅ [DB_CLOSED] База данных закрыта.")
        logging.info("👋 [SYSTEM_END] Завершение работы системы\n")


if __name__ == "__main__":
    asyncio.run(main_loop())