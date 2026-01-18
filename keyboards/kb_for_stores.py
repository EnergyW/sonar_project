from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import _
from db.database import AsyncDatabase
from states.states import stores

async def store_choice_ikb(account_id: str):
    kb = [
        [InlineKeyboardButton(text=await _(account_id, s), callback_data=f"store_{s}")]
        for s in stores
    ]
    kb.append([InlineKeyboardButton(text=await _(account_id, "back_to_main_menu"), callback_data="back_to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def main_menu_ikb(account_id: str, is_owner: bool = True):
    buttons = [
        [InlineKeyboardButton(text=await _(account_id, "my_profile_button"), callback_data="my_profile")],
        [InlineKeyboardButton(text=await _(account_id, "my_stores_button"), callback_data="my_stores")],
        [InlineKeyboardButton(text=await _(account_id, "support"), callback_data="support")],
    ]
    if is_owner:
        buttons.insert(2, [InlineKeyboardButton(text=await _(account_id, "my_employees"), callback_data="my_employees")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def store_action_ikb(account_id: str, is_owner: bool = True):
    buttons = [
        [InlineKeyboardButton(text=await _(account_id, "reviews_work"), callback_data="reviews_work")],
        [InlineKeyboardButton(text=await _(account_id, "questions_work"), callback_data="questions_work")],
        [InlineKeyboardButton(text=await _(account_id, "store_settings"), callback_data="store_settings")],
        [InlineKeyboardButton(text=await _(account_id, "back_to_stores_list"), callback_data="back_to_stores_list")]
    ]
    if is_owner:
        buttons.insert(0, [InlineKeyboardButton(text=await _(account_id, "edit_store"), callback_data="edit_store")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def edit_store_ikb(account_id: str, store_type: str):
    kb = [
        [
            InlineKeyboardButton(text=await _(account_id, "edit_name"), callback_data="edit_name"),
            InlineKeyboardButton(text=await _(account_id, "edit_api_key"), callback_data="edit_api_key")
        ],
        [InlineKeyboardButton(text=await _(account_id, "delete_store"), callback_data="delete_store")],
        [InlineKeyboardButton(text=await _(account_id, "back_in_edit_field"), callback_data="back_in_edit_field")]
    ]
    if store_type != "Wildberries":
        kb.insert(1, [InlineKeyboardButton(text=await _(account_id, "edit_client_id"), callback_data="edit_client_id")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def delete_confirmation_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=await _(account_id, "confirm_delete"), callback_data="confirm_delete"),
                InlineKeyboardButton(text=await _(account_id, "cancel_delete"), callback_data="cancel_delete")
            ]
        ]
    )

async def stores_list_ikb(account_id: str, stores: list, is_owner: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(
            text=await _(account_id, "store_item", store_name=store[1], store_type=store[2]),
            callback_data=f"select_store_{store[0]}"
        )]
        for store in stores
    ]
    if is_owner:
        kb.append([InlineKeyboardButton(text=await _(account_id, "add_store_button"), callback_data="add_store")])
    if stores or is_owner:
        kb.append([InlineKeyboardButton(text=await _(account_id, "back_to_main_menu"), callback_data="back_to_main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

async def back_only_ikb(account_id: str, callback_data: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=await _(account_id, "back"), callback_data=callback_data)]
    ])