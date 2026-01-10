from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from states.states import LANGUAGE_CHOICES
from i18n import i18n, _
from db.database import AsyncDatabase
import logging


async def language_choice_ikb(account_id: str) -> InlineKeyboardMarkup:
    async with AsyncDatabase() as db:
        user = await db.get_user(account_id)
        lang = "en" if not user else await db.get_user_language(account_id) or "en"

    logging.info(f"language_choice_ikb: account_id={account_id}, selected lang={lang}")

    kb = []
    for code in LANGUAGE_CHOICES:
        translation_key = LANGUAGE_CHOICES[code]
        translated_text = i18n.get_translator(lang).gettext(translation_key)
        logging.info(f"Language code={code}, key={translation_key}, translated_text={translated_text}")
        kb.append([InlineKeyboardButton(
            text=translated_text,
            callback_data=f"set_lang_{code}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=kb)


async def request_phone_kb(account_id: str, lang_code: str):
    translator = i18n.get_translator(lang_code)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(
            text=translator.gettext("send_phone_button"),
            request_contact=True
        )]],
        resize_keyboard=True
    )


async def role_choice_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "role_owner"), callback_data="role_owner")],
            [InlineKeyboardButton(text=await _(account_id, "role_employee"), callback_data="role_employee")]
        ]
    )