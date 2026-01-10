import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_stores import store_choice_ikb, main_menu_ikb, stores_list_ikb, edit_store_ikb, \
    delete_confirmation_ikb, store_action_ikb, back_only_ikb
from states.states import Form
from i18n import _
from db.database import AsyncDatabase
from aiogram.filters import StateFilter
from utils.cache import store_cache
import time
import asyncio
from dotenv import load_dotenv

load_dotenv()
router = Router()

async def edit_or_reply(callback: CallbackQuery, text: str, reply_markup=None, state: FSMContext = None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        if state:
            await state.update_data(last_message_id=callback.message.message_id)
        return callback.message.message_id
    except Exception:
        new_message = await callback.message.answer(text, reply_markup=reply_markup)
        if state:
            await state.update_data(last_message_id=new_message.message_id)
        return new_message.message_id

@router.callback_query(F.data == "add_store")
async def add_store_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    account_id = str(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Error deleting message: {e}")

    msg = await callback.message.answer(
        await _(account_id, "choose_store_platform"),
        reply_markup=await store_choice_ikb(account_id)
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(Form.waiting_for_store_choice)
    await callback.answer()

@router.callback_query(Form.waiting_for_store_choice, F.data.startswith("store_"))
async def store_type_received(callback: CallbackQuery, state: FSMContext, bot: Bot):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    last_msg_id = data.get("last_message_id")

    try:
        await bot.delete_message(callback.message.chat.id, last_msg_id)
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")

    store_type = callback.data.replace("store_", "", 1)
    if store_type not in ["Ozon", "Wildberries", "Yandex Market"]:
        await callback.answer(await _(account_id, "invalid_store_type"))
        return

    await state.update_data(store_type=store_type)
    msg = await callback.message.answer(
        await _(account_id, "enter_store_name"),
        reply_markup=await back_only_ikb(account_id, "back_to_main_menu")
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(Form.waiting_for_store_name)
    await callback.answer()

@router.message(Form.waiting_for_store_name)
async def store_name_received(message: Message, state: FSMContext, bot: Bot):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    last_msg_id = data.get("last_message_id")

    try:
        await bot.delete_message(message.chat.id, last_msg_id)
        await message.delete()
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")

    await state.update_data(store_name=message.text.strip())
    msg = await message.answer(
        await _(account_id, "enter_api_key"),
        reply_markup=await back_only_ikb(account_id, "back_to_main_menu")
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(Form.waiting_for_store_api)

@router.message(Form.waiting_for_store_api)
async def store_api_received(message: Message, state: FSMContext, bot: Bot):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    last_msg_id = data.get("last_message_id")

    try:
        await bot.delete_message(message.chat.id, last_msg_id)
        await message.delete()
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")

    store_type = data["store_type"]
    api_key = message.text.strip()

    if store_type == "Wildberries":
        async with AsyncDatabase() as db:
            store_id = await db.create_store(account_id, data["store_name"], store_type, api_key)
        await message.answer(
            await _(account_id, "store_added", store_name=data['store_name'], store_type=store_type),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
    else:
        await state.update_data(api_key=api_key)
        msg = await message.answer(
            await _(account_id, "enter_client_id"),
            reply_markup=await back_only_ikb(account_id, "back_to_main_menu")
        )
        await state.update_data(last_message_id=msg.message_id)
        await state.set_state(Form.waiting_for_store_client_id)

@router.message(Form.waiting_for_store_client_id)
async def store_client_id_received(message: Message, state: FSMContext, bot: Bot):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    last_msg_id = data.get("last_message_id")

    try:
        await bot.delete_message(message.chat.id, last_msg_id)
        await message.delete()
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")

    store_type = data["store_type"]
    store_name = data["store_name"]
    api_key = data["api_key"]
    client_id = message.text.strip()

    try:
        client_id_str = str(client_id)
        async with AsyncDatabase() as db:
            store_id = await db.create_store(account_id, store_name, store_type, api_key, client_id_str)

        if store_id is None:
            await message.answer(
                await _(account_id, "store_creation_error"),
                reply_markup=await main_menu_ikb(account_id)
            )
            await state.clear()
            return

    except Exception as e:
        logging.error(f"Error creating store: {e}")
        await message.answer(
            await _(account_id, "store_creation_error"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    await message.answer(
        await _(account_id, "store_added", store_name=store_name, store_type=store_type),
        reply_markup=await main_menu_ikb(account_id)
    )
    await state.clear()

@router.callback_query(F.data == "my_stores")
async def show_my_stores(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        stores = await db.get_user_stores(account_id)

    data = await state.get_data()
    is_owner = data.get("role") != "role_employee"
    last_msg_id = data.get("last_message_id")

    if not stores:
        await edit_or_reply(
            callback,
            await _(account_id, "no_stores"),
            await stores_list_ikb(account_id, [], is_owner),
            await state.set_state(Form.waiting_for_store_selection)
        )
    else:
        stores_info_text = "🏪 " + await _(account_id, "stores_header") + "\n"
        stores_info_text += "────────────────\n"

        cache_tasks = []

        for store_tuple in stores:
            store_id = store_tuple[0]
            cache_tasks.append(store_cache.get_unanswered_counts(store_id))

        cache_results = await asyncio.gather(*cache_tasks, return_exceptions=True)

        for i, store_tuple in enumerate(stores):
            store_id = store_tuple[0]
            store_name = store_tuple[1]
            store_type = store_tuple[2]

            cache_data = cache_results[i]

            if isinstance(cache_data, Exception):
                logging.error(f"Error getting cache for store {store_id}: {cache_data}")
                unanswered_reviews = 0
                unanswered_questions = 0
            else:
                unanswered_reviews = cache_data.get("reviews", 0)
                unanswered_questions = cache_data.get("questions", 0)

            store_line = f"🔹 {store_name} ({store_type})\n\n"
            store_line += f"   ❓ {await _(account_id, 'questions')}: {unanswered_questions}    "
            store_line += f"📝 {await _(account_id, 'reviews')}: {unanswered_reviews}\n"
            store_line += "────────────────\n"
            stores_info_text += store_line

        final_text = stores_info_text + "\n\n" + await _(account_id, "choose_store")

        await edit_or_reply(
            callback,
            final_text,
            await stores_list_ikb(account_id, stores, is_owner),
            state
        )

    await state.set_state(Form.waiting_for_store_selection)
    await callback.answer()

@router.callback_query(Form.waiting_for_store_selection, F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    await edit_or_reply(
        callback,
        await _(account_id, "main_menu"),
        await main_menu_ikb(account_id)
    )
    await state.clear()
    await callback.answer()

async def render_store_edit_info(account_id: str, store: dict) -> tuple[str, InlineKeyboardMarkup]:
    status_text = await _(account_id, "enabled") if store.get("enabled", False) else await _(account_id, "disabled")
    questions_status = await _(account_id, "enabled") if store.get("questions_enabled", False) else await _(account_id,
                                                                                                         "disabled")
    notifications_status = await _(account_id, "enabled") if store.get("notifications_enabled", False) else await _(
        account_id, "disabled")

    store_data = {
        'store_name': store['store_name'],
        'store_type': store['type'],
        'status': status_text,
        'questions_status': questions_status,
        'api_key': store['api_key'],
        'client_id': (store['client_id']
                      if store.get('client_id') and store['type'] != "Wildberries"
                      else await _(account_id, "not_applicable"))
    }

    message_text = await _(account_id, "store_edit_info", **store_data)
    kb = await edit_store_ikb(account_id, store['type'])
    return message_text, kb

@router.message(Form.waiting_for_store_rename)
async def save_new_store_name(message: Message, state: FSMContext, bot: Bot):
    account_id = str(message.from_user.id)
    new_name = message.text.strip()
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    try:
        await message.delete()
    except Exception as e:
        logging.error(f"Error deleting user message: {e}")

    if not store_id:
        await bot.send_message(
            chat_id=message.chat.id,
            text=await _(account_id, "store_not_selected"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        await db.update_store_field(store_id, "store_name", new_name)
        store = await db.get_store_details(store_id)

    last_msg_id = data.get("last_message_id")

    try:
        message_text, kb = await render_store_edit_info(account_id, store)
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=last_msg_id,
            text=message_text,
            reply_markup=kb
        )
    except Exception as e:
        logging.error(f"Error editing message: {e}")
        new_msg = await bot.send_message(
            chat_id=message.chat.id,
            text=message_text,
            reply_markup=kb
        )
        await state.update_data(last_message_id=new_msg.message_id)

    await state.set_state(Form.waiting_for_store_edit_field)

@router.callback_query(Form.waiting_for_store_edit_field, F.data == "back_in_edit_field")
async def handle_back_in_edit_field(callback: CallbackQuery, state: FSMContext):
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

    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")

    await show_store_info(callback, state, account_id, store_id)
    await callback.answer()

@router.callback_query(Form.waiting_for_selected_store_action, F.data == "edit_store")
async def handle_edit_store(callback: CallbackQuery, state: FSMContext):
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

    message_text, kb = await render_store_edit_info(account_id, store)
    await edit_or_reply(callback, message_text, kb)
    await state.set_state(Form.waiting_for_store_edit_field)
    await callback.answer()

@router.callback_query(Form.waiting_for_store_edit_field,
                       F.data.in_(["edit_name", "edit_api_key", "edit_client_id", "delete_store"]))
async def store_edit_field(callback: CallbackQuery, state: FSMContext, bot: Bot):
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

    store_type = store["type"]
    current_message_id = callback.message.message_id

    if callback.data == "edit_name":
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=current_message_id,
            text=await _(account_id, "enter_new_store_name"),
            reply_markup=await back_only_ikb(account_id, "back_to_edit_field")
        )
        await state.update_data(last_message_id=current_message_id)
        await state.set_state(Form.waiting_for_store_rename)

    elif callback.data == "edit_api_key":
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=current_message_id,
            text=await _(account_id, "enter_new_api_key"),
            reply_markup=await back_only_ikb(account_id, "back_to_edit_field")
        )
        await state.update_data(last_message_id=current_message_id)
        await state.set_state(Form.waiting_for_store_edit_value)
        await state.update_data(field_to_edit="api_key")

    elif callback.data == "edit_client_id":
        if store_type == "Wildberries":
            await callback.answer(await _(account_id, "client_id_not_used"))
            return

        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=current_message_id,
            text=await _(account_id, "enter_new_client_id"),
            reply_markup=await back_only_ikb(account_id, "back_to_edit_field")
        )
        await state.update_data(last_message_id=current_message_id)
        await state.set_state(Form.waiting_for_store_edit_value)
        await state.update_data(field_to_edit="client_id")

    elif callback.data == "delete_store":
        await state.update_data(store_to_delete=store_id)
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=current_message_id,
            text=await _(account_id, "confirm_delete_store", store_name=store['store_name']),
            reply_markup=await delete_confirmation_ikb(account_id)
        )
        await state.update_data(last_message_id=current_message_id)
        await state.set_state(Form.waiting_for_confirm_delete)

    await callback.answer()

@router.message(Form.waiting_for_store_edit_value)
async def store_edit_value(message: Message, state: FSMContext, bot: Bot):
    account_id = str(message.from_user.id)
    value = message.text.strip()
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    field = data.get("field_to_edit")

    try:
        await message.delete()
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id - 1)
    except Exception as e:
        logging.error(f"Error deleting messages: {e}")

    if not store_id or not field:
        await message.answer(await _(account_id, "data_not_found"))
        await state.clear()
        return

    field_map = {
        "api_key": "api_key",
        "client_id": "client_id"
    }

    if field not in field_map:
        await message.answer(await _(account_id, "invalid_field"))
        return

    db_field = field_map[field]

    async with AsyncDatabase() as db:
        await db.update_store_field(store_id, db_field, value)
        store = await db.get_store_details(store_id)

    message_text, kb = await render_store_edit_info(account_id, store)
    await message.answer(message_text, reply_markup=kb)
    await state.set_state(Form.waiting_for_store_edit_field)

@router.callback_query(Form.waiting_for_store_selection, F.data.startswith("select_store_"))
async def handle_store_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    store_id = int(callback.data.split("_")[-1])
    await state.update_data(selected_store_id=store_id)
    data = await state.get_data()
    is_owner = data.get("role") != "role_employee"
    success = await show_store_info(callback, state, account_id, store_id, is_owner)
    if not success:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_found"),
            await main_menu_ikb(account_id)
        )
        await state.clear()

    await callback.answer()

async def show_store_info(callback: CallbackQuery, state: FSMContext, account_id: str, store_id: int,
                          is_owner: bool = True):
    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)

    if not store:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_found"),
            await main_menu_ikb(account_id)
        )
        await state.clear()
        return False

    reviews_status = await _(account_id, "reviews_enabled") if store["reviews_enabled"] else await _(account_id,
                                                                                                     "disabled")
    questions_status = await _(account_id, "enabled") if store["questions_enabled"] else await _(account_id, "disabled")
    modes_info = "\n".join(
        [await _(account_id, "mode_info", rating=rating, mode=await _(account_id, f"mode_{mode.lower()}"))
         for rating, mode in sorted(store["modes"].items(), key=lambda x: int(x[0]))]) if store[
        "modes"] else await _(account_id, "modes_not_set")

    cache_data = await store_cache.get_unanswered_counts(store_id)
    unanswered_reviews_count = cache_data["reviews"]
    unanswered_questions_count = cache_data["questions"]

    logging.info(
        f"📊 Using cached counts for store_id={store_id}: {unanswered_reviews_count} reviews, {unanswered_questions_count} questions")

    current_time = time.time()
    last_update = cache_data.get("last_full_update", 0)
    is_very_old_data = current_time - last_update > 300
    has_no_real_data = not cache_data.get("store_name")

    if (unanswered_reviews_count == 0 and unanswered_questions_count == 0 and
            (is_very_old_data or has_no_real_data)):

        loading_text = await _(account_id, "loading_store_data")
        temp_message = await callback.message.answer(loading_text)

        try:
            await store_cache.add_store(store_id)
            cache_data = await store_cache.get_unanswered_counts(store_id)
            unanswered_reviews_count = cache_data["reviews"]
            unanswered_questions_count = cache_data["questions"]

            logging.info(
                f"🔄 Synchronously updated store {store_id}: {unanswered_reviews_count} reviews, {unanswered_questions_count} questions")
        except Exception as e:
            logging.error(f"❌ Error during sync update for store {store_id}: {e}")
        finally:
            await temp_message.delete()

    info = await _(account_id, "store_info",
                   store_name=store['store_name'],
                   store_type=store['type'],
                   api_key=store['api_key'] if is_owner else "********",
                   client_id=store['client_id'] if store['type'] != "Wildberries" and is_owner else "N/A",
                   reviews_status=reviews_status,
                   modes_info=modes_info,
                   questions_status=questions_status,
                   questions_mode=await _(account_id, f"mode_{store['questions_mode'].lower()}"),
                   unanswered_reviews=unanswered_reviews_count,
                   unanswered_questions=unanswered_questions_count)

    await edit_or_reply(
        callback,
        info,
        await store_action_ikb(account_id, is_owner),
        state
    )
    await state.set_state(Form.waiting_for_selected_store_action)
    return True

@router.callback_query(Form.waiting_for_store_rename, F.data == "back_to_edit_field")
async def handle_back_from_rename(callback: CallbackQuery, state: FSMContext, bot: Bot):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    last_msg_id = data.get("last_message_id")
    if not store_id:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=last_msg_id,
            text=await _(account_id, "store_not_selected"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)

    if not store:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=last_msg_id,
            text=await _(account_id, "store_not_found"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    message_text, kb = await render_store_edit_info(account_id, store)
    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=last_msg_id,
        text=message_text,
        reply_markup=kb
    )
    await state.set_state(Form.waiting_for_store_edit_field)
    await callback.answer()

@router.callback_query(Form.waiting_for_store_edit_value, F.data == "back_to_edit_field")
async def handle_back_from_edit(callback: CallbackQuery, state: FSMContext, bot: Bot):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    try:
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")

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

    message_text, kb = await render_store_edit_info(account_id, store)
    await edit_or_reply(callback, message_text, kb)
    await state.set_state(Form.waiting_for_store_edit_field)
    await callback.answer()

@router.callback_query(Form.waiting_for_confirm_delete, F.data.in_(["confirm_delete", "cancel_delete"]))
async def handle_confirm_delete(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("store_to_delete")

    if callback.data == "confirm_delete":
        async with AsyncDatabase() as db:
            success = await db.delete_store(store_id)

        if success:
            await edit_or_reply(
                callback,
                await _(account_id, "store_deleted"),
                await main_menu_ikb(account_id)
            )
            await state.clear()
        else:
            await callback.message.answer(await _(account_id, "store_deletion_error"),
                                          reply_markup=await main_menu_ikb(account_id))
    else:
        async with AsyncDatabase() as db:
            store = await db.get_store_details(store_id)

        if store:
            message_text, kb = await render_store_edit_info(account_id, store)
            await edit_or_reply(callback, message_text, kb)
            await state.set_state(Form.waiting_for_store_edit_field)
    await callback.answer()

@router.callback_query(Form.waiting_for_selected_store_action, F.data == "back_to_stores_list")
async def handle_back_to_stores_list(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        stores = await db.get_user_stores(account_id)

    data = await state.get_data()
    is_owner = data.get("role") != "role_employee"

    if not stores:
        await edit_or_reply(
            callback,
            await _(account_id, "no_stores"),
            await stores_list_ikb(account_id, [], is_owner),
            state
        )
    else:
        stores_info_text = "🏪 " + await _(account_id, "stores_header") + "\n"
        stores_info_text += "────────────────\n"

        cache_tasks = []
        for store_tuple in stores:
            store_id = store_tuple[0]
            cache_tasks.append(store_cache.get_unanswered_counts(store_id))

        cache_results = await asyncio.gather(*cache_tasks, return_exceptions=True)

        for i, store_tuple in enumerate(stores):
            store_id = store_tuple[0]
            store_name = store_tuple[1]
            store_type = store_tuple[2]

            cache_data = cache_results[i]

            if isinstance(cache_data, Exception):
                logging.error(f"Error getting cache for store {store_id}: {cache_data}")
                unanswered_reviews = 0
                unanswered_questions = 0
            else:
                unanswered_reviews = cache_data.get("reviews", 0)
                unanswered_questions = cache_data.get("questions", 0)

            store_line = f"🔹 {store_name} ({store_type})\n\n"
            store_line += f"   ❓ Вопросы: {unanswered_questions}    "
            store_line += f"📝 Отзывы: {unanswered_reviews}\n"
            store_line += "────────────────\n"
            stores_info_text += store_line

        final_text = stores_info_text + "\n\n" + await _(account_id, "choose_store")

        await edit_or_reply(
            callback,
            final_text,
            await stores_list_ikb(account_id, stores, is_owner),
            state
        )

    await state.set_state(Form.waiting_for_store_selection)
    await callback.answer()

@router.callback_query(Form.waiting_for_store_choice, F.data == "back_to_main_menu")
async def back_to_main_menu_from_store_choice(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    await edit_or_reply(
        callback,
        await _(account_id, "main_menu"),
        await main_menu_ikb(account_id)
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "back_to_main_menu", StateFilter(
    Form.waiting_for_store_name,
    Form.waiting_for_store_api,
    Form.waiting_for_store_client_id
))
async def back_to_main_menu_from_input_states(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    await edit_or_reply(
        callback,
        await _(account_id, "main_menu"),
        await main_menu_ikb(account_id),
        state
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "support")
async def support_callback(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    support_text = await _(account_id, "support_text")
    button_text = await _(account_id, "contact_developer")
    back_text = await _(account_id, "back_to_menu_button")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=button_text,
                url="https://t.me/SonarSup"
            )],
            [InlineKeyboardButton(
                text=back_text,
                callback_data="back_to_main_menu"
            )]
        ]
    )

    await edit_or_reply(
        callback,
        support_text,
        keyboard,
        state
    )

    await state.set_state(Form.in_support_menu)
    await callback.answer()

@router.callback_query(Form.in_support_menu, F.data == "back_to_main_menu")
async def back_from_support(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    await edit_or_reply(
        callback,
        await _(account_id, "main_menu"),
        await main_menu_ikb(account_id)
    )
    await state.clear()
    await callback.answer()