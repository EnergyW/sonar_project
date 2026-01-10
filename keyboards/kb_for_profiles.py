from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import _

async def profile_ikb(account_id: str):
    buttons = [
        [InlineKeyboardButton(text=await _(account_id, "change_language"), callback_data="change_language")],
        [InlineKeyboardButton(text=await _(account_id, "back_to_menu_button"), callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


