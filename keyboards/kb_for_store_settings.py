from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from i18n import _
from db.database import AsyncDatabase
import logger

async def templates_list_ikb(account_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=await _(account_id, "rating_button_1"),
                callback_data="template_rate_1"
            ),
            InlineKeyboardButton(
                text=await _(account_id, "rating_button_2"),
                callback_data="template_rate_2"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "rating_button_3"),
                callback_data="template_rate_3"
            ),
            InlineKeyboardButton(
                text=await _(account_id, "rating_button_4"),
                callback_data="template_rate_4"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "rating_button_5"),
                callback_data="template_rate_5"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "back_to_reviews_menu"),
                callback_data="back_to_reviews_menu"
            )
        ]
    ])

async def template_actions_ikb(account_id: str, rating: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=await _(account_id, "edit_template"),
                callback_data=f"edit_template_{rating}"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "delete_template"),
                callback_data=f"delete_template_{rating}"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "back"),
                callback_data="back_to_template_list"
            )
        ]
    ])

async def cancel_template_ikb(account_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=await _(account_id, "cancel"),
                callback_data="back_to_template_list"
            )
        ]
    ])

async def rating_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=await _(account_id, "star_1"), callback_data="rate_1"),
                InlineKeyboardButton(text=await _(account_id, "star_2"), callback_data="rate_2")
            ],
            [
                InlineKeyboardButton(text=await _(account_id, "star_3"), callback_data="rate_3"),
                InlineKeyboardButton(text=await _(account_id, "star_4"), callback_data="rate_4")
            ],
            [InlineKeyboardButton(text=await _(account_id, "star_5"), callback_data="rate_5")],
            [InlineKeyboardButton(text=await _(account_id, "back_to_reviews_menu"), callback_data="back_to_reviews_menu")]
        ]
    )

async def advanced_settings_ikb(account_id: str, settings: dict, platform: str = None):
    length_map = {
        'short': await _(account_id, 'response_length_short'),
        'default': await _(account_id, 'response_length_default'),
        'long': await _(account_id, 'response_length_long')
    }
    current_length = length_map.get(
        settings.get('response_length', 'default'),
        await _(account_id, 'response_length_default')
    )

    delivery_map = {
        'marketplace': await _(account_id, 'delivery_method_marketplace'),
        'self': await _(account_id, 'delivery_method_self')
    }
    current_delivery = delivery_map.get(
        settings.get('delivery_method', 'marketplace'),
        await _(account_id, 'delivery_method_marketplace')
    )

    tone_map = {
        'business': await _(account_id, 'tone_business'),
        'friendly': await _(account_id, 'tone_friendly'),
        'strict': await _(account_id, 'tone_strict')
    }
    current_tone = tone_map.get(
        settings.get('tone', 'friendly'),
        await _(account_id, 'tone_friendly')
    )

    address_map = {
        'formal': await _(account_id, 'address_formal'),  # на Вы
        'lowercase': await _(account_id, 'address_lowercase'),  # на вы
        'informal': await _(account_id, 'address_informal')  # на ты
    }
    current_address = address_map.get(
        settings.get('address_style', 'formal'),
        await _(account_id, 'address_formal')
    )

    yes_text = await _(account_id, "yes")
    no_text = await _(account_id, "no")

    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'address_style_setting')}: {current_address}",
                callback_data="set_address_style"
            )
        ]
    ]

    show_use_name = True
    if platform:
        platform_lower = str(platform).lower()
        if platform_lower == 'ozon':
            show_use_name = False

    if show_use_name:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{await _(account_id, 'use_name_setting')}: {yes_text if settings.get('use_name', True) else no_text}",
                    callback_data="toggle_use_name"
                )
            ]
        )

    keyboard.extend([
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'mention_product_setting')}: {yes_text if settings.get('mention_product', True) else no_text}",
                callback_data="toggle_mention_product"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'use_emojis_setting')}: {yes_text if settings.get('use_emojis', True) else no_text}",
                callback_data="toggle_use_emojis"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'response_length_setting')}: {current_length}",
                callback_data="set_response_length"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'delivery_method_setting')}: {current_delivery}",
                callback_data="set_delivery_method"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{await _(account_id, 'tone_setting')}: {current_tone}",
                callback_data="set_tone"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "stop_words_setting"),
                callback_data="edit_stop_words"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "minus_words_setting"),
                callback_data="edit_minus_words"
            )
        ],
        [
            InlineKeyboardButton(
                text=await _(account_id, "back"),
                callback_data="back_to_store"
            )
        ]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def response_length_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "response_length_short"),
                                  callback_data="response_length:short")],
            [InlineKeyboardButton(text=await _(account_id, "response_length_default"),
                                  callback_data="response_length:default")],
            [InlineKeyboardButton(text=await _(account_id, "response_length_long"),
                                  callback_data="response_length:long")],
            [InlineKeyboardButton(text=await _(account_id, "back"), callback_data="advanced_settings")]
        ]
    )

async def delivery_method_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "delivery_method_marketplace"),
                                  callback_data="delivery_method:marketplace")],
            [InlineKeyboardButton(text=await _(account_id, "delivery_method_self"),
                                  callback_data="delivery_method:self")],
            [InlineKeyboardButton(text=await _(account_id, "back"), callback_data="advanced_settings")]
        ]
    )

async def tone_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "tone_business"), callback_data="tone:business")],
            [InlineKeyboardButton(text=await _(account_id, "tone_friendly"), callback_data="tone:friendly")],
            [InlineKeyboardButton(text=await _(account_id, "tone_strict"), callback_data="tone:strict")],
            [InlineKeyboardButton(text=await _(account_id, "back"), callback_data="advanced_settings")]
        ]
    )

async def address_style_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "address_formal"), callback_data="address_style:formal")],
            [InlineKeyboardButton(text=await _(account_id, "address_lowercase"), callback_data="address_style:lowercase")],
            [InlineKeyboardButton(text=await _(account_id, "address_informal"), callback_data="address_style:informal")],
            [InlineKeyboardButton(text=await _(account_id, "back"), callback_data="advanced_settings")]
        ]
    )

async def back_to_advanced_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=await _(account_id, "back"), callback_data="advanced_settings")]
        ]
    )

async def stop_words_actions_ikb(account_id: str, has_words: bool = False):
    keyboard = [
        [
            InlineKeyboardButton(
                text=await _(account_id, "add_button"),
                callback_data="add_stop_words"
            )
        ]
    ]

    if has_words:
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text=await _(account_id, "remove_button"),
                    callback_data="remove_stop_words"
                )
            ],
            [
                InlineKeyboardButton(
                    text=await _(account_id, "clear_button"),
                    callback_data="clear_stop_words"
                )
            ]
        ])

    keyboard.append([
        InlineKeyboardButton(
            text=await _(account_id, "back"),
            callback_data="advanced_settings"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def minus_words_actions_ikb(account_id: str, has_words: bool = False):
    keyboard = [
        [
            InlineKeyboardButton(
                text=await _(account_id, "add_button"),
                callback_data="add_minus_words"
            )
        ]
    ]

    if has_words:
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text=await _(account_id, "remove_button"),
                    callback_data="remove_minus_words"
                )
            ],
            [
                InlineKeyboardButton(
                    text=await _(account_id, "clear_button"),
                    callback_data="clear_minus_words"
                )
            ]
        ])

    keyboard.append([
        InlineKeyboardButton(
            text=await _(account_id, "back"),
            callback_data="advanced_settings"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def clear_stop_words_confirm_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=await _(account_id, "confirm_clear"),
                    callback_data="clear_stop_words_confirmed"
                )
            ],
            [
                InlineKeyboardButton(
                    text=await _(account_id, "cancel"),
                    callback_data="edit_stop_words"
                )
            ]
        ]
    )

async def clear_minus_words_confirm_ikb(account_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=await _(account_id, "confirm_clear"),
                    callback_data="clear_minus_words_confirmed"
                )
            ],
            [
                InlineKeyboardButton(
                    text=await _(account_id, "cancel"),
                    callback_data="edit_minus_words"
                )
            ]
        ]
    )