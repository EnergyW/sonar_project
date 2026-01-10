from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import _

async def back_only_ikb(account_id: str, callback_data: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=await _(account_id, "back"), callback_data=callback_data)]
    ])

async def employee_action_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "edit_employee"), callback_data="edit_employee")],
            [InlineKeyboardButton(text=await _(account_id, "delete_employee"), callback_data="delete_employee")],
            [InlineKeyboardButton(text=await _(account_id, "toggle_employee_status"), callback_data="toggle_employee_status")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_employees"), callback_data="back_to_employees")]
        ]
    )

async def employees_list_ikb(account_id: str, employees: list):
    kb = [
        [InlineKeyboardButton(
            text=await _(account_id, "employee_item", full_name=emp['full_name'], is_active=await _(account_id, "enabled" if emp['is_active'] else "disabled")),
            callback_data=f"select_employee_{emp['employee_id']}"
        )]
        for emp in employees
    ]
    kb.append([InlineKeyboardButton(text=await _(account_id, "add_employee"), callback_data="add_employee")])
    kb.append([InlineKeyboardButton(text=await _(account_id, "back_to_main_menu"), callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def employee_edit_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "edit_employee_name"), callback_data="edit_employee_name")],
            [InlineKeyboardButton(text=await _(account_id, "edit_employee_phone"), callback_data="edit_employee_phone")],
            [InlineKeyboardButton(text=await _(account_id, "edit_employee_code"), callback_data="edit_employee_code")],
            [InlineKeyboardButton(text=await _(account_id, "edit_employee_stores"), callback_data="edit_employee_stores")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_employee"), callback_data="back_to_employee")]
        ]
    )

async def employee_store_selection_ikb(account_id: str, stores: list, selected_stores: list = None):
    selected = set(selected_stores or [])
    kb = [
        [InlineKeyboardButton(
            text=f"{'✅ ' if store[0] in selected else ''}{await _(account_id, 'store_item', store_name=store[1], store_type=store[2])}",
            callback_data=f"toggle_store_{store[0]}"
        )]
        for store in stores
    ]
    kb.append([InlineKeyboardButton(text=await _(account_id, "select_all_stores"), callback_data="select_all_stores")])
    kb.append([InlineKeyboardButton(text=await _(account_id, "confirm_store_selection"), callback_data="confirm_store_selection")])
    kb.append([InlineKeyboardButton(text=await _(account_id, "back_to_employee_action"), callback_data="back_to_employee_action")])
    return InlineKeyboardMarkup(inline_keyboard=kb)