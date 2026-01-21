import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_store_settings import rating_ikb, templates_list_ikb, template_actions_ikb, cancel_template_ikb, \
    advanced_settings_ikb, response_length_ikb, delivery_method_ikb, \
    tone_ikb, back_to_advanced_ikb, address_style_ikb,  stop_words_actions_ikb, minus_words_actions_ikb, \
    clear_stop_words_confirm_ikb, clear_minus_words_confirm_ikb
from keyboards.kb_for_stores import main_menu_ikb, store_action_ikb
from states.states import Form
from i18n import _
from db.database import AsyncDatabase
import json

logger = logging.getLogger(__name__)
router = Router()

async def edit_or_reply(callback: CallbackQuery, text: str, reply_markup=None) -> Message:
    try:
        await callback.message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete message: {e}")

    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
        return callback.message
    except Exception:
        new_message = await callback.message.answer(text, reply_markup=reply_markup)
        return new_message

async def render_reviews_info(account_id: str, store: dict, store_id: str) -> tuple[str, InlineKeyboardMarkup]:
    try:
        reviews_status = await _(account_id, "enabled") if store.get("enabled", False) else await _(account_id,
                                                                                                    "disabled")
        modes = store.get("modes", {})
        modes_text = ""
        for i in range(1, 6):
            mode = modes.get(str(i), "mode_not_set")
            translated_mode = await _(account_id, f"mode_{mode.lower()}" if mode in ["auto", "semi", "manual",
                                                                                     "template"] else "mode_not_set")
            modes_text += await _(account_id, "mode_info", rating=i, mode=translated_mode) + "\n"

        message_text = await _(account_id, "reviews_info",
                               reviews_status=reviews_status,
                               modes_info=modes_text.strip(),
                               unanswered_count=0)
        from keyboards.kb_for_reviews import reviews_menu_ikb
        kb = await reviews_menu_ikb(account_id, store_id)
        return message_text, kb
    except Exception as e:
        logging.error(f"Error in render_reviews_info for account_id={account_id}, store_id={store_id}: {str(e)}")
        return await _(account_id, "error_processing"), await main_menu_ikb(account_id)

@router.callback_query(Form.waiting_for_reviews_action, F.data == "manage_templates")
async def manage_templates(callback: CallbackQuery, state: FSMContext):
    await refresh_templates_list(callback, state)
    await callback.answer()

@router.callback_query(Form.waiting_for_template_rating_selection, F.data.startswith("template_rate_"))
async def select_template_rating(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    rating = int(callback.data.split("_")[-1])
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        templates = store.get("templates", {})
        template = templates.get(str(rating))

    if template:
        text = await _(account_id, "current_template_for_rating", rating=rating, template=template)
        kb = await template_actions_ikb(account_id, rating)
        await state.set_state(Form.viewing_template_details)
        message = await edit_or_reply(callback, text, reply_markup=kb)
    else:
        text = await _(account_id, "enter_template_for_rating", rating=rating)
        kb = await cancel_template_ikb(account_id)
        await state.update_data(selected_rating=rating)
        await state.set_state(Form.waiting_for_template_text)
        message = await edit_or_reply(callback, text, reply_markup=kb)

        await state.update_data(template_request_message_id=message.message_id)

    await callback.answer()

@router.callback_query(Form.viewing_template_details, F.data.startswith("edit_template_"))
async def edit_template(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    rating = int(callback.data.split("_")[-1])

    await state.update_data(selected_rating=rating)
    message = await edit_or_reply(
        callback,
        await _(account_id, "enter_new_template", rating=rating),
        reply_markup=await cancel_template_ikb(account_id)
    )

    await state.update_data(template_request_message_id=message.message_id)

    await state.set_state(Form.waiting_for_template_text)
    await callback.answer()

@router.callback_query(Form.viewing_template_details, F.data.startswith("delete_template_"))
async def delete_template(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    rating = int(callback.data.split("_")[-1])
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        await db.update_store_template(store_id, rating, None)

    display_text = f"⚙️ {await _(account_id, 'template_deleted', rating=rating)}"
    await callback.answer(display_text, show_alert=False)
    await refresh_templates_list(callback, state)

@router.callback_query(Form.waiting_for_rating_to_change_template, F.data.startswith("rate_"))
async def handle_rating_for_template(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    rating = int(callback.data.split("_")[1])
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    if not store_id:
        display_text = f"⚙️ {await _(account_id, 'store_not_selected')}"
        await callback.answer(display_text, show_alert=True)
        return

    await state.update_data(selected_rating=rating)
    message = await edit_or_reply(
        callback,
        await _(account_id, "enter_template_for_rating", rating=rating),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "cancel"), callback_data="back_to_templates_menu")]
        ])
    )

    await state.update_data(template_request_message_id=message.message_id)

    await state.set_state(Form.waiting_for_template_text)
    await callback.answer()

@router.message(Form.waiting_for_template_text)
async def handle_template_text(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    rating = data.get("selected_rating")
    store_id = data.get("selected_store_id")
    template_text = message.text.strip()

    if not store_id or not rating:
        await message.answer(await _(account_id, "error_processing"))
        return

    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete user message: {e}")

    async with AsyncDatabase() as db:
        await db.update_store_template(store_id, rating, template_text)

    try:
        state_data = await state.get_data()
        request_message_id = state_data.get("template_request_message_id")
        if request_message_id:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=request_message_id)
    except Exception as e:
        logging.warning(f"Failed to delete bot request message: {e}")

    await refresh_templates_list(message, state)

@router.callback_query(F.data == "back_to_template_list")
async def back_to_template_list(callback: CallbackQuery, state: FSMContext):
    await manage_templates(callback, state)
    await callback.answer()

@router.callback_query(Form.waiting_for_rating_to_change_template, F.data == "back_to_reviews_menu")
async def back_from_template_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")
    if not store_id:
        await edit_or_reply(
            callback,
            await _(account_id, "store_not_selected"),
            reply_markup=await main_menu_ikb(account_id)
        )
        await state.clear()
        return

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await edit_or_reply(
                callback,
                await _(account_id, "store_not_found"),
                reply_markup=await main_menu_ikb(account_id)
            )
            await state.clear()
            return

        message_text, kb = await render_reviews_info(account_id, store, store_id)
        await edit_or_reply(callback, message_text, kb)
        await state.set_state(Form.waiting_for_reviews_action)
        await callback.answer()

@router.callback_query(Form.waiting_for_template_text, F.data == "back_to_templates_menu")
async def back_from_template_text(callback: CallbackQuery, state: FSMContext):
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

        templates = store.get("templates", {})
        text = await _(account_id, "current_templates") + "\n\n"
        for i in range(1, 6):
            template = templates.get(str(i), await _(account_id, "template_not_set"))
            text += await _(account_id, "template_info", rating=i, template=template) + "\n"

        await edit_or_reply(callback, text, reply_markup=await rating_ikb(account_id))
        await state.set_state(Form.waiting_for_rating_to_change_template)
        await callback.answer()

@router.callback_query(Form.waiting_for_template_rating_selection, F.data == "back_to_reviews_menu")
async def back_to_reviews_menu_from_templates(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)

    message_text, kb = await render_reviews_info(account_id, store, store_id)
    await edit_or_reply(callback, message_text, kb)
    await state.set_state(Form.waiting_for_reviews_action)
    await callback.answer()

async def refresh_templates_list(target, state: FSMContext):
    account_id = str(target.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        if not store:
            await target.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        templates = store.get("templates", {}) or {}
        text = await _(account_id, "current_templates_header") + "\n\n"

        for i in range(1, 6):
            raw_template = templates.get(str(i))
            template = (raw_template or "").strip() if raw_template is not None else ""

            if template:
                preview = (template[:47] + "...") if len(template) > 50 else template
                text += await _(account_id, "template_preview_line", rating=i, preview=preview) + "\n"
            else:
                text += await _(account_id, "template_not_set_line", rating=i) + "\n"

        kb = await templates_list_ikb(account_id)

        if isinstance(target, Message):
            await target.answer(text, reply_markup=kb)
        else:
            await edit_or_reply(target, text, reply_markup=kb)

        await state.set_state(Form.waiting_for_template_rating_selection)

@router.callback_query(F.data == "store_settings")
async def show_store_settings(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        store_type = store_details.get('type')
        client_config = store_details.get("client_config", {})

        platform = None

        if client_config:
            if isinstance(client_config, dict):
                platform = client_config.get("platform")
            else:
                try:
                    import json
                    if isinstance(client_config, str):
                        client_config_dict = json.loads(client_config)
                        platform = client_config_dict.get("platform")
                except Exception as e:
                    logging.error(f"Failed to parse client_config: {e}")

        if not platform:
            platform = store_type

        if platform:
            platform = str(platform).lower()
        else:
            platform = ""

        settings = await db.get_store_settings(store_id)

    if not settings:
        await callback.answer(await _(account_id, "error_loading_settings"), show_alert=True)
        return

    kb = await advanced_settings_ikb(account_id, settings, platform)
    await edit_or_reply(callback, await _(account_id, "advanced_settings_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "advanced_settings")
async def show_advanced_settings(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await callback.answer(await _(account_id, "store_not_found"), show_alert=True)
            return

        logging.info(f"store_details for store_id={store_id}: {store_details}")
        logging.info(f"store_details keys: {store_details.keys()}")

        store_type = store_details.get('type')
        client_config = store_details.get("client_config", {})

        logging.info(f"store_type from 'type' field: {store_type}")
        logging.info(f"client_config: {client_config}")

        platform = None

        if client_config:
            if isinstance(client_config, dict):
                platform = client_config.get("platform")
            else:
                try:
                    if isinstance(client_config, str):
                        client_config_dict = json.loads(client_config)
                        platform = client_config_dict.get("platform")
                except Exception as e:
                    logging.error(f"Failed to parse client_config: {e}")

        if not platform:
            platform = store_type

        if platform:
            platform = str(platform).lower()
        else:
            platform = ""

        logging.info(f"Final platform value: {platform}")

        settings = await db.get_store_settings(store_id)

    if not settings:
        await callback.answer(await _(account_id, "error_loading_settings"), show_alert=True)
        return

    kb = await advanced_settings_ikb(account_id, settings, platform)
    await edit_or_reply(callback, await _(account_id, "advanced_settings_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_boolean_setting(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    setting_type = callback.data.replace("toggle_", "")

    setting_map = {
        'use_name': 'use_name',
        'mention_product': 'mention_product',
        'use_emojis': 'use_emojis'
    }

    if setting_type not in setting_map:
        await callback.answer(await _(account_id, "unknown_setting"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        if settings:
            current_value = settings.get(setting_map[setting_type], True)
            await db.update_store_settings_field(store_id, setting_map[setting_type], not current_value)

    await show_advanced_settings(callback, state)
    await callback.answer()

@router.callback_query(F.data == "set_address_style")
async def set_address_style_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    kb = await address_style_ikb(account_id)
    await edit_or_reply(callback, await _(account_id, "address_style_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("address_style:"))
async def handle_address_style_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data_parts = callback.data.split(":")
    style = data_parts[1]
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_settings_field(store_id, 'address_style', style)

    await show_advanced_settings(callback, state)

    style_names = {
        'formal': await _(account_id, "address_formal"),
        'lowercase': await _(account_id, "address_lowercase"),
        'informal': await _(account_id, "address_informal")
    }
    style_display = style_names.get(style, style)

    await callback.answer(await _(account_id, "address_style_set", style=style_display))

@router.callback_query(F.data == "set_response_length")
async def set_response_length_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    kb = await response_length_ikb(account_id)
    await edit_or_reply(callback, await _(account_id, "response_length_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("response_length:"))
async def handle_response_length_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data_parts = callback.data.split(":")
    length = data_parts[1]
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_settings_field(store_id, 'response_length', length)

    await show_advanced_settings(callback, state)
    await callback.answer(await _(account_id, "response_length_set", length=length))

@router.callback_query(F.data == "set_delivery_method")
async def set_delivery_method_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    kb = await delivery_method_ikb(account_id)
    await edit_or_reply(callback, await _(account_id, "delivery_method_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("delivery_method:"))
async def handle_delivery_method_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data_parts = callback.data.split(":")
    method = data_parts[1]
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_settings_field(store_id, 'delivery_method', method)

    await show_advanced_settings(callback, state)
    await callback.answer(await _(account_id, "delivery_method_set", method=method))

@router.callback_query(F.data == "set_tone")
async def set_tone_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    kb = await tone_ikb(account_id)
    await edit_or_reply(callback, await _(account_id, "tone_header"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("tone:"))
async def handle_tone_selection(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data_parts = callback.data.split(":")
    tone = data_parts[1]
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_settings_field(store_id, 'tone', tone)

    await show_advanced_settings(callback, state)
    await callback.answer(await _(account_id, "tone_set", tone=tone))

@router.callback_query(F.data == "edit_stop_words")
async def edit_stop_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        stop_words = settings.get('stop_words', [])

    count = len(stop_words)
    words_list = ", ".join(stop_words) if stop_words else ""

    if stop_words:
        message_text = await _(account_id, "stop_words_list", count=count, words_list=words_list)
    else:
        message_text = await _(account_id, "stop_words_empty")

    kb = await stop_words_actions_ikb(account_id, has_words=bool(stop_words))

    await edit_or_reply(callback, message_text, reply_markup=kb)
    await state.update_data(editing_stop_words=store_id)
    await callback.answer()

@router.callback_query(F.data == "add_stop_words")
async def add_stop_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await back_to_advanced_ikb(account_id)
    message = await edit_or_reply(
        callback,
        await _(account_id, "add_stop_words_instruction"),
        reply_markup=kb
    )

    await state.update_data(
        stop_words_message_id=message.message_id,
        stop_words_action="add"
    )
    await state.set_state(Form.waiting_for_stop_words)
    await callback.answer()

@router.callback_query(F.data == "remove_stop_words")
async def remove_stop_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await back_to_advanced_ikb(account_id)
    message = await edit_or_reply(
        callback,
        await _(account_id, "remove_stop_words_instruction"),
        reply_markup=kb
    )

    await state.update_data(
        stop_words_message_id=message.message_id,
        stop_words_action="remove"
    )
    await state.set_state(Form.waiting_for_stop_words)
    await callback.answer()

@router.callback_query(F.data == "clear_stop_words")
async def clear_stop_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await clear_stop_words_confirm_ikb(account_id)
    await edit_or_reply(
        callback,
        await _(account_id, "clear_stop_words_confirm"),
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == "clear_stop_words_confirmed")
async def clear_stop_words_confirmed_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("editing_stop_words")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_array_setting(store_id, 'stop_words', [])

    await callback.answer(await _(account_id, "stop_words_cleared"))

    await state.update_data(selected_store_id=store_id)
    await edit_stop_words_handler(callback, state)

@router.callback_query(F.data == "edit_minus_words")
async def edit_minus_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("selected_store_id")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        minus_words = settings.get("minus_words", [])

    count = len(minus_words)
    words_list = ", ".join(minus_words) if minus_words else ""

    if minus_words:
        message_text = await _(account_id, "minus_words_list", count=count, words_list=words_list)
    else:
        message_text = await _(account_id, "minus_words_empty")

    kb = await minus_words_actions_ikb(account_id, has_words=bool(minus_words))

    await edit_or_reply(callback, message_text, reply_markup=kb)
    await state.update_data(editing_minus_words=store_id)
    await callback.answer()

@router.callback_query(F.data == "add_minus_words")
async def add_minus_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await back_to_advanced_ikb(account_id)
    message = await edit_or_reply(
        callback,
        await _(account_id, "add_minus_words_instruction"),
        reply_markup=kb
    )

    await state.update_data(
        minus_words_message_id=message.message_id,
        minus_words_action="add"
    )
    await state.set_state(Form.waiting_for_minus_words)
    await callback.answer()

@router.callback_query(F.data == "remove_minus_words")
async def remove_minus_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await back_to_advanced_ikb(account_id)
    message = await edit_or_reply(
        callback,
        await _(account_id, "remove_minus_words_instruction"),
        reply_markup=kb
    )

    await state.update_data(
        minus_words_message_id=message.message_id,
        minus_words_action="remove"
    )
    await state.set_state(Form.waiting_for_minus_words)
    await callback.answer()

@router.callback_query(F.data == "clear_minus_words")
async def clear_minus_words_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    kb = await clear_minus_words_confirm_ikb(account_id)
    await edit_or_reply(
        callback,
        await _(account_id, "clear_minus_words_confirm"),
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == "clear_minus_words_confirmed")
async def clear_minus_words_confirmed_handler(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    data = await state.get_data()
    store_id = data.get("editing_minus_words")

    if not store_id:
        await callback.answer(await _(account_id, "store_not_selected"), show_alert=True)
        return

    async with AsyncDatabase() as db:
        await db.update_store_array_setting(store_id, "minus_words", [])

    await callback.answer(await _(account_id, "minus_words_cleared"))

    await state.update_data(selected_store_id=store_id)
    await edit_minus_words_handler(callback, state)

@router.message(Form.waiting_for_stop_words)
async def handle_stop_words_input(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    store_id = data.get("editing_stop_words")
    stop_words_message_id = data.get("stop_words_message_id")
    action = data.get("stop_words_action", "add")

    if not store_id:
        await message.answer(await _(account_id, "error_processing"))
        return

    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete user message: {e}")

    if stop_words_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=stop_words_message_id)
        except Exception as e:
            logging.warning(f"Failed to delete bot instruction message: {e}")

    input_words = [word.strip().lower() for word in message.text.split(",") if word.strip()]

    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        current_words = settings.get('stop_words', [])

        if action == "add":
            updated_words = list(set(current_words + input_words))
        elif action == "remove":
            updated_words = [w for w in current_words if w not in input_words]
        else:
            updated_words = input_words

        await db.update_store_array_setting(store_id, 'stop_words', updated_words)

    count = len(updated_words)
    words_list = ", ".join(updated_words) if updated_words else ""

    success_message = await message.answer(
        await _(account_id, "stop_words_success", count=count, words_list=words_list or await _(account_id, "empty"))
    )

    await state.update_data(selected_store_id=store_id, editing_stop_words=store_id)
    await state.set_state(None)

    try:
        await success_message.delete()
    except Exception as e:
        logging.warning(f"Failed to delete success message: {e}")

    await show_stop_words_menu_after_edit(message, account_id, store_id, state)

@router.message(Form.waiting_for_minus_words)
async def handle_minus_words_input(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    data = await state.get_data()
    store_id = data.get("editing_minus_words")
    instruction_id = data.get("minus_words_message_id")
    action = data.get("minus_words_action", "add")

    if not store_id:
        await state.clear()
        return

    try:
        await message.delete()
    except:
        pass

    if instruction_id:
        try:
            await message.bot.delete_message(message.chat.id, instruction_id)
        except:
            pass

    input_words = [word.strip().lower() for word in message.text.split(",") if word.strip()]

    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        current_words = settings.get("minus_words", [])

        if action == "add":
            updated_words = list(set(current_words + input_words))
        elif action == "remove":
            updated_words = [w for w in current_words if w not in input_words]
        else:
            updated_words = input_words

        await db.update_store_array_setting(store_id, "minus_words", updated_words)

    count = len(updated_words)
    words_list = ", ".join(updated_words) if updated_words else ""

    success_message = await message.answer(
        await _(account_id, "minus_words_success", count=count, words_list=words_list or await _(account_id, "empty"))
    )

    await state.update_data(selected_store_id=store_id, editing_minus_words=store_id)
    await state.set_state(None)

    try:
        await success_message.delete()
    except:
        pass

    await show_minus_words_menu_after_edit(message, account_id, store_id, state)

async def show_stop_words_menu_after_edit(message: Message, account_id: str, store_id: int, state: FSMContext):
    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        stop_words = settings.get('stop_words', [])

    count = len(stop_words)
    words_list = ", ".join(stop_words) if stop_words else ""

    if stop_words:
        message_text = await _(account_id, "stop_words_list", count=count, words_list=words_list)
    else:
        message_text = await _(account_id, "stop_words_empty")

    kb = await stop_words_actions_ikb(account_id, has_words=bool(stop_words))

    await message.answer(message_text, reply_markup=kb)
    await state.update_data(editing_stop_words=store_id)

async def show_minus_words_menu_after_edit(message: Message, account_id: str, store_id: int, state: FSMContext):
    async with AsyncDatabase() as db:
        settings = await db.get_store_settings(store_id)
        minus_words = settings.get("minus_words", [])

    count = len(minus_words)
    words_list = ", ".join(minus_words) if minus_words else ""

    if minus_words:
        message_text = await _(account_id, "minus_words_list", count=count, words_list=words_list)
    else:
        message_text = await _(account_id, "minus_words_empty")

    kb = await minus_words_actions_ikb(account_id, has_words=bool(minus_words))

    await message.answer(message_text, reply_markup=kb)
    await state.update_data(editing_minus_words=store_id)

async def show_advanced_settings_after_edit(message: Message, account_id: str, store_id: int):
    async with AsyncDatabase() as db:
        store_details = await db.get_store_details(store_id)
        if not store_details:
            await message.answer(await _(account_id, "store_not_found"))
            return

        store_type = store_details.get('type')
        client_config = store_details.get("client_config", {})

        platform = None

        if client_config:
            if isinstance(client_config, dict):
                platform = client_config.get("platform")
            else:
                try:
                    import json
                    if isinstance(client_config, str):
                        client_config_dict = json.loads(client_config)
                        platform = client_config_dict.get("platform")
                except Exception as e:
                    logging.error(f"Failed to parse client_config: {e}")

        if not platform:
            platform = store_type

        if platform:
            platform = str(platform).lower()
        else:
            platform = ""

        settings = await db.get_store_settings(store_id)

    kb = await advanced_settings_ikb(account_id, settings, platform)
    await message.answer(await _(account_id, "advanced_settings_header"), reply_markup=kb)

@router.callback_query(F.data == "back_to_store")
async def back_to_store_from_settings(callback: CallbackQuery, state: FSMContext):
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

            reviews_status = await _(account_id, "reviews_enabled") if store_details.get("reviews_enabled",
                                                                                         False) else await _(account_id,
                                                                                                             "disabled")
            questions_status = await _(account_id, "enabled") if store_details.get("questions_enabled",
                                                                                   False) else await _(account_id,
                                                                                                       "disabled")

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

            from keyboards.kb_for_stores import store_action_ikb
            await callback.message.answer(
                info,
                reply_markup=await store_action_ikb(account_id, True)
            )
            await state.set_state(Form.waiting_for_selected_store_action)

    await callback.answer()