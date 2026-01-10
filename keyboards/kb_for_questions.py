from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import _
from db.database import AsyncDatabase
from dateutil.parser import isoparse
from datetime import datetime


async def questions_menu_ikb(account_id: str, store_id: str = None) -> InlineKeyboardMarkup:
    store = {}
    if store_id:
        async with AsyncDatabase() as db:
            store = await db.get_store_details(store_id)

    is_enabled = store.get("questions_enabled", False) if store else False

    toggle_text = (
        f"✅ {await _(account_id, 'auto_questions_enabled')}"
        if is_enabled
        else f"🚫 {await _(account_id, 'auto_questions_disabled')}"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "question_modes"), callback_data="question_modes")],
            [InlineKeyboardButton(text=toggle_text, callback_data="toggle_questions")],
            [
                InlineKeyboardButton(text=await _(account_id, "answered_questions"),
                                     callback_data="questions_answered"),
                InlineKeyboardButton(text=await _(account_id, "unanswered_questions"),
                                     callback_data="questions_unanswered")
            ],
            [InlineKeyboardButton(text=await _(account_id, "back_to_menu_from_questions"),
                                  callback_data="back_to_menu_from_questions")]
        ]
    )


async def question_action_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "send_as_is_question"),
                                  callback_data="send_as_is_question")],
            [InlineKeyboardButton(text=await _(account_id, "edit_question_reply"),
                                  callback_data="edit_question_reply")],
            [InlineKeyboardButton(text=await _(account_id, "skip_question"), callback_data="skip_question")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_store_question"),
                                  callback_data="back_to_store_question")]
        ]
    )


async def manual_question_reply_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "send_question_reply"),
                                  callback_data="send_question_reply")],
            [InlineKeyboardButton(text=await _(account_id, "skip_question"), callback_data="skip_question")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_store_question"),
                                  callback_data="back_to_store_question")]
        ]
    )


async def next_questions_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "next_questions"), callback_data="next_questions")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_questions_menu"),
                                  callback_data="back_to_questions_menu")]
        ]
    )


async def questions_list_ikb(account_id: str, questions: list, page: int, total_pages: int,
                             question_type: str) -> InlineKeyboardMarkup:
    buttons = []
    for question in questions:
        created_at = question.get('created_at', '')
        if isinstance(created_at, datetime):
            date = created_at.strftime('%d.%m.%Y')
        else:
            try:
                date = isoparse(created_at).strftime('%d.%m.%Y')
            except (ValueError, TypeError):
                date = "N/A"

        text = question['text'][:20] + "..." if len(question['text']) > 20 else question['text']

        buttons.append([InlineKeyboardButton(
            text=f"{date} | {text}",
            callback_data=f"vq_{str(question['id'])}"
        )])

    pagination = []
    if page > 0:
        pagination.append(InlineKeyboardButton(text="⬅️", callback_data=f"pp_{question_type}"))

    pagination.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        pagination.append(InlineKeyboardButton(text="➡️", callback_data=f"np_{question_type}"))

    if pagination:
        buttons.append(pagination)

    back_button_text = await _(account_id, "back_to_questions_menu")
    buttons.append([InlineKeyboardButton(text=back_button_text, callback_data="back_to_questions_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def mode_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "mode_auto"), callback_data="mode_auto")],
            [InlineKeyboardButton(text=await _(account_id, "mode_semi"), callback_data="mode_semi")],
            [InlineKeyboardButton(text=await _(account_id, "mode_manual"), callback_data="mode_manual")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_questions_menu"), callback_data="back_to_questions_menu")]
        ]
    )


async def single_question_ikb(
        account_id: str,
        question_id: str,
        question_type: str,
        questions_mode: str,
        question_index: int,
        total_questions: int,
        questions: list
) -> InlineKeyboardMarkup:
    keyboard = []

    nav_row = []
    if question_index > 0:
        prev_q = questions[question_index - 1]["id"]
        nav_row.append(InlineKeyboardButton(
            text=await _(account_id, "prev_button"),
            callback_data=f"vq_{prev_q}"
        ))

    if question_index + 1 < total_questions:
        next_q = questions[question_index + 1]["id"]
        nav_row.append(InlineKeyboardButton(
            text=await _(account_id, "next"),
            callback_data=f"vq_{next_q}"
        ))

    if nav_row:
        keyboard.append(nav_row)

    if question_type == "unanswered":
        action_row = []
        if questions_mode in ["semi", "auto"]:
            action_row.append(InlineKeyboardButton(
                text=await _(account_id, "send_ai_reply"),
                callback_data=f"sai_{question_id}"
            ))
        if questions_mode != "auto":
            action_row.append(InlineKeyboardButton(
                text=await _(account_id, "manual_reply"),
                callback_data=f"mr_{question_id}"
            ))
        if action_row:
            keyboard.append(action_row)

    keyboard.append([InlineKeyboardButton(
        text=await _(account_id, "back_to_list"),
        callback_data=f"bl_{question_type}"
    )])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)