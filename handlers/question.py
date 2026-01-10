import asyncio
import logging
import logger
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from handlers.store import show_store_info
from keyboards.kb_for_questions import questions_menu_ikb, questions_list_ikb, next_questions_ikb, question_action_ikb, \
    manual_question_reply_ikb, mode_ikb, single_question_ikb
from keyboards.kb_for_stores import main_menu_ikb
from states.states import Form
from i18n import _
from db.database import AsyncDatabase
from utils.api_utils import post_question_answer, get_question_answers, get_store_questions
from utils.ai_utils import generate_question_reply
from dateutil.parser import isoparse
from datetime import datetime
from utils.cache import store_cache
import html

router = Router()

async def edit_or_reply(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

async def render_questions_info(account_id: str, store: dict) -> tuple[str, InlineKeyboardMarkup]:
    questions_status = await _(account_id, "enabled") if store.get("questions_enabled", False) else await _(account_id,
                                                                                                         "disabled")
    mode = store.get("questions_mode", "manual")
    translated_mode = await _(account_id, f"mode_{mode.lower()}")

    store_id = store.get("store_id")
    unanswered_count = 0
    if store_id:
        try:
            # Используем кеш вместо прямого запроса к API
            cache_data = await store_cache.get_unanswered_counts(store_id)
            unanswered_count = cache_data.get("questions", 0)
            logging.info(f"Unanswered questions count from cache for store_id={store_id}: {unanswered_count}")
        except Exception as e:
            logging.error(f"Error getting unanswered questions count from cache for store_id={store_id}: {str(e)}")
            unanswered_count = 0

    message_text = await _(account_id, "questions_info",
                           questions_status=questions_status,
                           questions_mode=translated_mode,
                           unanswered_count=unanswered_count)
    kb = await questions_menu_ikb(account_id, store_id)
    return message_text, kb

@router.callback_query(Form.waiting_for_selected_store_action, F.data == "questions_work")
async def handle_questions_work(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        message_text, kb = await render_questions_info(account_id, store)
        await edit_or_reply(callback, message_text, kb)
        await state.set_state(Form.waiting_for_questions_action)
        await callback.answer()

@router.callback_query(Form.waiting_for_questions_action, F.data == "toggle_questions")
async def toggle_questions(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    logging.info(f"User {account_id} toggled questions auto_reply, store_id={store_id}")

    if not store_id:
        logging.warning(f"No store_id found for account_id={account_id}")
        await callback.message.edit_text(
            await _(account_id, "store_not_selected"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            logging.warning(f"Store not found for store_id={store_id}, account_id={account_id}")
            await callback.message.edit_text(
                await _(account_id, "store_not_found"),
                reply_markup=await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        logging.info(f"Before toggle: store_id={store_id}, questions_enabled={store.get('questions_enabled', False)}")
        is_enabled = not store.get("questions_enabled", False)
        try:
            await db.toggle_store_setting(store_id, "questions_enabled", is_enabled)
            store = await db.get_store_details(store_id)
            logging.info(
                f"After toggle: store_id={store_id}, questions_enabled={store.get('questions_enabled', False)}")
        except Exception as e:
            logging.error(f"Error toggling store setting for store_id={store_id}: {str(e)}")
            await callback.answer(await _(account_id, "error_processing"), show_alert=True)
            return

    status_text = f"✅ {await _(account_id, 'auto_questions_enabled')}" if is_enabled else f"🚫 {await _(account_id, 'auto_questions_disabled')}"
    await callback.answer(
        status_text,
        show_alert=False
    )

    message_text, kb = await render_questions_info(account_id, store)
    await callback.message.edit_text(message_text, reply_markup=kb)
    await state.set_state(Form.waiting_for_questions_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_questions_action, F.data == "question_modes")
async def set_questions_mode(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        current_mode = await _(account_id, f"mode_{store.get('questions_mode', 'manual').lower()}")
        await edit_or_reply(
            callback,
            await _(account_id, "current_questions_mode", current_mode=current_mode),
            reply_markup=await mode_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_questions_mode)
        await callback.answer()

@router.callback_query(Form.waiting_for_questions_mode, F.data.startswith("mode_"))
async def save_questions_mode(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    logging.info(f"User {account_id} setting questions mode, store_id={store_id}")

    if not store_id:
        logging.warning(f"No store_id found for account_id={account_id}")
        await callback.message.edit_text(
            await _(account_id, "store_not_selected"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            logging.warning(f"Store not found for store_id={store_id}, account_id={account_id}")
            await callback.message.edit_text(
                await _(account_id, "store_not_found"),
                reply_markup=await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        mode_name = callback.data.split("_")[1]
        mode_map = {"auto": "auto", "semi": "semi", "manual": "manual"}
        db_mode = mode_map.get(mode_name, "manual")
        try:
            await db.update_questions_mode(store_id, db_mode)
            display_mode = await _(account_id, f"mode_{db_mode}")
            logging.info(f"Questions mode set to {db_mode} for store_id={store_id}")
        except Exception as e:
            logging.error(f"Error setting questions mode for store_id={store_id}: {str(e)}")
            await callback.answer(await _(account_id, "error_processing"), show_alert=True)
            return

    await callback.answer(
        f"⚙️ {await _(account_id, 'questions_mode_set', mode=display_mode)}",
        show_alert=False
    )

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        message_text, kb = await render_questions_info(account_id, store)
    await callback.message.edit_text(message_text, reply_markup=kb)
    await state.set_state(Form.waiting_for_questions_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_questions_action, F.data == "questions_answered")
async def view_answered_questions(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    limit = 20

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        platform = store.get("type", "Ozon")

    params = {"limit": limit}
    if platform == "Ozon":
        params["last_id"] = ""

    response = await get_store_questions(store_id, answered=True, **params)
    questions = response.get("questions", [])

    if not questions:
        await edit_or_reply(
            callback,
            await _(account_id, "no_answered_questions"),
            await questions_menu_ikb(account_id, store_id)
        )
        await state.set_state(Form.waiting_for_questions_action)
        return

    questions_per_page = 5
    total_pages = (len(questions) + questions_per_page - 1) // questions_per_page

    await state.update_data(
        all_questions=questions,
        current_page=0,
        questions_per_page=questions_per_page,
        total_pages=total_pages,
        question_type="answered",
        last_id=response.get("last_id", "")
    )

    first_page_questions = questions[:questions_per_page]
    kb = await questions_list_ikb(account_id, first_page_questions, 0, total_pages, "answered")

    await edit_or_reply(
        callback,
        await _(account_id, "answered_questions_list"),
        kb
    )

    await state.set_state(Form.viewing_questions_list)
    await callback.answer()

@router.callback_query(Form.waiting_for_questions_action, F.data == "questions_unanswered")
async def view_unanswered_questions(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    limit = 20

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        platform = store.get("type", "Ozon")

    params = {"limit": limit}
    if platform == "Ozon":
        params["last_id"] = ""

    response = await get_store_questions(store_id, answered=False, **params)
    questions = response.get("questions", [])

    if not questions:
        await edit_or_reply(
            callback,
            await _(account_id, "no_unanswered_questions"),
            await questions_menu_ikb(account_id, store_id)
        )
        await state.set_state(Form.waiting_for_questions_action)
        return

    questions_per_page = 5
    total_pages = (len(questions) + questions_per_page - 1) // questions_per_page

    await state.update_data(
        all_questions=questions,
        current_page=0,
        questions_per_page=questions_per_page,
        total_pages=total_pages,
        question_type="unanswered",
        last_id=response.get("last_id", "")
    )

    first_page_questions = questions[:questions_per_page]
    kb = await questions_list_ikb(account_id, first_page_questions, 0, total_pages, "unanswered")

    await edit_or_reply(
        callback,
        await _(account_id, "unanswered_questions_list"),
        kb
    )

    await state.set_state(Form.viewing_questions_list)
    await callback.answer()

async def send_question_answer(store_id: int, question_id: str, answer_text: str):
    try:
        async with AsyncDatabase() as db:
            store_details = await db.get_store_details(store_id)
            if not store_details:
                return False

            question = {"id": question_id}
            result = await post_question_answer(
                client_id=store_details.get("client_id", ""),
                api_key=store_details["api_key"],
                question=question,
                answer_text=answer_text,
                platform=store_details["type"]
            )

            # Обновляем кеш после отправки ответа
            if result:
                await store_cache.decrement_question_count(store_id)

            return result
    except Exception as e:
        logging.error(f"Error sending question answer: {str(e)}")
        return False

async def show_current_question(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    questions = data.get("questions", [])
    current_index = data.get("current_question_index", 0)
    store_id = data.get("store_id")
    questions_mode = data.get("questions_mode", "manual")

    if current_index >= len(questions):
        await message.answer(
            await _(account_id, "all_questions_viewed"),
            reply_markup=await next_questions_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_questions_view)
        return

    question = questions[current_index]
    question["mode"] = questions_mode

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
    platform = store_details["type"]

    full_text = ""

    created_at = question.get("created_at", "")
    if created_at:
        try:
            if isinstance(created_at, datetime):
                dt = created_at
            else:
                dt = isoparse(created_at)
            full_text += f"📅 {dt.strftime('%d.%m.%Y %H:%M')}\n\n"
        except Exception as e:
            logging.warning(f"Failed to parse date '{created_at}' for question {question.get('id')}: {str(e)}")
            full_text += f"📅 {await _(account_id, 'date')}: {created_at}\n\n"
    else:
        full_text += f"📅 {await _(account_id, 'date')}: {await _(account_id, 'not_available')}\n\n"

    product_name = question.get("product_name", "Неизвестный товар")
    supplier_article = question.get("supplierArticle", "N/A")

    if platform == "Wildberries" and supplier_article and supplier_article != "N/A":
        product_name = f"{product_name} ({supplier_article})"

    sku = question.get("sku", "N/A")

    if platform == "Wildberries" and sku and sku != "N/A":
        product_display = f'<a href="https://www.wildberries.ru/catalog/{sku}/detail.aspx">{html.escape(product_name)}</a>'
    elif platform == "Ozon" and sku and sku != "N/A":
        product_display = f'<a href="https://www.ozon.ru/product/{sku}">{html.escape(product_name)}</a>'
    else:
        product_display = product_name

    if product_name and product_name != "Неизвестный товар":
        full_text += f"📦 {await _(account_id, 'product_name')}: {product_display}\n\n"

    if sku and sku != "N/A":
        if platform == "Wildberries":
            full_text += f"🔢 {await _(account_id, 'article')}: {sku}\n\n"
        else:
            full_text += f"🔢 {await _(account_id, 'sku')}: {sku}\n\n"

    full_text += f"❓ {await _(account_id, 'question')}: {question.get('original_text', question.get('text', ''))}\n\n"

    if store_details['type'] == "Wildberries":
        full_text += await _(account_id, "wildberries_question_warning") + "\n\n"

    try:
        if question['mode'] == "auto":
            async with AsyncDatabase() as db:
                store_details = await db.get_store_details(store_id)

            client_config = {
                "client_id": store_details.get("client_id", ""),
                "api_key": store_details["api_key"],
                "platform": store_details["type"]
            }

            reply_text = await generate_question_reply(
                question_text=question.get("original_text", question.get("text", "")),
                sku=question.get("sku", "Не указан"),
                link=question.get("product_url", "Не указан"),
                client_config=client_config,
                product_name=question.get("product_name", ""),
                supplier_article=question.get("supplierArticle", "")
            )
            success = await send_question_answer(store_id, question['id'], reply_text)
            if success:
                full_text += f"📫 {await _(account_id, 'answer_sent_auto', reply_text=reply_text)}"
            else:
                full_text += await _(account_id, "error_sending_answer")
            await message.answer(full_text, parse_mode="HTML")
            await move_to_next_question(message, state)

        elif question['mode'] == "semi":
            async with AsyncDatabase() as db:
                store_details = await db.get_store_details(store_id)

            client_config = {
                "client_id": store_details.get("client_id", ""),
                "api_key": store_details["api_key"],
                "platform": store_details["type"]
            }

            proposed_reply = await generate_question_reply(
                question_text=question.get("original_text", question.get("text", "")),
                sku=question.get("sku", "Не указан"),
                link=question.get("product_url", "Не указан"),
                client_config=client_config,
                product_name=question.get("product_name", ""),
                supplier_article=question.get("supplierArticle", "")
            )
            await state.update_data(current_question=question, proposed_reply=proposed_reply)
            full_text += f" {await _(account_id, 'proposed_answer', proposed_reply=proposed_reply)}\n\n"
            full_text += f"⚙️ {await _(account_id, 'choose_action')}"
            await message.answer(full_text, reply_markup=await question_action_ikb(account_id), parse_mode="HTML")
            await state.set_state(Form.waiting_for_question_action)

        elif question['mode'] == "manual":
            await state.update_data(current_question=question)
            full_text += f"🖋️ {await _(account_id, 'write_answer')}"
            await message.answer(full_text, reply_markup=await manual_question_reply_ikb(account_id), parse_mode="HTML")
            await state.set_state(Form.waiting_for_manual_question_reply)

    except Exception as e:
        logging.error(f"Error processing question: {str(e)}")
        await message.answer(await _(account_id, "error_processing_question", error=str(e)))
        await move_to_next_question(message, state)

async def move_to_next_question(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    current_index = data.get("current_question_index", 0) + 1
    questions = data.get("questions", [])
    await state.update_data(current_question_index=current_index)

    if current_index >= len(questions):
        await message.answer(
            await _(account_id, "all_questions_viewed"),
            reply_markup=await next_questions_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_questions_view)
        return
    await show_current_question(message, state)

@router.callback_query(Form.waiting_for_questions_view, F.data == "next_questions")
async def load_next_questions(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("store_id")
    last_id = data.get("last_id", "")

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        platform = store.get("type", "Ozon")

        user_stores = await db.get_user_stores(account_id)
        if not any(s[0] == store_id for s in user_stores):
            await callback.answer(await _(account_id, "store_access_denied"))
            return

    limit = 20
    params = {"limit": limit}
    if platform == "Ozon":
        params["last_id"] = last_id

    response = await get_store_questions(store_id, answered=False, **params)
    questions = response.get("questions", [])
    if not questions:
        await callback.message.answer(
            await _(account_id, "no_more_questions"),
            reply_markup=await questions_menu_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_questions_action)
        await callback.answer()
        return

    new_last_id = response.get("last_id", "")

    if store['type'] == "Wildberries":
        for q in questions:
            created_raw = q.get("createdDate") or q.get("created_at")
            if created_raw:
                try:
                    dt = isoparse(created_raw)
                    formatted_date = dt.strftime("%d.%m.%Y")
                    q["text"] = f"{formatted_date} | {q.get('text', '')}"
                except Exception:
                    q["text"] = f"{created_raw[:10]} | {q.get('text', '')}"

    await state.update_data(
        questions=questions,
        current_question_index=0,
        last_id=new_last_id
    )
    await show_current_question(callback.message, state)
    await callback.answer()

@router.callback_query(Form.waiting_for_question_action, F.data.in_(
    ["send_as_is_question", "edit_question_reply", "skip_question", "back_to_store_question"]))
async def handle_question_action(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    question = data.get("current_question")
    store_id = data.get("store_id")
    proposed_reply = data.get("proposed_reply")

    if callback.data == "send_as_is_question":
        success = await send_question_answer(store_id, question['id'], proposed_reply)
        if success:
            await callback.message.answer(await _(account_id, "answer_sent", reply_text=proposed_reply))
        else:
            await callback.message.answer(await _(account_id, "error_sending_answer"))
        await move_to_next_question(callback.message, state)

    elif callback.data == "edit_question_reply":
        await callback.message.answer(
            await _(account_id, "enter_your_answer"),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.update_data(manual_reply=proposed_reply)
        await state.set_state(Form.waiting_for_manual_question_reply)

    elif callback.data == "skip_question":
        await callback.message.answer(await _(account_id, "question_skipped"))
        await move_to_next_question(callback.message, state)

    elif callback.data == "back_to_store_question":
        async with AsyncDatabase() as db:
            store = await db.get_store_details(store_id)
            if not store:
                await edit_or_reply(
                    callback,
                    await _(account_id, "store_not_found"),
                    await main_menu_ikb(account_id)
                )
                await state.clear()
                return
        await show_store_info(callback, state, account_id, store_id)

    await callback.answer()

@router.message(Form.waiting_for_manual_question_reply)
async def handle_manual_question_reply_text(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    response_text = message.text.strip()
    await state.update_data(manual_reply=response_text)
    await message.answer(
        await _(account_id, "your_answer", response_text=response_text),
        reply_markup=await manual_question_reply_ikb(account_id)
    )

@router.callback_query(Form.waiting_for_manual_question_reply,
                       F.data.in_(["send_question_reply", "skip_question", "back_to_store_question"]))
async def handle_manual_question_reply_action(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("store_id")
    question = data.get("current_question")

    if callback.data == "send_question_reply":
        reply_text = data.get("manual_reply")
        if reply_text:
            success = await send_question_answer(store_id, question['id'], reply_text)
            if success:
                await callback.message.answer(await _(account_id, "answer_sent", reply_text=reply_text))
            else:
                await callback.message.answer(await _(account_id, "error_sending_answer"))
            await move_to_next_question(callback.message, state)
        else:
            await callback.message.answer(await _(account_id, "enter_answer_first"))

    elif callback.data == "skip_question":
        await callback.message.answer(await _(account_id, "question_skipped"))
        await move_to_next_question(callback.message, state)

    elif callback.data == "back_to_store_question":
        async with AsyncDatabase() as db:
            store = await db.get_store_details(store_id)
            if not store:
                await edit_or_reply(
                    callback,
                    await _(account_id, "store_not_found"),
                    await main_menu_ikb(account_id)
                )
                await state.clear()
                return
        await show_store_info(callback, state, account_id, store_id)

    await callback.answer()

@router.callback_query(Form.waiting_for_questions_action, F.data == "back_to_menu_from_questions")
async def handle_back_to_menu_from_questions(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "main_menu"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
    else:
        success = await show_store_info(callback, state, account_id, store_id)
        if not success:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                await main_menu_ikb(account_id)
            )
            await state.clear()

    await callback.answer()

@router.callback_query(Form.viewing_questions_list, F.data == "back_to_questions_menu")
async def handle_back_to_questions_menu(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        message_text, kb = await render_questions_info(account_id, store)
        await edit_or_reply(callback, message_text, kb)
        await state.set_state(Form.waiting_for_questions_action)
        await callback.answer()

@router.callback_query(Form.waiting_for_questions_mode, F.data == "back_to_questions_menu")
async def handle_back_to_questions_menu_from_modes(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        message_text, kb = await render_questions_info(account_id, store)
        await edit_or_reply(callback, message_text, kb)
        await state.set_state(Form.waiting_for_questions_action)
        await callback.answer()

@router.callback_query(Form.viewing_questions_list,
                       F.data.in_(["np_answered", "pp_answered", "np_unanswered", "pp_unanswered"]))
async def handle_questions_pagination(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    # Правильно определяем тип вопросов и направление пагинации
    if callback.data.endswith("_answered"):
        question_type = "answered"
    else:
        question_type = "unanswered"

    if callback.data.startswith("np_"):
        direction = "next"
    else:
        direction = "previous"

    logging.info(
        f"Pagination: account_id={account_id}, store_id={store_id}, callback={callback.data}, direction={direction}, question_type={question_type}")

    current_page = data.get("current_page", 0)
    all_questions = data.get("all_questions", [])
    questions_per_page = data.get("questions_per_page", 5)
    total_pages = data.get("total_pages", 1)
    last_id = data.get("last_id", "")

    # Правильно вычисляем новую страницу
    if direction == "next":
        new_page = current_page + 1
    else:
        new_page = current_page - 1

    logging.info(
        f"Pagination: current_page={current_page}, new_page={new_page}, total_pages={total_pages}, total_questions={len(all_questions)}")

    # Инициализируем переменную new_questions
    new_questions = []

    # Обрабатываем граничные случаи
    if new_page < 0:
        await callback.answer(await _(account_id, "first_page"))
        return

    if new_page >= total_pages:
        # Пытаемся загрузить больше вопросов, если есть last_id
        if last_id:
            async with AsyncDatabase() as db:
                store = await db.get_store_details(store_id)
                platform = store.get("type", "Ozon")

            params = {"limit": 20}
            if platform == "Ozon":
                params["last_id"] = last_id

            try:
                response = await get_store_questions(store_id, answered=(question_type == "answered"), **params)
                new_questions = response.get("questions", [])
                logging.info(
                    f"Fetched {len(new_questions)} new questions for page {new_page}, question_type={question_type}")

                if new_questions:
                    all_questions.extend(new_questions)
                    last_id = response.get("last_id", "")
                    total_pages = (len(all_questions) + questions_per_page - 1) // questions_per_page
                else:
                    await callback.answer(await _(account_id, "no_more_questions"))
                    return
            except Exception as e:
                logging.error(f"Error loading more questions: {e}")
                await callback.answer(await _(account_id, "error_loading_questions"))
                return
        else:
            await callback.answer(await _(account_id, "no_more_questions"))
            return

    # Если мы все еще на той же странице после всех проверок
    if new_page == current_page and not new_questions:
        await callback.answer()
        return

    # Обновляем данные состояния
    await state.update_data(
        current_page=new_page,
        all_questions=all_questions,
        last_id=last_id,
        total_pages=total_pages,
        question_type=question_type
    )

    # Получаем вопросы для отображения
    start_idx = new_page * questions_per_page
    end_idx = start_idx + questions_per_page
    questions_to_show = all_questions[start_idx:end_idx]

    kb = await questions_list_ikb(account_id, questions_to_show, new_page, total_pages, question_type)

    try:
        await callback.message.edit_text(
            await _(account_id, f"{question_type}_questions_list"),
            reply_markup=kb
        )
    except Exception as e:
        if "message is not modified" in str(e):
            await callback.answer()
        else:
            logging.error(f"Error editing message: {e}")
            await callback.answer(await _(account_id, "error_processing"))

    await callback.answer()

@router.callback_query(Form.viewing_questions_list, F.data.startswith("vq_"))
async def view_single_question(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    question_id = callback.data.replace("vq_", "")
    logging.info(f"Attempting to view question: account_id={account_id}, question_id={question_id}")

    questions = data.get("all_questions", [])

    # Логируем информацию о всех вопросах
    logging.info(f"Total questions in state: {len(questions)}")
    logging.info(f"Question IDs in state: {[q.get('id') for q in questions]}")

    question = None
    for q in questions:
        if str(q.get("id")) == str(question_id):
            question = q
            break

    if not question:
        logging.error(
            f"Question not found: question_id={question_id}, available_ids={[q.get('id') for q in questions]}")
        await callback.answer(await _(account_id, "question_not_found"), show_alert=True)
        return

    store_id = data.get("selected_store_id")

    # Логируем информацию о магазине
    logging.info(f"Store ID from state: {store_id}")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            logging.error(f"Store not found: store_id={store_id}")
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

    platform = store_details["type"]
    questions_mode = store_details.get("questions_mode", "manual")

    full_text = ""
    question_index = next((i for i, q in enumerate(questions) if str(q.get("id")) == str(question_id)), -1)
    total_questions = len(questions)

    logging.info(f"Found question at index: {question_index}, total_questions: {total_questions}")

    # Остальной код функции остается без изменений...
    created_at = question.get("created_at", "")
    if created_at:
        try:
            if isinstance(created_at, datetime):
                dt = created_at
            else:
                dt = isoparse(created_at)
            full_text += f"📅 {dt.strftime('%d.%m.%Y %H:%M')}\n\n"
        except Exception as e:
            logging.warning(f"Failed to parse date '{created_at}' for question {question_id}: {str(e)}")
            full_text += f"📅 {await _(account_id, 'date')}: {created_at}\n\n"
    else:
        full_text += f"📅 {await _(account_id, 'date')}: {await _(account_id, 'not_available')}\n\n"

    product_name = question.get("product_name", "Неизвестный товар")
    supplier_article = question.get("supplierArticle", "N/A")

    if platform == "Wildberries" and supplier_article and supplier_article != "N/A":
        product_name = f"{product_name} ({supplier_article})"

    sku = question.get("sku", "N/A")

    if platform == "Wildberries" and sku and sku != "N/A":
        product_display = f'<a href="https://www.wildberries.ru/catalog/{sku}/detail.aspx">{html.escape(product_name)}</a>'
    elif platform == "Ozon" and sku and sku != "N/A":
        product_display = f'<a href="https://www.ozon.ru/product/{sku}">{html.escape(product_name)}</a>'
    else:
        product_display = product_name

    if product_name and product_name != "Неизвестный товар":
        full_text += f"📦 {await _(account_id, 'product_name')}: {product_display}\n\n"

    if sku and sku != "N/A":
        if platform == "Wildberries":
            full_text += f"🔢 {await _(account_id, 'article')}: {sku}\n\n"
        else:
            full_text += f"🔢 {await _(account_id, 'sku')}: {sku}\n\n"

    full_text += f"❓ {await _(account_id, 'question')}: {question.get('original_text', question.get('text', ''))}\n\n"

    question_type = data.get("question_type", "unanswered")
    logging.info(f"Question type: {question_type}")

    if question_type == "answered":
        if platform == "Ozon" and sku and sku != "N/A":
            try:
                answers = await get_question_answers(
                    client_id=store_details.get("client_id", ""),
                    api_key=store_details["api_key"],
                    question_id=question_id,
                    sku=sku,
                    platform=platform
                )
                if answers:
                    full_text += f"📫 {await _(account_id, 'answer')}: {answers[0]['text']}\n\n"
                else:
                    full_text += f"📫 {await _(account_id, 'answer')}: {await _(account_id, 'not_available')}\n\n"
            except Exception as e:
                logging.error(f"Error getting answers for question {question_id}: {str(e)}")
                full_text += f"📫 {await _(account_id, 'answer')}: {await _(account_id, 'error_loading')}\n\n"

        elif platform == "Wildberries":
            answer_text = question.get("answer")
            if answer_text:
                full_text += f"📫 {await _(account_id, 'answer')}: {answer_text}\n\n"
            else:
                full_text += f"📫 {await _(account_id, 'answer')}: {await _(account_id, 'not_available')}\n\n"

        full_text += f"🔢 {question_index + 1} из {total_questions}"

    if question_type == "unanswered":
        await state.update_data(current_question=question)
        if questions_mode in ["auto", "semi"]:
            try:
                async with AsyncDatabase() as db:
                    store_details = await db.get_store_details(store_id)

                client_config = {
                    "client_id": store_details.get("client_id", ""),
                    "api_key": store_details["api_key"],
                    "platform": store_details["type"]
                }

                proposed_reply = await generate_question_reply(
                    question_text=question.get("original_text", question.get("text", "")),
                    sku=question.get("sku", "Не указан"),
                    link=question.get("product_url", "Не указан"),
                    client_config=client_config,
                    product_name=question.get("product_name", ""),
                    supplier_article=question.get("supplierArticle", "")
                )

                await state.update_data(proposed_reply=proposed_reply)
                full_text += f"{await _(account_id, 'proposed_answer', proposed_reply=proposed_reply)}\n\n"

            except Exception as e:
                logging.error(f"Error generating AI reply for question {question_id}: {str(e)}")
                full_text += f"Warning: {await _(account_id, 'error_generating_ai_reply')}\n\n"

    kb = await single_question_ikb(
        account_id, question_id, question_type, questions_mode,
        question_index, total_questions, questions
    )

    try:
        await callback.message.edit_text(full_text, reply_markup=kb, parse_mode="HTML")
        logging.info(f"Successfully displayed question {question_id}")
    except Exception as e:
        logging.error(f"Error displaying question {question_id}: {str(e)}")
        await callback.message.answer(full_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("mr_"))
async def handle_manual_reply(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    question_id = callback.data.replace("mr_", "")
    data = await state.get_data()
    question = data.get("current_question")
    if question['id'] != question_id:
        await callback.answer(await _(account_id, "question_not_found"), show_alert=True)
        return

    await callback.message.answer(
        await _(account_id, "write_answer"),
        reply_markup=await manual_question_reply_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_manual_question_reply)
    await callback.answer()

@router.callback_query(F.data.startswith("sai_"))
async def handle_send_ai_reply(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    question_id = callback.data.replace("sai_", "")
    data = await state.get_data()
    question = data.get("current_question")
    store_id = data.get("selected_store_id")
    if question['id'] != question_id:
        await callback.answer(await _(account_id, "question_not_found"), show_alert=True)
        return

    try:
        async with AsyncDatabase() as db:
            store_details = await db.get_store_details(store_id)

        client_config = {
            "client_id": store_details.get("client_id", ""),
            "api_key": store_details["api_key"],
            "platform": store_details["type"]
        }

        reply_text = await generate_question_reply(
            question_text=question.get('original_text', question.get('text', '')),
            sku=question.get("sku", "Не указан"),
            link=question.get("product_url", "Не указан"),
            client_config=client_config,
            product_name=question.get("product_name", ""),
            supplier_article=question.get("supplierArticle", "")
        )
        success = await send_question_answer(store_id, question_id, reply_text)
        if success:
            await callback.message.answer(await _(account_id, "answer_sent_auto", reply_text=reply_text))
        else:
            await callback.message.answer(await _(account_id, "error_sending_answer"))
    except Exception as e:
        logging.error(f"Error generating or sending AI reply: {str(e)}")
        await callback.message.answer(await _(account_id, "error_processing"))

    await back_to_questions_list(callback, state)
    await callback.answer()

@router.callback_query(Form.viewing_questions_list, F.data.startswith("bl_"))
async def back_to_questions_list(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    question_type = callback.data.replace("bl_", "")

    all_questions = data.get("all_questions", [])
    current_page = data.get("current_page", 0)
    questions_per_page = data.get("questions_per_page", 5)
    total_pages = data.get("total_pages", 1)

    start_idx = current_page * questions_per_page
    end_idx = start_idx + questions_per_page
    questions_to_show = all_questions[start_idx:end_idx]

    kb = await questions_list_ikb(account_id, questions_to_show, current_page, total_pages, question_type)

    await callback.message.edit_text(
        await _(account_id, f"{question_type}_questions_list"),
        reply_markup=kb
    )
    await callback.answer()