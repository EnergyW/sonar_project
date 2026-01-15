import logging
import html
from collections import Counter
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_reviews import reviews_menu_ikb, review_action_ikb, manual_reply_ikb, next_reviews_ikb, \
    reviews_list_ikb, review_mode_ikb, review_details_ikb
from keyboards.kb_for_stores import main_menu_ikb
from states.states import Form
from i18n import _
from db.database import AsyncDatabase
from utils.api_utils import get_review_comments, post_review_answer
from utils.ai_utils import generate_reply
from aiogram.types import InlineKeyboardMarkup
from states.states import MODES
from utils.cache import store_cache
import time

async def edit_or_reply(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

async def render_reviews_info(account_id: str, store: dict, store_id: str) -> tuple[str, InlineKeyboardMarkup]:
    try:
        reviews_status = await _(account_id, "enabled") if store.get("reviews_enabled", False) else await _(account_id,
                                                                                                            "disabled")

        modes = store.get("modes", {})
        modes_text = ""
        for i in range(1, 6):
            mode = modes.get(str(i), "mode_not_set")
            translated_mode = await _(account_id, f"mode_{mode.lower()}" if mode in MODES else "mode_not_set")
            modes_text += await _(account_id, "mode_info", rating=i, mode=translated_mode) + "\n"

        cache_data = await store_cache.get_unanswered_counts(store_id)
        unanswered_count = cache_data["reviews"]

        logging.info(f"📊 Using cached review count for store_id={store_id}: {unanswered_count} unanswered reviews")

        message_text = await _(account_id, "reviews_info",
                               reviews_status=reviews_status,
                               modes_info=modes_text.strip(),
                               unanswered_count=unanswered_count)
        kb = await reviews_menu_ikb(account_id, store_id)
        return message_text, kb
    except Exception as e:
        logging.error(f"Error in render_reviews_info for account_id={account_id}, store_id={store_id}: {str(e)}")
        return await _(account_id, "error_processing"), await main_menu_ikb(account_id)

async def show_next_review(callback: CallbackQuery, state: FSMContext, action: str = "next"):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    current_index = data["current_review_index"]
    reviews = data["all_reviews"]

    if not reviews:
        await callback.answer(await _(account_id, "no_reviews_found"))
        return

    if action == "next":
        new_index = current_index + 1
    elif action == "prev":
        new_index = current_index - 1
    else:
        new_index = current_index + 1

    if new_index < 0:
        new_index = 0
    elif new_index >= len(reviews):
        new_index = len(reviews) - 1

    await state.update_data(current_review_index=new_index)
    await show_review_details(callback, state)

async def move_to_next_review(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    current_index = data.get("current_review_index", 0) + 1
    reviews = data.get("reviews", [])
    review_message_id = data.get("review_message_id")

    await state.update_data(current_review_index=current_index)

    if current_index >= len(reviews):
        if review_message_id:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=review_message_id,
                text=await _(account_id, "all_reviews_viewed"),
                reply_markup=await next_reviews_ikb(account_id)
            )
        else:
            await message.answer(
                await _(account_id, "all_reviews_viewed"),
                reply_markup=await next_reviews_ikb(account_id)
            )
        await state.set_state(Form.waiting_for_reviews_view)
        return

    await show_current_review(message, state)

async def send_review_answer(store_details, review_id, answer_text) -> bool:
    try:
        return await post_review_answer(
            client_id=store_details.get("client_id", ""),
            api_key=store_details["api_key"],
            review_id=review_id,
            answer_text=answer_text,
            platform=store_details["type"]
        )
    except Exception as e:
        logging.error(f"Error sending review answer: {str(e)}")
        return False

async def show_review_details(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    all_reviews = data.get("all_reviews", [])
    review_type = data.get("review_type", "unanswered")
    current_index = data.get("current_review_index")
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)

    if current_index is None or current_index >= len(all_reviews):
        await edit_or_reply(
            callback,
            await _(account_id, "review_not_found"),
            reply_markup=await reviews_menu_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_reviews_type_selection)
        return

    review = all_reviews[current_index]

    if review_type == "answered" and not review.get("answer") and store_details["type"].lower() == "ozon":
        comments = await get_review_comments(
            client_id=store_details.get("client_id", ""),
            api_key=store_details["api_key"],
            review_id=review["id"],
            platform=store_details["type"],
            limit=20
        )
        official_comment = next(
            (c for c in comments if c.get("is_official") or c.get("is_owner")),
            None,
        )
        review["answer"] = official_comment.get("text", "") if official_comment else ""
        all_reviews[current_index]["answer"] = review["answer"]
        await state.update_data(all_reviews=all_reviews)

    date = review["created_at"].strftime("%d.%m.%Y")
    stars = f"{review['rating']}⭐️"
    text = review.get("text", "")
    base_product_name = review.get("product_name", await _(account_id, "unknown_product"))
    supplier_article = review.get("supplierArticle", "")
    product_name = f"{base_product_name} ({supplier_article})" if supplier_article and supplier_article != "N/A" else base_product_name
    sku_label = "Артикул" if store_details["type"].lower() == "wildberries" else "SKU"
    sku = review.get("nmId", review.get("sku", await _(account_id, "sku_not_available")))
    user_name = selected_review.get("user_name", "")
    user_display = f"👤 {user_name}\n\n" if user_name and store_details["type"].lower() == "wildberries" else ""

    if store_details["type"].lower() == "wildberries":
        product_display = f'<a href="https://www.wildberries.ru/catalog/{sku}/detail.aspx">{html.escape(product_name)}</a>'
    elif store_details["type"].lower() == "ozon":
        product_display = f'<a href="https://www.ozon.ru/product/{sku}">{html.escape(product_name)}</a>'
    else:
        product_display = product_name

    template_text = text
    if store_details["type"].lower() == "wildberries":
        pros = review.get("pros", "")
        cons = review.get("cons", "")
        if pros:
            template_text += f". {await _(account_id, 'pros')}: {pros}"
        if cons:
            template_text += f". {await _(account_id, 'cons')}: {cons}"

    try:
        response = await _(account_id, "review_details",
                           date=date,
                           stars=stars,
                           user_display=user_display,
                           sku_label=sku_label,
                           sku=sku,
                           product_name=product_display,
                           text=template_text if template_text else "(нет текста)"
                           )
    except Exception as e:
        logging.error(f"Translation error: {str(e)}")
        response = (
            f"📅 {date}\n\n"
            f"🌟 {stars}\n\n"
            f"{user_display}"
            f"📦 Название: {product_display}\n"
            f"🔢 {sku_label}: {sku}\n\n"
            f"💬 {template_text if template_text else '(нет текста)'}"
        )

    if review_type == "answered":
        answer = review.get("answer", "")
        clean_answer = html.unescape(str(answer)).strip()
        if clean_answer:
            response += "\n\n" + await _(account_id, "store_reply", answer=clean_answer)
        else:
            response += "\n\n" + await _(account_id, "no_store_reply")

    response += "\n\n" + await _(
        account_id,
        "review_counter",
        current=current_index + 1,
        total=len(all_reviews),
    )

    if review_type == "unanswered":
        mode = store_details.get("modes", {}).get(str(review["rating"]), "manual")
        keyboard = await review_mode_ikb(
            account_id=account_id,
            mode=mode,
            review_id=str(review["id"]),
            current_index=current_index,
            total_reviews=len(all_reviews),
        )
    else:
        keyboard = await review_details_ikb(
            account_id,
            review["id"],
            review_type,
            current_index,
            len(all_reviews),
        )

    await edit_or_reply(callback, response, reply_markup=keyboard)
    await state.update_data(current_review_id=review["id"])
    await state.set_state(Form.viewing_review_details)