from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from i18n import _
from db.database import AsyncDatabase

async def mode_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "mode_auto"), callback_data="mode_auto")],
            [InlineKeyboardButton(text=await _(account_id, "mode_semi"), callback_data="mode_semi")],
            [InlineKeyboardButton(text=await _(account_id, "mode_manual"), callback_data="mode_manual")],
            [InlineKeyboardButton(text=await _(account_id, "mode_template"), callback_data="mode_template")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_reviews_menu"), callback_data="back_to_reviews_menu")]
        ]
    )

async def reviews_menu_ikb(account_id: str, store_id: str) -> InlineKeyboardMarkup:
    store = {}
    if store_id:
        async with AsyncDatabase() as db:
            store = await db.get_store_details(store_id)

    is_enabled = store.get("reviews_enabled", False) if store else False

    toggle_text = (
        f"✅ {await _(account_id, 'auto_replies_enabled')}"
        if is_enabled
        else f"🚫 {await _(account_id, 'auto_replies_disabled')}"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "review_modes"), callback_data="review_modes")],
            [InlineKeyboardButton(text=toggle_text, callback_data="toggle_auto_reply")],
            [
                InlineKeyboardButton(text=await _(account_id, "answered"), callback_data="reviews_answered"),
                InlineKeyboardButton(text=await _(account_id, "unanswered"), callback_data="reviews_unanswered")
            ],
            [InlineKeyboardButton(text=await _(account_id, "manage_templates"), callback_data="manage_templates")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_store_from_reviews"),
                                  callback_data="back_to_store_from_reviews")]
        ]
    )

async def review_action_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "send_as_is"), callback_data="send_as_is")],
            [InlineKeyboardButton(text=await _(account_id, "edit_reply"), callback_data="edit_reply")],
            [InlineKeyboardButton(text=await _(account_id, "send_by_template"), callback_data="send_by_template")],
            [InlineKeyboardButton(text=await _(account_id, "skip_review"), callback_data="skip_review")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_store"), callback_data="back_to_store")]
        ]
    )

async def manual_reply_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "send_reply"), callback_data="send_reply")],
            [InlineKeyboardButton(text=await _(account_id, "skip_review"), callback_data="skip_review")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_store"), callback_data="back_to_store")]
        ]
    )

async def next_reviews_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "next_reviews"), callback_data="next_reviews")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_reviews_menu"), callback_data="back_to_reviews_menu")]
        ]
    )

async def reviews_list_ikb(reviews: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for review in reviews:
        date = review['created_at'].strftime("%d.%m.%Y")
        stars = f"{review['rating']}⭐️"
        text = review['text'][:20] + "..." if len(review['text']) > 20 else review['text']
        buttons.append([InlineKeyboardButton(
            text=f"{date} | {stars} | {text}",
            callback_data=f"review_{review['id']}"
        )])

    pagination = []
    if page > 0:
        pagination.append(InlineKeyboardButton(text="⬅️", callback_data="prev_reviews"))  # Изменено
    pagination.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))
    if page < total_pages - 1:
        pagination.append(InlineKeyboardButton(text="➡️", callback_data="next_reviews"))  # Изменено

    buttons.append(pagination)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_types")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def review_details_ikb(account_id: str, review_id: str, review_type: str, current_index: int,
                             total_reviews: int) -> InlineKeyboardMarkup:
    buttons = []

    if review_type == "unanswered":
        buttons.append([
            InlineKeyboardButton(
                text=await _(account_id, "manual_reply"),
                callback_data="reply_review"
            )
        ])

    navigation_buttons = []
    if current_index > 0:
        navigation_buttons.append(
            InlineKeyboardButton(
                text=await _(account_id, "prev_button"),
                callback_data=f"prev_review_{review_id}"
            )
        )
    if current_index < total_reviews - 1:
        navigation_buttons.append(
            InlineKeyboardButton(
                text=await _(account_id, "next_button"),
                callback_data=f"next_review_{review_id}"
            )
        )
    if navigation_buttons:
        buttons.append(navigation_buttons)

    buttons.append([
        InlineKeyboardButton(
            text=await _(account_id, "back_to_list_button"),
            callback_data="back_to_list"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def review_mode_ikb(account_id: str, mode: str, review_id: str, current_index: int,
                          total_reviews: int) -> InlineKeyboardMarkup:
    buttons = []

    if mode == "semi":
        buttons.append([
            InlineKeyboardButton(text=await _(account_id, "send_ai_reply"), callback_data=f"send_ai_reply_{review_id}"),
            InlineKeyboardButton(text=await _(account_id, "manual_reply"), callback_data="reply_review")
        ])
    elif mode == "manual":
        buttons.append([
            InlineKeyboardButton(text=await _(account_id, "manual_reply"), callback_data="reply_review")
        ])
    elif mode == "template":
        buttons.append([
            InlineKeyboardButton(text=await _(account_id, "send_by_template"),
                                 callback_data=f"send_by_template_{review_id}"),
            InlineKeyboardButton(text=await _(account_id, "manual_reply"), callback_data="reply_review")
        ])
    elif mode == "auto":
        buttons.append(
            [InlineKeyboardButton(text=await _(account_id, "skip_review"), callback_data=f"skip_review_{review_id}")])

    nav = []
    if current_index > 0:
        nav.append(InlineKeyboardButton(text=await _(account_id, "prev_button"), callback_data=f"prev_review_{review_id}"))
    if current_index < total_reviews - 1:
        nav.append(InlineKeyboardButton(text=await _(account_id, "next_button"), callback_data=f"next_review_{review_id}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text=await _(account_id, "back_to_list_button"), callback_data="back_to_list")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

