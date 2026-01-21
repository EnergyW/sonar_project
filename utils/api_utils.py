import json
import logging
from datetime import datetime, timezone, timedelta
import time
from typing import List, Dict, Any, Optional
import aiohttp
from db.database import AsyncDatabase

logger.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PLATFORM_CONFIG = {
    "Ozon": {
        "review_url": "https://api-seller.ozon.ru/v1/review/list",
        "review_method": "POST",
        "review_headers": lambda client_id, api_key: {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json"
        },
        "review_body": lambda status, limit, last_id, date_to: {
            "last_id": last_id,
            "limit": limit,
            "sort_dir": "ASC",
            "status": status
        },
        "review_response_parser": lambda data: [
           {
               "id": review["id"],
               "text": review.get("text", ""),
               "rating": review.get("rating", 0),
               "created_at": review.get("published_at", ""),
               "sku": review.get("sku", 0)
           }
           for review in data.get("reviews", [])
       ][::-1],
        "answer_url": "https://api-seller.ozon.ru/v1/review/comment/create",
        "answer_method": "POST",
        "answer_body": lambda review_id, answer_text: {
            "review_id": review_id,
            "text": answer_text,
            "mark_review_as_processed": True
        },
        "question_url": "https://api-seller.ozon.ru/v1/question/list",
        "question_method": "POST",
        "question_body": lambda status, limit, last_id: {
            "filter": {
                "status": status
            },
            "last_id": last_id,
            "limit": limit,
        },
         "question_response_parser": lambda data: [
        {
            "id": q["id"],
            "text": q.get("text", ""),
            "sku": q.get("sku", 0),
            "created_at": q.get("published_at", ""),
            "answer": q.get("answer", {}).get("text", "") if q.get("answer") else "",
            "question_link": q.get("question_link", ""),
            "product_url": q.get("product_url", ""),
            "status": q.get("status", ""),
            "answers_count": q.get("answers_count", 0),
            "author_name": q.get("author_name", "")
        }
        for q in data.get("questions", [])
    ] if data.get("questions") else [],
        "question_answer_url": "https://api-seller.ozon.ru/v1/question/answer/create",
        "question_answer_method": "POST",
        "question_answer_body": lambda question_id, sku, answer_text: {
            "question_id": question_id,
            "sku": sku,
            "text": answer_text[:3000]
        },
        "requires_client_id": True,
        "rate_limit": False,
        "supports_auto_reply": True,
        "supports_monitoring": True
    },
    "Wildberries": {
        "review_url": "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
        "review_method": "GET",
        "review_headers": lambda client_id, api_key: {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        },
        "review_params": lambda status, limit, offset, nmId=None: {
            "isAnswered": "true" if status == "PROCESSED" else "false",
            "take": limit,
            "skip": int(offset) if offset and str(offset).isdigit() else 0,
            "order": "dateDesc",
            **({"nmId": nmId} if nmId else {})
        },
        "review_response_parser": lambda data: [
                (lambda review: {
                    "id": review.get("id"),
                    "text": review.get("text", ""),
                    "rating": review.get("productValuation", 0),
                    "created_at": (lambda date_value: (
                        datetime.fromtimestamp(int(date_value) / 1000).strftime("%Y-%m-%d %H:%M:%S")
                        if str(date_value).isdigit()
                        else (
                            datetime.strptime(date_value.replace("ZZ", "Z"), "%Y-%m-%dT%H:%M:%SZ").strftime(
                                "%Y-%m-%d %H:%M:%S")
                            if isinstance(date_value, str) and "T" in date_value and "ZZ" in date_value
                            else (
                                datetime.strptime(date_value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")
                                if isinstance(date_value, str) and "T" in date_value
                                else (
                                    datetime.strptime(date_value[:26] + 'Z', "%Y-%m-%dT%H:%M:%S.%fZ").strftime(
                                        "%Y-%m-%d %H:%M:%S")
                                    if isinstance(date_value, str) and "." in date_value
                                    else ""
                                )
                            )
                        )
                    ))(review.get("createdDate", "")),
                    "pros": review.get("pros", ""),
                    "cons": review.get("cons", ""),
                    "product_name": review.get("productDetails", {}).get("productName", "Неизвестный товар"),
                    "nmId": str(review.get("productDetails", {}).get("nmId", "N/A")),
                    "sku": str(review.get("productDetails", {}).get("nmId", "N/A")),
                    "supplierArticle": review.get("productDetails", {}).get("supplierArticle", "N/A"),
                    "answer": review.get("answer", {}).get("text", "") if review.get("answer") else "",
                    "userName": review.get("userName", "")
                })(review)
                for review in data.get("data", {}).get("feedbacks", [])
            ],
        "answer_url": "https://feedbacks-api.wildberries.ru/api/v1/feedbacks/answer",
        "answer_method": "POST",
        "answer_body": lambda review_id, answer_text: {
            "id": review_id,
            "text": answer_text
        },
        "question_url": "https://feedbacks-api.wildberries.ru/api/v1/questions",
        "question_method": "GET",
        "question_headers": lambda client_id, api_key: {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        },
        "question_params": lambda status, limit, last_id, nmId=None, date_from=None, date_to=None: {
            "isAnswered": "true" if status == "PROCESSED" else "false",
            "take": min(limit, 10000),
            "skip": int(last_id) if last_id and str(last_id).isdigit() else 0,
            "order": "dateDesc",
            **({"nmId": nmId} if nmId else {}),
            **({"dateFrom": int(date_from.timestamp())} if date_from else {}),
            **({"dateTo": int(date_to.timestamp())} if date_to else {})
        },
        "question_response_parser": lambda data: [
            {
                "id": q["id"],
                "text": q.get("text", ""),
                "created_at": (lambda date_value: (
                    datetime.strptime(date_value[:26] + 'Z', "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(date_value, str) and "." in date_value
                    else (
                        datetime.strptime(date_value.replace("ZZ", "Z"), "%Y-%m-%dT%H:%M:%SZ").strftime(
                            "%Y-%m-%d %H:%M:%S")
                        if isinstance(date_value, str) and "ZZ" in date_value
                        else (
                            datetime.strptime(date_value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H:%M:%S")
                            if isinstance(date_value, str) and "T" in date_value
                            else ""
                        )
                    )
                ))(q.get("createdDate", "")),
                "answer": q.get("answer", {}).get("text", "") if q.get("answer") else "",
                "sku": str(q.get("productDetails", {}).get("nmId", "N/A")),
                "product_name": q.get("productDetails", {}).get("productName", "Неизвестный товар"),
                "supplierArticle": q.get("productDetails", {}).get("supplierArticle", "N/A"),
                "state": q.get("state", ""),
                "wasViewed": q.get("wasViewed", False),
                "isWarned": q.get("isWarned", False)
            }
            for q in data.get("data", {}).get("questions", [])
        ],
        "question_answer_url": "https://feedbacks-api.wildberries.ru/api/v1/questions/answer",
        "question_answer_method": "POST",
        "question_answer_body": lambda question_id, answer_text: {
            "id": question_id,
            "text": answer_text
        },
        "requires_client_id": False,
        "rate_limit": True,
        "supports_auto_reply": True,
        "supports_monitoring": True
    },
}

async def get_reviews(
        client_id: str,
        api_key: str,
        platform: str = "Ozon",
        status: str = "UNPROCESSED",
        limit: int = 20,
        last_id: str = "",
        date_to: str = None,
        secret_key: str = None,
        timestamp: int = int(time.time()),
        nmId: int = None
) -> List[Dict[str, Any]]:
    if platform not in PLATFORM_CONFIG:
        logger.error(f"Неподдерживаемая платформа: {platform}")
        return []

    config = PLATFORM_CONFIG[platform]
    headers = config["review_headers"](client_id, api_key)
    url = config["review_url"]

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if platform == "Wildberries":
                params = config["review_params"](status, limit, last_id, nmId)
                logger.info(f"[WB] GET {url} params={params}")
                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
            else:
                body = config["review_body"](status, limit, last_id, date_to)
                logger.info(f"[Ozon] POST {url} body={body}")
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    data = await response.json()

        logger.debug(f"Response from {platform}: {json.dumps(data, ensure_ascii=False)}")

        if platform == "Ozon":
            logger.info(f"Ozon: {len(data.get('reviews', []))} отзывов")
        elif platform == "Wildberries":
            fb = data.get("data", {}).get("feedbacks", [])
            logger.info(f"WB: {len(fb)} отзывов (countUnanswered={data.get('data', {}).get('countUnanswered', '?')})")

        reviews = config["review_response_parser"](data)
        return reviews

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка запроса {platform}: {e}")
    except json.JSONDecodeError:
        logger.error(f"Ошибка JSON при разборе ответа {platform}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении отзывов {platform}: {e}")

    return []

async def get_store_reviews(
        store_details,
        answered: bool = False,
        limit: int = 100,
        last_id: str = "",
        nmId: int = None):
    try:
        platform = store_details.get("type")
        api_key = store_details.get("api_key")
        client_id = store_details.get("client_id", "")

        if not platform or not api_key:
            logger.error("Некорректные данные магазина: отсутствует type или api_key")
            return []

        status_map = {
            "Ozon": {
                True: "PROCESSED",
                False: "UNPROCESSED"
            },
            "Wildberries": {
                True: "PROCESSED",
                False: "UNPROCESSED"
            }
        }

        status = status_map.get(platform, {}).get(answered)
        if not status:
            logger.error(f"Неверная платформа или статус: platform={platform}, answered={answered}")
            return []

        logger.info(f"🔍 Получение отзывов: {platform}, answered={answered}, limit={limit}, last_id={last_id}")

        clean_params = {
            "client_id": str(client_id) if client_id else "",
            "api_key": str(api_key),
            "platform": str(platform),
            "limit": int(limit) if limit else 100
        }

        if platform.lower() == "ozon":
            since = datetime.now(timezone.utc) - timedelta(days=180)
            clean_params.update({
                "since": since,
                "last_id": str(last_id) if last_id else "",
                "status": str(status)
            })
            reviews = await get_reviews_since(**clean_params)

        elif platform.lower() == "wildberries":

            all_reviews = []

            clean_params_unanswered = {
                "client_id": str(client_id) if client_id else "",
                "api_key": str(api_key),
                "platform": str(platform),
                "limit": int(limit) if limit else 100,
                "status": "UNPROCESSED",
                "last_id": str(last_id) if last_id else "",
            }
            if nmId is not None:
                clean_params_unanswered["nmId"] = int(nmId)

            unanswered_reviews = await get_reviews(**clean_params_unanswered)
            logger.info(f"📥 WB вернул {len(unanswered_reviews)} отзывов с isAnswered=false")
            all_reviews.extend(unanswered_reviews)

            clean_params_answered = {
                "client_id": str(client_id) if client_id else "",
                "api_key": str(api_key),
                "platform": str(platform),
                "limit": int(limit) if limit else 100,
                "status": "PROCESSED",
                "last_id": str(last_id) if last_id else "",
            }
            if nmId is not None:
                clean_params_answered["nmId"] = int(nmId)

            answered_reviews = await get_reviews(**clean_params_answered)
            logger.info(f"📥 WB вернул {len(answered_reviews)} отзывов с isAnswered=true")
            all_reviews.extend(answered_reviews)

            filtered_reviews = []
            for review in all_reviews:
                has_answer = bool(review.get("answer", "").strip())

                if answered and has_answer:
                    filtered_reviews.append(review)
                elif not answered and not has_answer:
                    filtered_reviews.append(review)

            reviews = filtered_reviews
            logger.info(
                f"✅ После фильтрации WB: {len(reviews)} отзывов (запрошено answered={answered}, всего получено {len(all_reviews)})")
        else:
            logger.error(f"❌ Платформа {platform} не поддерживается.")
            return []

        if not reviews:
            logger.warning(f"⚠️ Отзывы не получены с {platform}. Возможные причины: пустой список или ошибка API.")
            return []

        if reviews and len(reviews) > 0:
            logger.debug(f"Пример отзыва: {json.dumps(reviews[0], ensure_ascii=False, indent=2)}")

        sku_to_name = {}
        try:
            products_list = await get_store_products(
                str(client_id) if client_id else "",
                str(api_key),
                platform=str(platform),
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
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить список товаров для {platform}: {e}")

        result = []
        for review in reviews:
            created_at = review.get("created_at", "")
            parsed_date = None

            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed_date = datetime.strptime(created_at, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            if not parsed_date:
                parsed_date = datetime.now(timezone.utc)

            user_name = ""
            if platform.lower() == "wildberries":
                user_name = review.get("userName", "")
            elif platform.lower() == "ozon":
                user_name = review.get("user_name", review.get("author", ""))

            if platform.lower() == "ozon":
                sku = str(review.get("sku", review.get("product", {}).get("sku", "")))
            elif platform.lower() == "wildberries":
                sku = str(review.get("nmId", ""))
            else:
                sku = "N/A"

            if not sku:
                sku = "N/A"

            product_name = sku_to_name.get(sku,
                                           "Неизвестный товар") if platform.lower() != "wildberries" else review.get(
                "product_name", "Неизвестный товар")

            result.append({
                "id": review.get("id"),
                "text": review.get("text", ""),
                "rating": review.get("rating", 0),
                "created_at": parsed_date,
                "answer": review.get("answer", ""),
                "sku": sku,
                "product_name": product_name,
                "user_name": user_name,
                "pros": review.get("pros", "") if platform.lower() == "wildberries" else "",
                "cons": review.get("cons", "") if platform.lower() == "wildberries" else "",
                "supplierArticle": review.get("supplierArticle", "N/A"),
            })

        result.sort(key=lambda x: x["created_at"], reverse=True)

        logger.info(
            f"📅 Успешно обработано {len(result)} отзывов. "
            f"Диапазон дат: {result[0]['created_at'].strftime('%Y-%m-%d %H:%M:%S')} → "
            f"{result[-1]['created_at'].strftime('%Y-%m-%d %H:%M:%S')}"
        )

        return result

    except Exception as e:
        logger.error(f"❌ Ошибка при получении отзывов: {str(e)}", exc_info=True)
        return []

async def post_review_answer(
        client_id: str,
        api_key: str,
        review_id: str,
        answer_text: str,
        platform: str = "Ozon",
        secret_key: str = None,
        timestamp: int = int(time.time())
) -> bool:
    if platform not in PLATFORM_CONFIG:
        logger.error(f"Неподдерживаемая платформа: {platform}")
        return False

    config = PLATFORM_CONFIG[platform]
    if platform == "Kaufland":
        headers = config["review_headers"](client_id, api_key, secret_key, timestamp)
    else:
        headers = config["review_headers"](client_id, api_key) if config.get("requires_client_id", False) else config[
            "review_headers"]("", api_key)
    url = config["answer_url"].format(review_id=review_id) if "{review_id}" in config["answer_url"] else config[
        "answer_url"]

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if config["answer_method"] == "POST":
                body = config["answer_body"](review_id, answer_text)
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
            elif config["answer_method"] == "PATCH":
                body = config["answer_body"](review_id, answer_text)
                async with session.patch(url, headers=headers, json=body) as response:
                    response.raise_for_status()
            else:
                logger.error(f"Неподдерживаемый метод {config['answer_method']} для {platform}")
                return False

        logger.info(f"Ответ на отзыв {review_id} отправлен для {platform}")
        return True

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка отправки ответа на отзыв {platform}: {e}")
        return False

async def get_reviews_since(
        client_id: str,
        api_key: str,
        platform: str,
        since: datetime,
        limit: int,
        last_id: str,
        status: str
) -> List[Dict[str, Any]]:
    if platform == "Ozon":
        config = PLATFORM_CONFIG["Ozon"]
        headers = config["review_headers"](client_id, api_key)
        url = config["review_url"]
        since_iso = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = {
            "last_id": last_id,
            "limit": limit,
            "sort_dir": "DESC",
            "status": status,
            "filter": {
                "date_from": since_iso
            }
        }

        try:
            logger.info(f"Sending POST to {url} with body: {body}, status={status}")
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    data = await response.json()

            logger.debug(f"Response from Ozon API: {json.dumps(data, ensure_ascii=False)}")
            return config["review_response_parser"](data)
        except Exception as e:
            logger.error(f"Error getting reviews for Ozon: {e}")
            return []

    return await get_reviews(
        client_id=client_id,
        api_key=api_key,
        platform=platform,
        status=status,
        limit=limit,
        last_id=last_id
    )

async def get_questions(
        client_id: str,
        api_key: str,
        platform: str = "Ozon",
        status: str = "UNPROCESSED",
        limit: int = 20,
        last_id: str = "",
        nmId: int = None,
        date_from: datetime = None,
        date_to: datetime = None
) -> Dict[str, Any]:
    if platform not in PLATFORM_CONFIG:
        logger.error(f"Неподдерживаемая платформа: {platform}")
        return {"questions": [], "last_id": ""}

    config = PLATFORM_CONFIG[platform]
    headers = config.get("question_headers", config["review_headers"])(client_id, api_key)
    url = config["question_url"]

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if config["question_method"] == "GET":
                params = config["question_params"](status, limit, last_id, nmId, date_from, date_to)
                logger.info(f"[{platform}] GET {url} params={params}")
                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
            else:
                body = config["question_body"](status, limit, last_id)
                logger.info(f"[{platform}] POST {url} body={body}")
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    data = await response.json()

        logger.debug(f"Response from {platform}: {json.dumps(data, ensure_ascii=False)}")

        if platform == "Ozon":
            questions = data.get("questions", [])
            if not questions:
                logger.info(f"Ozon: нет вопросов со статусом {status}")
                return {"questions": [], "last_id": ""}

            actual_questions = [q for q in questions if q.get("status") == status]
            if not actual_questions and questions:
                logger.info(f"Ozon: найдено {len(questions)} вопросов, но ни один не имеет статуса {status}")
                return {"questions": [], "last_id": data.get("last_id", "")}

            questions = config["question_response_parser"](data)
        else:
            questions = config["question_response_parser"](data)

        last_id = str(data.get("data", {}).get("skip", 0) + len(questions)) if platform == "Wildberries" else data.get(
            "last_id", "")

        logger.info(f"{platform}: получено {len(questions)} вопросов со статусом {status}, last_id={last_id}")
        return {"questions": questions, "last_id": last_id}

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка запроса вопросов {platform}: {e}")
        return {"questions": [], "last_id": ""}
    except json.JSONDecodeError:
        logger.error(f"Ошибка JSON при разборе ответа вопросов {platform}")
        return {"questions": [], "last_id": ""}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении вопросов {platform}: {e}")
        return {"questions": [], "last_id": ""}

async def get_store_questions(
        store_id: int,
        answered: bool = False,
        limit: int = 20,
        last_id: str = "",
        nmId: int = None,
        date_from: datetime = None,
        date_to: datetime = None
) -> Dict[str, Any]:
    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            logger.error(f"Store not found for store_id={store_id}")
            return {"questions": [], "last_id": ""}

        platform = store.get("type", "Ozon")
        client_id = store.get("client_id", "")
        api_key = store.get("api_key", "")
        status = "PROCESSED" if answered else "UNPROCESSED"

        try:
            response = await get_questions(client_id, api_key, platform, status, limit, last_id, nmId, date_from,
                                           date_to)
            logger.info(f"Raw API response for store_id={store_id}, platform={platform}, status={status}: {response}")
            questions = response.get("questions", [])
            logger.info(
                f"Fetched {len(questions)} questions for store_id={store_id}, platform={platform}, status={status}")

            sku_to_name = {}
            try:
                products_list = await get_store_products(client_id, api_key, platform=platform, include_archived=True)
                for product in products_list:
                    if "(sku:" in product:
                        try:
                            name_part, sku_part = product.split("(sku:")
                            sku = sku_part.strip(" )")
                            sku_to_name[sku] = name_part.strip()
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"⚠️ Не удалось загрузить список товаров для {platform}: {e}")

            result = []
            for question in questions:
                if platform.lower() == "ozon":
                    sku = str(question.get("sku", ""))
                elif platform.lower() == "wildberries":
                    sku = str(question.get("sku", ""))
                else:
                    sku = "N/A"

                if not sku or sku == "0":
                    sku = "N/A"

                product_name = question.get("product_name", sku_to_name.get(sku, "Неизвестный товар"))

                parsed_question = {
                    "id": question.get("id"),
                    "text": question.get("text", ""),
                    "original_text": question.get("original_text", question.get("text", "")),
                    "created_at": question.get("created_at", ""),
                    "sku": sku,
                    "product_url": question.get("product_url", ""),
                    "product_name": product_name,
                    "answer": question.get("answer", ""),
                    "supplierArticle": question.get("supplierArticle", "N/A"),
                    "state": question.get("state", ""),
                    "wasViewed": question.get("wasViewed", False),
                    "isWarned": question.get("isWarned", False)
                }

                created_at = question.get("created_at", "")
                if created_at:
                    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                        try:
                            parsed_date = datetime.strptime(created_at, fmt).replace(tzinfo=timezone.utc)
                            parsed_question["created_at"] = parsed_date
                            break
                        except ValueError:
                            continue
                    else:
                        parsed_question["created_at"] = datetime.now(timezone.utc)

                result.append(parsed_question)

            result.sort(key=lambda x: x["created_at"], reverse=True)

            logger.info(
                f"📅 Успешно обработано {len(result)} вопросов. "
                f"Диапазон дат: {result[0]['created_at'].strftime('%Y-%m-%d %H:%M:%S')} → "
                f"{result[-1]['created_at'].strftime('%Y-%m-%d %H:%M:%S') if result else 'N/A'}"
            )

            return {
                "questions": result,
                "last_id": response.get("last_id", "")
            }

        except Exception as e:
            logger.error(f"Error fetching questions for store_id={store_id}: {str(e)}")
            return {"questions": [], "last_id": ""}

async def post_question_answer(
        client_id: str,
        api_key: str,
        question: Dict[str, Any],
        answer_text: str,
        platform: str,
        secret_key: str = None,
        timestamp: int = int(time.time())
) -> bool:
    if platform not in PLATFORM_CONFIG:
        logger.error(f"Неподдерживаемая платформа: {platform}")
        return False

    config = PLATFORM_CONFIG[platform]
    if platform == "Kaufland":
        headers = config["review_headers"](client_id, api_key, secret_key, timestamp)
    else:
        headers = config["review_headers"](client_id, api_key) if config.get("requires_client_id", False) else config[
            "review_headers"]("", api_key)
    url = config["question_answer_url"].format(question_id=question.get("id")) if "{question_id}" in config[
        "question_answer_url"] else config["question_answer_url"]

    question_id = question.get('id')
    if not question_id:
        logger.error(f"Отсутствует ID вопроса для {platform}")
        return False

    if platform == "Ozon":
        sku = question.get('sku')
        if not sku:
            logger.error("Отсутствует SKU товара для Ozon")
            return False
        body = config["question_answer_body"](question_id, sku, answer_text)
    else:
        body = config["question_answer_body"](question_id, answer_text)

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            if config["question_answer_method"] == "POST":
                async with session.post(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    data = await response.json() if response.content else {}
            elif config["question_answer_method"] == "PATCH":
                async with session.patch(url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    data = await response.json() if response.content else {}
            else:
                logger.error(f"Неподдерживаемый метод {config['question_answer_method']} для {platform}")
                return False

        if platform == "Ozon" and 'answer_id' not in data:
            logger.warning(f"Неожиданный ответ от Ozon: {data}")
            return False
        logger.info(f"Ответ на вопрос {question_id} отправлен для {platform}")
        return True

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка отправки ответа на вопрос {platform}: {e}")
        return False

async def get_review_comments(
        client_id: str,
        api_key: str,
        review_id: str,
        platform: str = "Ozon",
        limit: int = 20,
        offset: int = 0,
        sort_dir: str = "ASC"
) -> list:
    if platform != "Ozon":
        logger.error(f"Комментарии к отзывам поддерживаются только для Ozon, передан: {platform}")
        return []

    url = "https://api-seller.ozon.ru/v1/review/comment/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "limit": limit,
        "offset": offset,
        "review_id": review_id,
        "sort_dir": sort_dir
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Received comments for review_id={review_id}: {data}")
                    return data.get("comments", [])
                else:
                    logger.error(
                        f"Failed to fetch comments for review_id={review_id}, status={response.status}, response={await response.text()}")
                    return []
    except Exception as e:
        logger.error(f"Error fetching comments for review_id={review_id}: {str(e)}")
        return []

async def get_question_answers(
        client_id: str,
        api_key: str,
        question_id: str,
        sku: int,
        platform: str
) -> List[Dict[str, Any]]:
    if platform != "Ozon":
        logger.warning(f"Fetching question answers not supported for platform {platform}")
        return []

    url = "https://api-seller.ozon.ru/v1/question/answer/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "last_id": "",
        "question_id": question_id,
        "sku": sku
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch answers for question_id={question_id}, status={response.status}")
                    return []
                data = await response.json()
                answers = data.get("answers", [])
                logger.info(f"Fetched {len(answers)} answers for question_id={question_id}")
                return [
                    {
                        "id": answer["id"],
                        "text": answer.get("text", ""),
                        "author_name": answer.get("author_name", ""),
                        "published_at": answer.get("published_at", "")
                    }
                    for answer in answers
                ]
    except Exception as e:
        logger.error(f"Error fetching answers for question_id={question_id}: {e}")
        return []

async def get_store_products(
        client_id: str,
        api_key: str,
        platform: str = "Ozon",
        limit: int = 100,
        include_archived: bool = False
) -> List[str]:
    if not api_key:
        logger.error(f"Invalid api_key: {api_key}")
        return []
    if platform not in ["Ozon", "Wildberries"]:
        logger.error(f"Unsupported platform: {platform}")
        return []

    products = []

    try:
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ---------------------- OZON ----------------------
            if platform == "Ozon":
                headers = {
                    "Client-Id": client_id,
                    "Api-Key": api_key,
                    "Content-Type": "application/json"
                }
                product_ids = []
                last_id = ""
                visibility = "ALL" if include_archived else "IN_SALE"

                while True:
                    payload = {
                        "filter": {"visibility": visibility},
                        "last_id": last_id,
                        "limit": limit
                    }

                    async with session.post(
                            "https://api-seller.ozon.ru/v3/product/list",
                            headers=headers,
                            json=payload
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()

                    for item in data.get("result", {}).get("items", []):
                        if "product_id" in item:
                            product_ids.append(str(item["product_id"]))

                    last_id = data.get("result", {}).get("last_id", "")
                    if not last_id:
                        break

                if product_ids:
                    chunks = [product_ids[i:i + 100] for i in range(0, len(product_ids), 100)]
                    for chunk in chunks:
                        payload = {"product_id": chunk}
                        async with session.post(
                                "https://api-seller.ozon.ru/v3/product/info/list",
                                headers=headers,
                                json=payload
                        ) as response:
                            response.raise_for_status()
                            data = await response.json()

                        for item in data.get("items", []):
                            name = item.get("name", "")
                            sku = item.get("sku", "")
                            if name:
                                products.append(f"{name} (sku: {sku})" if sku else name)

            # ---------------------- WILDBERRIES ----------------------
            elif platform == "Wildberries":
                url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
                headers = {
                    "Authorization": api_key.strip(),
                    "Content-Type": "application/json"
                }

                cursor = {"limit": limit}
                total = limit

                while total >= limit:
                    payload = {
                        "settings": {
                            "cursor": cursor,
                            "filter": {"withPhoto": -1}
                        }
                    }

                    async with session.post(url, headers=headers, json=payload) as response:
                        if response.status != 200:
                            logger.error(f"WB API error {response.status_code}: {await response.text()}")
                            break
                        data = await response.json()

                    cards = data.get("cards", [])
                    cursor_data = data.get("cursor", {})
                    total = cursor_data.get("total", 0)

                    for card in cards:
                        nm = card.get("nmID")
                        name = card.get("title") or card.get("name") or "Без названия"
                        if nm and name:
                            products.append(f"{name} (nmID: {nm})")

                    if total < limit:
                        break

                    cursor = {
                        "updatedAt": cursor_data.get("updatedAt"),
                        "nmID": cursor_data.get("nmID"),
                        "limit": limit
                    }

        return products

    except Exception as e:
        logger.error(f"Ошибка при получении списка товаров на {platform}: {e}")
        return []

async def get_ozon_product_attributes(
        client_id: str,
        api_key: str,
        offer_id: str = None,
        product_id: str = None,
        sku: str = None,
        visibility: str = "ALL"
) -> Dict[str, Any]:
    attributes_url = "https://api-seller.ozon.ru/v4/product/info/attributes"
    description_url = "https://api-seller.ozon.ru/v1/product/info/description"

    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json"
    }

    filter_params = {"visibility": visibility}

    if offer_id:
        filter_params["offer_id"] = [offer_id]
    elif product_id:
        filter_params["product_id"] = [product_id]
    elif sku:
        filter_params["sku"] = [sku]
    else:
        logger.error("Не указан идентификатор товара (offer_id, product_id или sku)")
        return {}

    attributes_body = {
        "filter": filter_params,
        "limit": 1,
        "sort_dir": "ASC"
    }

    try:
        async with aiohttp.ClientSession() as session:
            logger.info(f"[Ozon Attributes] POST {attributes_url} body={attributes_body}")
            async with session.post(attributes_url, headers=headers, json=attributes_body) as response:
                response.raise_for_status()
                attributes_data = await response.json()

            if not attributes_data.get("result"):
                logger.warning("Товар не найден или нет характеристик")
                return {}

            product_data = attributes_data["result"][0]
            logger.info(f"Получены характеристики товара: {product_data.get('name', 'Unknown')}")

            description_body = {}
            description_result = {}

            if product_data.get('offer_id'):
                description_body["offer_id"] = product_data['offer_id']
            if product_data.get('id'):
                description_body["product_id"] = product_data['id']

            if description_body:
                logger.info(f"[Ozon Description] POST {description_url} body={description_body}")
                async with session.post(description_url, headers=headers, json=description_body) as response:
                    response.raise_for_status()
                    description_data = await response.json()
                    description_result = description_data.get("result", {})

                if description_result and 'description' in description_result:
                    product_data['description'] = description_result['description']
                    logger.info(f"Получено описание товара ({len(product_data['description'])} символов)")
            else:
                logger.warning("Не удалось получить идентификаторы для запроса описания товара")

            return product_data

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка запроса данных товара Ozon: {e}")
    except json.JSONDecodeError:
        logger.error("Ошибка JSON при разборе ответа данных товара")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при получении данных товара: {e}")

    return {}