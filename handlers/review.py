import logging
import logger
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_reviews import reviews_menu_ikb, review_action_ikb, manual_reply_ikb, \
    reviews_list_ikb, mode_ikb, review_details_ikb, review_mode_ikb
from keyboards.kb_for_stores import main_menu_ikb, store_action_ikb
from states.states import Form, MODES
from i18n import _
from db.database import AsyncDatabase
from utils.api_utils import get_reviews, post_review_answer, get_reviews_since, get_review_comments, \
    get_store_reviews
from utils.ai_utils import generate_reply
from datetime import datetime, timedelta, timezone
import json
import html
from collections import Counter
from handlers.review_utils import edit_or_reply, render_reviews_info, show_next_review, move_to_next_review,\
    send_review_answer, show_review_details
from aiogram.filters import StateFilter
from utils.cache import store_cache
import time
from keyboards.kb_for_store_settings import rating_ikb

router = Router()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

@router.callback_query(Form.waiting_for_selected_store_action, F.data == "reviews_work")
async def handle_reviews_work(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    logging.info(f"User {account_id} entered reviews_work, store_id={store_id}")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        message_text, kb = await render_reviews_info(account_id, store, store_id)
        await edit_or_reply(
            callback,
            message_text,
            kb
        )
        await state.set_state(Form.waiting_for_reviews_action)
        await callback.answer()

@router.callback_query(Form.waiting_for_reviews_action, F.data == "review_modes")
async def choose_rating(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"))
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await callback.answer(await _(account_id, "store_not_found"))
            return

        modes = store.get("modes", {})
        text = await _(account_id, "current_modes") + "\n\n"
        for i in range(1, 6):
            mode = modes.get(str(i), "mode_not_set")
            translated_mode = await _(account_id, f"mode_{mode.lower()}" if mode in MODES else "mode_not_set")
            text += await _(account_id, "mode_info", rating=i, mode=translated_mode) + "\n"

        await edit_or_reply(callback, text, reply_markup=await rating_ikb(account_id))
        await state.set_state(Form.waiting_for_rating_to_change_mode)
        await callback.answer()

@router.callback_query(Form.waiting_for_rating_to_change_mode, F.data.startswith("rate_"))
async def handle_rating_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    rating = int(callback.data.split("_")[1])
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return
    await state.update_data(selected_rating=rating)
    await edit_or_reply(
        callback,
        await _(account_id, "rating_selected", rating=rating),
        reply_markup=await mode_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_mode_selection)
    await callback.answer()

@router.callback_query(Form.waiting_for_mode_selection)
async def handle_mode_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    rating = data.get("selected_rating")
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        if callback.data.startswith("mode_"):
            mode_name = callback.data.split("_")[1]
            mode_map = {
                "auto": "auto",
                "semi": "semi",
                "manual": "manual",
                "template": "template"
            }
            db_mode = mode_map.get(mode_name, "manual")
            display_mode = await _(account_id, f"mode_{db_mode}")

            if db_mode == "template":
                templates = store.get("templates", {})
                if not templates.get(str(rating)):
                    await callback.answer(await _(account_id, "no_template_for_rating", rating=rating), show_alert=True)
                    return

            await db.update_store_mode(store_id, rating, db_mode)
            store = await db.get_store_details(store_id)

            modes = store.get("modes", {})
            text = await _(account_id, "current_modes") + "\n\n"
            for i in range(1, 6):
                mode = modes.get(str(i), "mode_not_set")
                translated_mode = await _(account_id,
                                          f"mode_{mode.lower()}" if mode in mode_map.values() else "mode_not_set")
                text += await _(account_id, "mode_info", rating=i, mode=translated_mode) + "\n"

            await callback.answer(
                f"⚙️ {await _(account_id, 'mode_updated', rating=rating, mode=display_mode)}",
                show_alert=False
            )

            await callback.message.edit_text(text, reply_markup=await rating_ikb(account_id))
            await state.set_state(Form.waiting_for_rating_to_change_mode)
            return

        elif callback.data == "back_to_reviews_menu":
            message_text, kb = await render_reviews_info(account_id, store, store_id)
            await callback.message.edit_text(message_text, reply_markup=kb)
            await state.set_state(Form.waiting_for_reviews_action)
            await callback.answer()
            return

@router.callback_query(Form.waiting_for_mode_selection, F.data == "back_to_rating_selection")
async def back_from_mode_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"))
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await callback.answer(await _(account_id, "store_not_found"))
            return

        modes = store.get("modes", {})
        text = await _(account_id, "current_modes") + "\n\n"
        for i in range(1, 6):
            mode = modes.get(str(i), "mode_not_set")
            translated_mode = await _(account_id, f"mode_{mode.lower()}" if mode in MODES else "mode_not_set")
            text += await _(account_id, "mode_info", rating=i, mode=translated_mode) + "\n"

        await callback.message.edit_text(
            text,
            reply_markup=await rating_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_rating_to_change_mode)
        await callback.answer()

@router.callback_query(Form.waiting_for_review_action)
async def handle_review_action(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    review = data.get("current_review")
    store_id = data.get("store_id")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)

    proposed_reply = data.get("proposed_reply")
    modes = store_details.get("modes", {})
    mode = modes.get(str(review['rating']), "manual")

    if mode == "auto":
        success = await send_review_answer(store_details, review['id'], proposed_reply)
        if success:
            await callback.message.answer(await _(account_id, "answer_sent", reply_text=proposed_reply))
        else:
            await callback.message.answer(await _(account_id, "error_sending_answer"))
        await move_to_next_review(callback.message, state)
        await callback.answer()
        return

    if mode == "semi":
        kb = await review_mode_ikb(
            account_id=account_id,
            mode=mode,
            current_index=data.get("current_index", 0),
            total_reviews=data.get("total_reviews", 1)
        )
        await callback.message.edit_text(
            f"⭐️ {review['rating']}\n\n{review['text']}\n\n🤖 {await _(account_id, 'proposed_reply')}:\n\n{proposed_reply}",
            reply_markup=kb
        )
        await state.set_state(Form.viewing_review_details)
        await callback.answer()
        return

    if mode == "manual":
        await callback.message.answer(
            await _(account_id, "enter_your_answer"),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.update_data(editing_reply=True)
        await state.set_state(Form.waiting_for_manual_reply)
        await callback.answer()
        return

    if mode == "template":
        templates = store_details.get("templates", {})
        rating = str(review['rating'])
        template = templates.get(rating)
        if not template:
            await callback.answer(await _(account_id, "no_template_for_rating", rating=rating), show_alert=True)
            return
        success = await send_review_answer(store_details, review['id'], template)
        if success:
            await callback.message.answer(await _(account_id, "answer_sent", reply_text=template))
        else:
            await callback.message.answer(await _(account_id, "error_sending_answer"))
        await move_to_next_review(callback.message, state)
        await callback.answer()
        return

    if callback.data == "back_to_store":
        async with AsyncDatabase() as db:
            store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"))
            return
        message_text = await _(account_id, "store_info",
                               store_name=store_details['store_name'],
                               store_type=store_details['type'])
        is_owner = True
        kb = await store_action_ikb(account_id, is_owner)
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(message_text, reply_markup=kb)
        await state.set_state(Form.waiting_for_selected_store_action)
    await callback.answer()

@router.message(Form.waiting_for_manual_reply)
async def handle_manual_reply_text(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    await state.update_data(manual_reply=message.text)
    await message.answer(
        await _(account_id, "your_answer", response_text=message.text),
        reply_markup=await manual_reply_ikb(account_id)
    )

@router.callback_query(Form.waiting_for_manual_reply)
async def handle_manual_reply_action(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("store_id")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)

    review = data.get("current_review")

    if callback.data == "send_reply":
        reply_text = data.get("manual_reply")
        if reply_text:
            success = await send_review_answer(store_details, review['id'], reply_text)
            if success:
                await callback.message.answer(await _(account_id, "answer_sent", reply_text=reply_text))
            else:
                await callback.message.answer(await _(account_id, "error_sending_answer"))
            await move_to_next_review(callback.message, state)
        else:
            await callback.message.answer(await _(account_id, "enter_answer_first"))

    elif callback.data == "send_by_template":
        templates = store_details.get("templates", {})
        rating = str(review['rating'])
        template = templates.get(rating)
        if not template:
            await callback.answer(await _(account_id, "no_template_for_rating", rating=rating), show_alert=True)
            return
        success = await send_review_answer(store_details, review['id'], template)
        if success:
            await callback.message.answer(await _(account_id, "answer_sent", reply_text=template))
        else:
            await callback.message.answer(await _(account_id, "error_sending_answer"))
        await move_to_next_review(callback.message, state)

    elif callback.data == "back_to_store":
        async with AsyncDatabase() as db:
            store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"))
            return
        message_text = await _(account_id, "store_info",
                               store_name=store_details['store_name'],
                               store_type=store_details['type'])
        is_owner = True
        kb = await store_action_ikb(account_id, is_owner)
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(message_text, reply_markup=kb)
        await state.set_state(Form.waiting_for_selected_store_action)
    await callback.answer()

@router.callback_query(Form.waiting_for_reviews_list, F.data == "next_reviews")
async def handle_next_page(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()

    current_page = data.get("current_page", 0)
    reviews_per_page = data.get("reviews_per_page", 5)
    all_reviews = data.get("all_reviews", [])
    total_pages = data.get("total_pages", 1)

    if current_page >= total_pages - 1:
        await callback.answer(await _(account_id, "no_more_reviews"))
        return

    current_page += 1
    start_idx = current_page * reviews_per_page
    end_idx = start_idx + reviews_per_page
    reviews = all_reviews[start_idx:end_idx]

    rating_counts = Counter(r["rating"] for r in all_reviews)
    rating_summary = "\n".join([f"{i}⭐️: {rating_counts.get(i, 0)}" for i in range(1, 6)])
    review_type = data.get("review_type", "unanswered")
    translated_type = await _(account_id, "answered" if review_type == "answered" else "unanswered")
    response = await _(account_id, "reviews_list_title", type=translated_type, rating_summary=rating_summary)

    await callback.message.edit_text(
        response,
        reply_markup=await reviews_list_ikb(reviews, current_page, total_pages)
    )
    await state.update_data(current_page=current_page)
    await callback.answer()

@router.callback_query(Form.waiting_for_reviews_list, F.data == "prev_reviews")
async def handle_prev_page(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()

    current_page = data.get("current_page", 0)
    reviews_per_page = data.get("reviews_per_page", 5)
    all_reviews = data.get("all_reviews", [])
    total_pages = data.get("total_pages", 1)

    if current_page == 0:
        await callback.answer(await _(account_id, "no_previous_reviews"))
        return

    current_page -= 1
    start_idx = current_page * reviews_per_page
    end_idx = start_idx + reviews_per_page
    reviews = all_reviews[start_idx:end_idx]

    rating_counts = Counter(r["rating"] for r in all_reviews)
    rating_summary = "\n".join([f"{i}⭐️: {rating_counts.get(i, 0)}" for i in range(1, 6)])
    review_type = data.get("review_type", "unanswered")
    translated_type = await _(account_id, "answered" if review_type == "answered" else "unanswered")
    response = await _(account_id, "reviews_list_title", type=translated_type, rating_summary=rating_summary)

    await callback.message.edit_text(
        response,
        reply_markup=await reviews_list_ikb(reviews, current_page, total_pages)
    )
    await state.update_data(current_page=current_page)
    await callback.answer()

@router.callback_query(Form.waiting_for_reviews_action, F.data == "back_to_store_from_reviews")
async def back_from_reviews(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            await main_menu_ikb(account_id)
        )
        return

    try:
        from handlers.store import show_store_info
        await show_store_info(callback, state, account_id, store_id)
    except (ImportError, AttributeError):
        async with AsyncDatabase() as db:
            store_details = await db.get_store_details(store_id)
            if not store_details:
                await edit_or_reply(
                    callback,
                    await _(account_id, "store_not_found"),
                    await main_menu_ikb(account_id)
                )
                await state.clear()
                return

            reviews_status = await _(account_id, "reviews_enabled") if store_details.get("reviews_enabled", False) else await _(account_id,
                                                                                                             "disabled")
            questions_status = await _(account_id, "enabled") if store_details.get("questions_enabled",
                                                                                False) else await _(account_id, "disabled")

            modes = store_details.get("modes", {})
            modes_info = "\n".join(
                [await _(account_id, "mode_info", rating=rating, mode=await _(account_id, f"mode_{mode.lower()}"))
                 for rating, mode in sorted(modes.items(), key=lambda x: int(x[0]))]) or await _(account_id,
                                                                                                 "modes_not_set")

            info = await _(account_id, "store_main_info",
                           store_name=store_details['store_name'],
                           store_type=store_details['type'],
                           api_key=store_details.get('api_key', await _(account_id, "not_set")),
                           client_id=store_details.get('client_id', await _(account_id, "not_set")),
                           reviews_status=reviews_status,
                           modes_info=modes_info,
                           questions_status=questions_status,
                           questions_mode=await _(account_id,
                                                  f"mode_{store_details.get('questions_mode', 'manual').lower()}"))

            try:
                await callback.message.delete()
            except:
                pass
            await callback.message.answer(
                info,
                reply_markup=await store_action_ikb(account_id, True)
            )
            await state.set_state(Form.waiting_for_selected_store_action)

    await callback.answer()

@router.callback_query(Form.waiting_for_reviews_action, F.data == "toggle_auto_reply")
async def toggle_auto_response(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    logging.info(f"User {account_id} toggled auto_reply, store_id={store_id}")

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

        logging.info(f"Before toggle: store_id={store_id}, reviews_enabled={store.get('reviews_enabled', False)}")
        current_enabled = store.get("reviews_enabled", False)
        new_enabled = not current_enabled

        try:
            result = await db.toggle_store_setting(store_id, 'reviews_enabled', new_enabled)

            if result is None:
                logging.error(f"Failed to toggle reviews_enabled for store_id={store_id}")
                await callback.answer(await _(account_id, "error_processing"), show_alert=True)
                return

            store = await db.get_store_details(store_id)
            logging.info(f"After toggle: store_id={store_id}, reviews_enabled={store.get('reviews_enabled', False)}")

        except Exception as e:
            logging.error(f"Error toggling store setting for store_id={store_id}: {str(e)}")
            await callback.answer(await _(account_id, "error_processing"), show_alert=True)
            return

        status_text = f"✅ {await _(account_id, 'auto_replies_enabled')}" if new_enabled else f"🚫 {await _(account_id, 'auto_replies_disabled')}"

        await callback.answer(
            status_text,
            show_alert=False
        )

        message_text, kb = await render_reviews_info(account_id, store, store_id)
        await callback.message.edit_text(message_text, reply_markup=kb)
        await state.set_state(Form.waiting_for_reviews_action)
        await callback.answer()

@router.message(Form.waiting_for_reply_text)
async def handle_reply_text(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    await state.update_data(reply_text=message.text)
    await message.answer(
        await _(account_id, "confirm_reply", reply_text=message.text),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=await _(account_id, "send"), callback_data="confirm_send"),
                InlineKeyboardButton(text=await _(account_id, "cancel"), callback_data="cancel_send")
            ],
            [InlineKeyboardButton(text=await _(account_id, "back_to_review"), callback_data="back_to_review")]
        ])
    )
    await state.set_state(Form.confirming_reply)

@router.callback_query(Form.confirming_reply, F.data == "confirm_send")
async def confirm_send(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()

    current_index = data["current_review_index"]
    reviews = data["all_reviews"]

    if current_index >= len(reviews):
        await callback.answer(await _(account_id, "review_not_found"))
        return

    review = reviews[current_index]
    reply_text = data.get("reply_text", "")

    if not reply_text:
        await callback.answer(await _(account_id, "empty_reply_text"))
        return

    store_id = data.get("selected_store_id")
    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"))
        return

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"))
            return

        success = await send_review_answer(store_details, review['id'], reply_text)
        if success:
            # Уменьшаем счетчик неотвеченных отзывов в кеше
            store_id_int = int(store_id)
            await store_cache.decrement_review_count(store_id_int)

            await callback.answer(await _(account_id, "answer_sent_successfully"))
            await show_next_review(callback, state, action="next")
        else:
            await callback.answer(await _(account_id, "error_sending_answer"))

@router.callback_query(Form.viewing_review_details, F.data == "back_to_list")
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    reviews_per_page = data.get("reviews_per_page", 5)
    all_reviews = data.get("all_reviews", [])
    review_type = data.get("review_type", "unanswered")
    current_page = data.get("current_page", 0)

    start_idx = current_page * reviews_per_page
    end_idx = start_idx + reviews_per_page
    reviews = all_reviews[start_idx:end_idx]
    total_pages = (len(all_reviews) + reviews_per_page - 1) // reviews_per_page

    rating_counts = Counter(r["rating"] for r in all_reviews)
    rating_summary = "\n".join([f"{i}⭐️: {rating_counts.get(i, 0)}" for i in range(1, 6)])

    translated_type = await _(account_id, "answered" if review_type == "answered" else "unanswered")
    response = await _(account_id, "reviews_list_title", type=translated_type, rating_summary=rating_summary)

    await callback.message.edit_text(response, reply_markup=await reviews_list_ikb(reviews, current_page, total_pages))
    await state.update_data(current_page=current_page, total_pages=total_pages)
    await state.set_state(Form.waiting_for_reviews_list)
    await callback.answer()

@router.callback_query(Form.viewing_review_details, F.data.startswith(("next_review_", "prev_review_")))
async def handle_navigate_review(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    if callback.data.startswith("next_review_"):
        direction = 1
        review_id = callback.data.split("_", maxsplit=2)[-1]
    else:
        direction = -1
        review_id = callback.data.split("_", maxsplit=2)[-1]

    data = await state.get_data()
    all_reviews = data.get("all_reviews", [])
    review_type = data.get("review_type", "unanswered")
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        current_idx = next((i for i, r in enumerate(all_reviews) if r["id"] == review_id), -1)
        if current_idx == -1:
            logging.error(f"Review {review_id} not found")
            await callback.message.edit_text(
                await _(account_id, "review_not_found"),
                reply_markup=await reviews_menu_ikb(account_id)
            )
            await state.set_state(Form.waiting_for_reviews_action)
            return

        new_idx = current_idx + direction

        if new_idx < 0:
            await callback.answer(await _(account_id, "no_previous_reviews"))
            return
        elif new_idx >= len(all_reviews):
            message_text, kb = await render_reviews_info(account_id, store_details, store_id)
            await callback.message.edit_text(
                message_text,
                reply_markup=kb
            )
            await state.set_state(Form.waiting_for_reviews_action)
            await callback.answer(await _(account_id, "no_more_reviews"))
            return

        selected_review = all_reviews[new_idx]

        if (review_type == "answered" and not selected_review.get("answer")
                and store_details["type"].lower() == "ozon"):
            comments = await get_review_comments(
                client_id=store_details.get("client_id", ""),
                api_key=store_details["api_key"],
                review_id=selected_review["id"],
                platform=store_details["type"],
                limit=20,
            )
            official = next(
                (c for c in comments if c.get("is_official") or c.get("is_owner")), None
            )
            selected_review["answer"] = official.get("text", "") if official else ""
            all_reviews[new_idx]["answer"] = selected_review["answer"]
            await state.update_data(all_reviews=all_reviews)

        base_product_name = selected_review.get("product_name", await _(account_id, "unknown_product"))
        supplier_article = selected_review.get("supplierArticle", "")
        product_name = f"{base_product_name} ({supplier_article})" if supplier_article and supplier_article != "N/A" else base_product_name
        sku = selected_review.get("nmId", selected_review.get("sku", await _(account_id, "sku_not_available")))
        offer_id = selected_review.get("offer_id")
        product_id = selected_review.get("product_id")
        user_name = selected_review.get("user_name", "")
        user_display = f"👤 {user_name}\n\n" if user_name and store_details["type"].lower() == "wildberries" else ""

        if store_details["type"].lower() == "wildberries":
            product_display = f'<a href="https://www.wildberries.ru/catalog/{sku}/detail.aspx">{html.escape(product_name)}</a>'
        elif store_details["type"].lower() == "ozon":
            product_display = f'<a href="https://www.ozon.ru/product/{sku}">{html.escape(product_name)}</a>'
        else:
            product_display = product_name

        mode = store_details.get("modes", {}).get(str(selected_review['rating']), "manual")
        suggested_reply = None

        if mode == "semi" and review_type == "unanswered":
            await callback.message.delete()
            generating_msg = await callback.message.answer("🤖 Генерируется ответ ИИ...")

            try:
                async with AsyncDatabase() as db:
                    store_settings = await db.get_store_settings(store_details.get("store_id"))

                    generate_reply_kwargs = {
                        "review_text": selected_review['text'],
                        "rating": selected_review['rating'],
                        "client_config": {
                            "client_id": store_details.get("client_id", ""),
                            "api_key": store_details.get("api_key", ""),
                            "platform": store_details.get("type", "Ozon")
                        },
                        "store_settings": store_settings
                    }

                    if store_details['type'].lower() == "wildberries":
                        generate_reply_kwargs.update({
                            "product_name": product_name,
                            "supplier_article": supplier_article,
                            "sku": sku,
                            "pros": selected_review.get("pros", ""),
                            "cons": selected_review.get("cons", "")
                        })

                    if store_details['type'].lower() == "ozon":
                        generate_reply_kwargs.update({
                            "product_name": product_name,
                            "sku": sku,
                            "offer_id": offer_id,
                            "product_id": product_id
                        })

                    suggested_reply = await generate_reply(**generate_reply_kwargs)
                await generating_msg.delete()
            except Exception as e:
                logging.error(f"Error generating AI reply: {str(e)}")
                await generating_msg.delete()
                error_msg = await callback.message.answer(await _(account_id, "error_generating_reply"))
                await asyncio.sleep(2)
                await error_msg.delete()
                suggested_reply = await _(account_id, "error_reply_placeholder")

            await state.update_data(suggested_reply=suggested_reply)

        date = selected_review["created_at"].strftime("%d.%m.%Y")
        stars = f"{selected_review['rating']}⭐️"
        text = selected_review.get("text", "")
        sku_label = "Артикул" if store_details["type"].lower() == "wildberries" else "SKU"

        template_text = text
        if store_details["type"].lower() == "wildberries":
            pros = selected_review.get("pros", "")
            cons = selected_review.get("cons", "")
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
            answer = selected_review.get("answer", "")
            clean_answer = html.unescape(str(answer)).strip()
            if clean_answer:
                response += "\n\n" + await _(account_id, "store_reply", answer=clean_answer)
            else:
                response += "\n\n" + await _(account_id, "no_store_reply")

        if mode == "semi" and review_type == "unanswered" and suggested_reply:
            response += "\n\n" + await _(account_id, "suggested_reply", reply_text=suggested_reply)

        response += "\n\n" + await _(
            account_id,
            "review_counter",
            current=new_idx + 1,
            total=len(all_reviews),
        )

        if review_type == "unanswered":
            keyboard = await review_mode_ikb(
                account_id=account_id,
                mode=mode,
                review_id=str(selected_review["id"]),
                current_index=new_idx,
                total_reviews=len(all_reviews),
            )
        else:
            keyboard = await review_details_ikb(
                account_id,
                selected_review["id"],
                review_type,
                new_idx,
                len(all_reviews),
            )

        if mode == "semi" and review_type == "unanswered":
            await callback.message.answer(response, reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.message.edit_text(response, reply_markup=keyboard, parse_mode="HTML")

        await state.update_data(current_review_index=new_idx, current_review_id=selected_review["id"])
        await callback.answer()

@router.callback_query(Form.viewing_review_details, F.data == "reply_review")
async def handle_reply_review(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    logging.info(f"Обработка reply_review для пользователя {account_id}, данные callback: {callback.data}")
    current_state = await state.get_state()
    logging.info(f"Текущее состояние: {current_state}")

    data = await state.get_data()
    current_index = data.get("current_review_index")
    reviews = data.get("all_reviews", [])
    logging.info(f"Текущий индекс: {current_index}, Длина списка отзывов: {len(reviews)}")

    if current_index >= len(reviews):
        logging.error(f"Неверный индекс отзыва: {current_index}")
        await callback.answer(await _(account_id, "review_not_found"), show_alert=True)
        return

    review = reviews[current_index]
    logging.info(f"Обработка отзыва ID: {review['id']}")

    review_text = review.get('text', '')
    if not review_text or not review_text.strip():
        review_text = await _(account_id, "no_review_text")
        logging.info(f"Отзыв без текста, используем заглушку: {review_text}")

    if not isinstance(review['rating'], int):
        logging.error(f"Некорректный рейтинг отзыва: rating={review['rating']}")
        await callback.answer(await _(account_id, "invalid_review_data"), show_alert=True)
        return

    try:
        prompt = await _(account_id, "enter_reply_text")
    except Exception as e:
        logging.error(f"Ошибка перевода для 'enter_reply_text': {str(e)}")
        prompt = "Пожалуйста, введите текст ответа:"

    try:
        await callback.message.answer(
            prompt,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=await _(account_id, "cancel"), callback_data="cancel_input")]
            ])
        )
        logging.info(f"Запрос на ввод ответа отправлен для пользователя {account_id}")
    except Exception as e:
        logging.error(f"Не удалось отправить запрос на ввод ответа: {str(e)}")
        await callback.answer(await _(account_id, "error_sending_message"), show_alert=True)
        return

    await state.set_state(Form.waiting_for_reply_text)
    await callback.answer()

@router.callback_query(Form.waiting_for_review_action, F.data == "back_to_review")
async def back_to_review(callback: CallbackQuery, state: FSMContext):
    await show_review_details(callback, state)
    await callback.answer()

@router.callback_query(Form.confirming_reply, F.data == "back_to_review")
async def handle_back_to_review(callback: CallbackQuery, state: FSMContext):
    await show_review_details(callback, state)
    await callback.answer()

@router.callback_query(Form.waiting_for_reviews_list, F.data.startswith("review_"))
async def handle_review_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    review_id = callback.data.split("_")[1]
    logging.info(f"User {account_id} selected review_id={review_id}")

    data = await state.get_data()
    all_reviews = data.get("all_reviews", [])
    review_type = data.get("review_type", "unanswered")
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)

    selected_review = next((r for r in all_reviews if r["id"] == review_id), None)
    if not selected_review:
        logging.error(f"Review {review_id} not found")
        await callback.answer(await _(account_id, "review_not_found"), show_alert=True)
        return

    base_product_name = selected_review.get("product_name", await _(account_id, "unknown_product"))
    supplier_article = selected_review.get("supplierArticle", "")
    product_name = f"{base_product_name} ({supplier_article})" if supplier_article and supplier_article != "N/A" else base_product_name
    sku = selected_review.get("nmId", selected_review.get("sku", await _(account_id, "sku_not_available")))
    offer_id = selected_review.get("offer_id")
    product_id = selected_review.get("product_id")
    user_name = selected_review.get("user_name", "")
    user_display = f"👤 {user_name}\n\n" if user_name and store_details["type"].lower() == "wildberries" else ""

    if store_details["type"].lower() == "wildberries":
        product_display = f'<a href="https://www.wildberries.ru/catalog/{sku}/detail.aspx">{html.escape(product_name)}</a>'
    elif store_details["type"].lower() == "ozon":
        product_display = f'<a href="https://www.ozon.ru/product/{sku}">{html.escape(product_name)}</a>'
    else:
        product_display = product_name

    if review_type == "answered" and not selected_review.get("answer") and store_details["type"].lower() == "ozon":
        comments = await get_review_comments(
            client_id=store_details.get("client_id", ""),
            api_key=store_details["api_key"],
            review_id=review_id,
            platform=store_details["type"],
            limit=20
        )
        official_comment = next(
            (comment for comment in comments if comment.get("is_official", False) or comment.get("is_owner", False)),
            None
        )
        selected_review["answer"] = official_comment.get("text", "") if official_comment else ""

    mode = store_details.get("modes", {}).get(str(selected_review['rating']), "manual")
    current_index = all_reviews.index(selected_review)

    if mode == "semi" and review_type == "unanswered":
        await callback.message.delete()
        generating_msg = await callback.message.answer("🤖 Генерируется ответ ИИ...")

        try:
            async with AsyncDatabase() as db:
                store_settings = await db.get_store_settings(store_details.get("store_id"))

                generate_reply_kwargs = {
                    "review_text": selected_review['text'],
                    "rating": selected_review['rating'],
                    "client_config": {
                        "client_id": store_details.get("client_id", ""),
                        "api_key": store_details.get("api_key", ""),
                        "platform": store_details.get("type", "Ozon")
                    },
                    "store_settings": store_settings
                }

                if store_details['type'].lower() == "wildberries":
                    generate_reply_kwargs.update({
                        "product_name": product_name,
                        "supplier_article": supplier_article,
                        "sku": sku,
                        "pros": selected_review.get("pros", ""),
                        "cons": selected_review.get("cons", "")
                    })

                if store_details['type'].lower() == "ozon":
                    generate_reply_kwargs.update({
                        "product_name": product_name,
                        "sku": sku,
                        "offer_id": offer_id,
                        "product_id": product_id
                    })

                suggested_reply = await generate_reply(**generate_reply_kwargs)
            await generating_msg.delete()
        except Exception as e:
            logging.error(f"Error generating AI reply: {str(e)}")
            await generating_msg.delete()
            await callback.message.answer(await _(account_id, "error_generating_reply"))
            suggested_reply = await _(account_id, "error_reply_placeholder")

        await state.update_data(suggested_reply=suggested_reply)

        date = selected_review["created_at"].strftime("%d.%m.%Y")
        stars = f"{selected_review['rating']}⭐️"
        text = selected_review.get("text", "")
        sku_label = "Артикул" if store_details["type"].lower() == "wildberries" else "SKU"

        template_text = text
        if store_details["type"].lower() == "wildberries":
            pros = selected_review.get("pros", "")
            cons = selected_review.get("cons", "")
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
                               text=template_text or "(нет текста)")
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

        response += "\n\n" + await _(account_id, "suggested_reply", reply_text=suggested_reply)
        response += "\n\n" + await _(account_id, "review_counter", current=current_index + 1, total=len(all_reviews))

        keyboard = await review_mode_ikb(
            account_id=account_id, mode=mode, review_id=str(selected_review["id"]),
            current_index=current_index, total_reviews=len(all_reviews)
        )

        await callback.message.answer(response, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        await state.update_data(current_review_id=review_id, current_review_index=current_index)
        await state.set_state(Form.viewing_review_details)

    else:
        date = selected_review["created_at"].strftime("%d.%m.%Y")
        stars = f"{selected_review['rating']}⭐️"
        text = selected_review.get("text", "")

        sku_label = "Артикул" if store_details["type"].lower() == "wildberries" else "SKU"

        template_text = text
        if store_details["type"].lower() == "wildberries":
            pros = selected_review.get("pros", "")
            cons = selected_review.get("cons", "")
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
                               text=template_text or "(нет текста)")
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

        if review_type == "answered" and selected_review.get("answer"):
            clean_answer = html.unescape(str(selected_review["answer"])).strip()
            response += "\n\n" + await _(account_id, "store_reply", answer=clean_answer)
        elif review_type == "answered":
            response += "\n\n" + await _(account_id, "no_store_reply")

        response += "\n\n" + await _(account_id, "review_counter", current=current_index + 1, total=len(all_reviews))

        keyboard = await review_mode_ikb(
            account_id=account_id, mode=mode, review_id=str(selected_review["id"]),
            current_index=current_index, total_reviews=len(all_reviews)
        ) if review_type == "unanswered" else await review_details_ikb(
            account_id, selected_review["id"], review_type, current_index, len(all_reviews)
        )

        await callback.message.edit_text(response, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
        await state.update_data(current_review_id=review_id, current_review_index=current_index)
        await state.set_state(Form.viewing_review_details)

    await callback.answer()

@router.callback_query(
    StateFilter(
        Form.waiting_for_rating_to_change_mode,
        Form.waiting_for_mode_selection,
        Form.waiting_for_reviews_list,
        Form.waiting_for_reviews_type_selection
    ),
    F.data.in_(["back_to_reviews_menu", "back_to_types", "back_to_reviews_work"])
)
async def back_to_reviews_menu(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        message_text, kb = await render_reviews_info(account_id, store, store_id)
        await edit_or_reply(callback, message_text, kb)
        await state.set_state(Form.waiting_for_reviews_action)
        await callback.answer()

@router.callback_query(
    StateFilter(Form.confirming_reply, Form.waiting_for_reply_text),
    F.data.in_(["cancel_send", "cancel_input"])
)
async def handle_cancel_action(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    try:
        await callback.message.delete()
    except:
        pass

    await show_review_details(callback, state)

    current_state = await state.get_state()
    action_type = "reply" if current_state == Form.confirming_reply else "input"
    await callback.answer(await _(account_id, f"{action_type}_cancelled"))

@router.callback_query(
    StateFilter(Form.viewing_review_details),
    F.data.startswith(("send_ai_reply_", "send_by_template_"))
)
async def handle_send_predefined_reply(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    if callback.data.startswith("send_ai_reply_"):
        reply_type = "ai"
        review_id = callback.data.split("_", maxsplit=3)[-1]
    else:
        reply_type = "template"
        review_id = callback.data.split("_", maxsplit=3)[-1]

    data = await state.get_data()
    current_review_id = data.get("current_review_id")

    if review_id != current_review_id:
        await callback.answer(await _(account_id, "review_mismatch"), show_alert=True)
        return

    store_id = data.get("selected_store_id")
    current_index = data.get("current_review_index")
    reviews = data.get("all_reviews", [])

    if current_index >= len(reviews):
        await callback.answer(await _(account_id, "review_not_found"), show_alert=True)
        return

    review = reviews[current_index]

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        # Получаем текст ответа в зависимости от типа
        if reply_type == "ai":
            reply_text = data.get("suggested_reply")
            if not reply_text:
                await callback.answer(await _(account_id, "no_suggested_reply"), show_alert=True)
                return
        else:  # template
            templates = store_details.get("templates", {})
            rating = str(review['rating'])
            reply_text = templates.get(rating)
            if not reply_text:
                await callback.answer(await _(account_id, "no_template_for_rating", rating=rating), show_alert=True)
                return

        success = await send_review_answer(store_details, review_id, reply_text)
        if success:
            # Уменьшаем счетчик неотвеченных отзывов в кеше
            store_id_int = int(store_id)
            await store_cache.decrement_review_count(store_id_int)

            await callback.answer(await _(account_id, "answer_sent_successfully"), show_alert=False)
            await back_to_list(callback, state)
        else:
            await callback.answer(await _(account_id, "error_sending_answer"), show_alert=True)

@router.callback_query(
    StateFilter(Form.waiting_for_reviews_type_selection, Form.waiting_for_reviews_action),
    F.data.startswith("reviews_")
)
async def handle_reviews_type_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    review_type = callback.data.split("_")[1]

    logging.info(f"User {account_id} selected review_type={review_type}, store_id={store_id}")

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        answered = (review_type == "answered")
        reviews = await get_store_reviews(store_details, answered=answered, limit=100)
        reviews_per_page = 5
        total_pages = (len(reviews) + reviews_per_page - 1) // reviews_per_page

        if not reviews:
            translated_type = await _(account_id, "answered" if answered else "unanswered")
            await edit_or_reply(
                callback,
                await _(account_id, "no_reviews_found", type=translated_type),
                reply_markup=await reviews_menu_ikb(account_id, store_id)
            )
            await state.set_state(Form.waiting_for_reviews_action)
            await callback.answer()
            return

        rating_counts = Counter(review["rating"] for review in reviews)
        rating_summary = "\n".join([f"{i}⭐️: {rating_counts.get(i, 0)}" for i in range(1, 6)])
        translated_type = await _(account_id, "answered" if answered else "unanswered")
        response = await _(account_id, "reviews_list_title", type=translated_type, rating_summary=rating_summary)

        await state.update_data(
            all_reviews=reviews,
            current_page=0,
            reviews_per_page=reviews_per_page,
            total_pages=total_pages,
            review_type=review_type
        )

        await edit_or_reply(
            callback,
            response,
            reply_markup=await reviews_list_ikb(reviews[:reviews_per_page], 0, total_pages)
        )
        await state.set_state(Form.waiting_for_reviews_list)
        await callback.answer()