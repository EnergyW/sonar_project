import hashlib
import re
import asyncio
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from keyboards.kb_for_profiles import profile_ikb
from keyboards.kb_for_stores import main_menu_ikb
from i18n import _
from db.database import AsyncDatabase
from states.states import Form

router = Router()

@router.callback_query(F.data == "my_profile")
async def show_profile(callback: CallbackQuery):
    account_id = str(callback.from_user.id)

    async with AsyncDatabase() as db:
        user = await db.get_user(account_id)
        stores = await db.get_user_stores(account_id)
        employees = await db.get_employees_by_owner(account_id)

    phone = user["phone"] if user and user["phone"] else await _(account_id, "not_specified")
    store_count = len(stores)
    employee_count = len(employees)

    store_list = (
        "\n".join([f"- {store_name} ({store_type})" for store_id, store_name, store_type in stores])
        if stores else await _(account_id, "no_stores")
    )
    employee_list = (
        "\n".join([f"- {e['full_name']}" for e in employees])
        if employees else await _(account_id, "no_employees")
    )

    text = (
        f" *{await _(account_id, 'profile_title')}*\n\n"
        f" {await _(account_id, 'profile_phone')}: `{phone}`\n"
        f" {await _(account_id, 'profile_stores_count')}: *{store_count}*\n{store_list}\n\n"
        f" {await _(account_id, 'profile_employees_count')}: *{employee_count}*\n{employee_list}"
    )

    await callback.message.edit_text(
        text, parse_mode="Markdown", reply_markup=await profile_ikb(account_id)
    )

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    account_id = str(callback.from_user.id)
    await callback.message.edit_text(
        await _(account_id, "main_menu_text"),
        reply_markup=await main_menu_ikb(account_id)
    )
