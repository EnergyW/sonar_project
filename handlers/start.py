from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from keyboards.kb_for_start import language_choice_ikb, role_choice_ikb, request_phone_kb
from keyboards.kb_for_stores import main_menu_ikb, stores_list_ikb
from states.states import Form, LANGUAGE_CHOICES
from i18n import _
from db.database import AsyncDatabase
from i18n import i18n
import hashlib
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

router = Router()

def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("8"):
        digits = "7" + digits[1:]
    elif digits.startswith("7"):
        pass
    elif digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    elif digits.startswith("0"):
        digits = "7" + digits[1:]

    return digits

async def edit_or_reply(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)

@router.message(Form.waiting_for_phone, F.contact)
async def phone_received(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    account_id = str(message.from_user.id)
    data = await state.get_data()
    lang_code = data.get("chosen_language", "ru")

    phone_request_message_id = data.get("phone_request_message_id")

    if phone_request_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=phone_request_message_id)
        except:
            pass

    try:
        await message.delete()
    except:
        pass

    await state.update_data(phone=phone)

    async with AsyncDatabase() as db:
        existing_user = await db.get_user_by_phone(phone)

        if existing_user:
            role = existing_user.get("role")
            if role == "owner":
                await message.answer(
                    await _(account_id, "welcome_back"),
                    reply_markup=await main_menu_ikb(account_id, is_owner=True)
                )
                await state.clear()
            elif role == "employee":
                employee = await db.get_employee_by_phone_and_code(phone, "")
                if employee:
                    stores = await db.get_employee_stores(employee["employee_id"])
                    if not stores:
                        await message.answer(
                            await _(account_id, "no_stores_assigned"),
                            reply_markup=ReplyKeyboardRemove()
                        )
                        await state.clear()
                        return
                    await message.answer(
                        await _(account_id, "welcome_employee"),
                        reply_markup=await stores_list_ikb(account_id, stores)
                    )
                    await state.set_state(Form.waiting_for_store_selection)
                    await state.update_data(employee_id=employee["employee_id"])
        else:
            role = data.get("role", "owner")
            await db.create_user(account_id, phone, lang_code, role=role)

            if role == "owner":
                await message.answer(
                    await _(account_id, "main_menu"),
                    reply_markup=await main_menu_ikb(account_id, is_owner=True)
                )
                await state.clear()
            elif role == "employee":
                await message.answer(
                    await _(account_id, "enter_access_code"),
                    reply_markup=ReplyKeyboardRemove()
                )
                await state.set_state(Form.waiting_for_employee_code)

@router.message(Form.waiting_for_phone)
async def manual_phone_received(message: Message, state: FSMContext):
    raw_phone = message.text.strip()
    phone = normalize_phone(raw_phone)
    account_id = str(message.from_user.id)
    data = await state.get_data()
    lang_code = data.get("chosen_language", "ru")

    phone_request_message_id = data.get("phone_request_message_id")

    if phone_request_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=phone_request_message_id)
        except:
            pass

    try:
        await message.delete()
    except:
        pass

    if len(phone) != 11 or not phone.isdigit():
        await message.answer(await _(account_id, "invalid_phone_format"))
        return

    async with AsyncDatabase() as db:
        existing_user = await db.get_user_by_phone(phone)

    if existing_user:
        await state.update_data(phone=phone)
        role = existing_user.get("role")

        if role == "owner":
            await message.answer(
                await _(account_id, "welcome_back"),
                reply_markup=await main_menu_ikb(account_id, is_owner=True)
            )
            await state.clear()
        elif role == "employee":
            async with AsyncDatabase() as db:
                employee = await db.get_employee_by_phone_and_code(phone, "")
                if employee:
                    stores = await db.get_employee_stores(employee["employee_id"])
                    if not stores:
                        await message.answer(
                            await _(account_id, "no_stores_assigned"),
                            reply_markup=ReplyKeyboardRemove()
                        )
                        await state.clear()
                        return
                    await message.answer(
                        await _(account_id, "welcome_employee"),
                        reply_markup=await stores_list_ikb(account_id, stores)
                    )
                    await state.set_state(Form.waiting_for_store_selection)
                    await state.update_data(employee_id=employee["employee_id"])
    else:
        await state.update_data(phone=phone)
        await message.answer(
            await _(account_id, "choose_role"),
            reply_markup=await role_choice_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_role)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)

    async with AsyncDatabase() as db:
        user = await db.get_user(account_id)

    if not user:
        await message.answer(
            await _(account_id, "choose_language", state=state),
            reply_markup=await language_choice_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_language)
        return

    if not user.get("phone"):
        lang_code = user.get("lang", "ru")
        phone_message = await message.answer(
            await _(account_id, "enter_phone_to_login"),
            reply_markup=await request_phone_kb(account_id, lang_code)
        )
        await state.update_data(phone_request_message_id=phone_message.message_id)
        await state.set_state(Form.waiting_for_phone)
        return

    role = user.get("role")
    if role == "owner":
        await message.answer(
            await _(account_id, "welcome_back"),
            reply_markup=await main_menu_ikb(account_id, is_owner=True)
        )
        await state.clear()
    elif role == "employee":
        async with AsyncDatabase() as db:
            employee = await db.get_employee_by_phone_and_code(user.get("phone", ""), "")
            if employee:
                stores = await db.get_employee_stores(employee["employee_id"])
                if not stores:
                    await message.answer(
                        await _(account_id, "no_stores_assigned"),
                        reply_markup=ReplyKeyboardRemove()
                    )
                    await state.clear()
                    return
                await message.answer(
                    await _(account_id, "welcome_employee"),
                    reply_markup=await stores_list_ikb(account_id, stores)
                )
                await state.set_state(Form.waiting_for_store_selection)
                await state.update_data(employee_id=employee["employee_id"])
            else:
                lang_code = user.get("lang", "ru")
                phone_message = await message.answer(
                    await _(account_id, "enter_employee_phone"),
                    reply_markup=await request_phone_kb(account_id, lang_code)
                )
                await state.update_data(phone_request_message_id=phone_message.message_id)
                await state.set_state(Form.waiting_for_employee_phone)
    else:
        await message.answer(
            await _(account_id, "choose_role"),
            reply_markup=await role_choice_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_role)

@router.callback_query(F.data == "change_language")
async def change_language(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)

    await edit_or_reply(
        callback,
        await _(account_id, "choose_language"),
        reply_markup=await language_choice_ikb(account_id)
    )
    await state.set_state(Form.waiting_for_language)
    await callback.answer()

@router.callback_query(Form.waiting_for_language, F.data.startswith("set_lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    lang_code = callback.data.split("_")[2]

    if lang_code not in LANGUAGE_CHOICES:
        await callback.answer(await _(account_id, "unsupported_language"))
        return

    translator = i18n.get_translator(lang_code)
    lang_name = translator.gettext(f"language_{lang_code}")

    await state.update_data(chosen_language=lang_code)

    async with AsyncDatabase() as db:
        await db.update_user_language(account_id, lang_code)
        user = await db.get_user(account_id)

    await callback.message.delete()

    if user and user.get("role"):
        role = user.get("role")
        if role == "owner":
            await callback.message.answer(
                await _(account_id, "welcome_back"),
                reply_markup=await main_menu_ikb(account_id, is_owner=True)
            )
        else:
            async with AsyncDatabase() as db:
                employee = await db.get_employee_by_phone_and_code(user.get("phone", ""), "")
                if employee:
                    stores = await db.get_employee_stores(employee["employee_id"])
                    if not stores:
                        await callback.message.answer(
                            await _(account_id, "no_stores_assigned"),
                            reply_markup=ReplyKeyboardRemove()
                        )
                    else:
                        await callback.message.answer(
                            await _(account_id, "welcome_employee"),
                            reply_markup=await stores_list_ikb(account_id, stores)
                        )
                        await state.set_state(Form.waiting_for_store_selection)
                        await state.update_data(employee_id=employee["employee_id"])
                else:
                    if not user.get("phone"):
                        phone_message = await callback.message.answer(
                            await _(account_id, "enter_phone_to_login"),
                            reply_markup=await request_phone_kb(account_id, lang_code)
                        )
                        await state.update_data(phone_request_message_id=phone_message.message_id)
                        await state.set_state(Form.waiting_for_phone)
                    else:
                        phone_message = await callback.message.answer(
                            await _(account_id, "enter_employee_phone"),
                            reply_markup=await request_phone_kb(account_id, lang_code)
                        )
                        await state.update_data(phone_request_message_id=phone_message.message_id)
                        await state.set_state(Form.waiting_for_employee_phone)
        await state.clear()
    else:
        phone_message = await callback.message.answer(
            await _(account_id, "enter_phone_to_login"),
            reply_markup=await request_phone_kb(account_id, lang_code)
        )
        await state.update_data(phone_request_message_id=phone_message.message_id)
        await state.set_state(Form.waiting_for_phone)

    await callback.answer()

@router.callback_query(Form.waiting_for_role, F.data.in_(["role_owner", "role_employee"]))
async def set_role(callback: CallbackQuery, state: FSMContext):
    account_id = str(callback.from_user.id)
    role = callback.data
    db_role = "owner" if role == "role_owner" else "employee"

    await callback.message.delete()

    data = await state.get_data()
    phone = data.get("phone")
    lang_code = data.get("chosen_language", "ru")

    async with AsyncDatabase() as db:
        existing_user = await db.get_user(account_id)

        if not existing_user:
            await db.create_user(account_id, phone, lang_code, role=db_role)
        else:
            await db.update_user_role(account_id, db_role)

    await state.update_data(role=db_role)

    if db_role == "owner":
        await callback.message.answer(
            await _(account_id, "welcome_back"),
            reply_markup=await main_menu_ikb(account_id, is_owner=True)
        )
        await state.clear()
    else:
        if not phone:
            phone_message = await callback.message.answer(
                await _(account_id, "enter_phone_to_login"),
                reply_markup=await request_phone_kb(account_id, lang_code)
            )
            await state.update_data(phone_request_message_id=phone_message.message_id)
            await state.set_state(Form.waiting_for_phone)
        else:
            await callback.message.answer(
                await _(account_id, "enter_access_code"),
                reply_markup=ReplyKeyboardRemove()
            )
            await state.set_state(Form.waiting_for_employee_code)

@router.message(Form.waiting_for_employee_phone, F.contact)
async def employee_phone_contact_received(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    account_id = str(message.from_user.id)

    phone_request_message_id = (await state.get_data()).get("phone_request_message_id")
    if phone_request_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=phone_request_message_id)
        except:
            pass

    try:
        await message.delete()
    except:
        pass

    await state.update_data(employee_phone=phone)
    await message.answer(
        await _(account_id, "enter_access_code"),
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_for_employee_code)

@router.message(Form.waiting_for_employee_phone)
async def employee_phone_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    phone = message.text.strip()

    phone_request_message_id = (await state.get_data()).get("phone_request_message_id")
    if phone_request_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=phone_request_message_id)
        except:
            pass

    await state.update_data(employee_phone=phone)
    await message.answer(
        await _(account_id, "enter_access_code"),
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_for_employee_code)

@router.message(Form.waiting_for_employee_code)
async def employee_code_received(message: Message, state: FSMContext):
    account_id = str(message.from_user.id)
    access_code = message.text.strip()
    data = await state.get_data()
    phone = data.get("employee_phone")

    async with AsyncDatabase() as db:
        employee = await db.get_employee_by_phone_and_code(phone, access_code)

    if not employee or not employee['is_active']:
        await message.answer(
            await _(account_id, "invalid_employee_credentials"),
            reply_markup=await role_choice_ikb(account_id)
        )
        await state.set_state(Form.waiting_for_role)
        return

    async with AsyncDatabase() as db:
        await db.update_user_role(account_id, "employee")
        stores = await db.get_employee_stores(employee['employee_id'])

    if not stores:
        await message.answer(
            await _(account_id, "no_stores_assigned"),
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return

    await state.update_data(employee_id=employee['employee_id'])
    await message.answer(
        await _(account_id, "welcome_employee"),
        reply_markup=await stores_list_ikb(account_id, stores)
    )
    await state.set_state(Form.waiting_for_store_selection)