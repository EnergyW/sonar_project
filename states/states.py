from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    waiting_for_login_password = State()
    waiting_for_password_confirmation = State()
    waiting_for_password = State()
    waiting_for_language = State()
    waiting_for_phone = State()
    waiting_for_store_choice = State()
    waiting_for_store_name = State()
    waiting_for_store_api = State()
    waiting_for_store_client_id = State()
    waiting_for_add_store_choice = State()
    waiting_for_store_removal = State()
    waiting_for_store_view = State()
    waiting_for_store_edit_choice = State()
    waiting_for_store_edit_field = State()
    waiting_for_store_edit_value = State()
    waiting_for_store_rename = State()
    waiting_for_selected_store_action = State()
    waiting_for_confirm_delete = State()
    waiting_for_rating_to_change_mode = State()
    waiting_for_mode_selection = State()
    waiting_for_reviews_action = State()
    waiting_for_questions_action = State()
    waiting_for_questions_mode = State()
    waiting_for_reviews_view = State()
    waiting_for_review_action = State()
    waiting_for_manual_reply = State()
    waiting_for_notification_action = State()
    notification_settings = State()
    choosing_frequency = State()
    choosing_urgent_threshold = State()
    setting_quiet_hours = State()
    waiting_for_store_selection = State()
    waiting_for_questions_view = State()
    waiting_for_question_action = State()
    waiting_for_manual_question_reply = State()
    waiting_for_role = State()
    waiting_for_employee_phone = State()
    waiting_for_employee_code = State()
    waiting_for_employee_action = State()
    waiting_for_employee_name = State()
    waiting_for_employee_phone_input = State()
    waiting_for_employee_code_input = State()
    waiting_for_employee_store_selection = State()
    waiting_for_employee_edit_field = State()
    waiting_for_employee_edit_value = State()
    waiting_for_confirm_employee_delete = State()
    waiting_for_store_domain = State()
    waiting_for_item_type = State()
    waiting_for_item_list = State()
    waiting_for_item_view = State()
    waiting_for_item_reply = State()
    waiting_for_store_action = State()
    waiting_for_reviews_list = State()
    waiting_for_review_detail = State()
    waiting_for_questions_list = State()
    waiting_for_question_detail = State()
    waiting_for_reviews_type_selection = State()
    viewing_review_details = State()
    waiting_for_reply_text = State()
    confirming_reply = State()
    viewing_answered_questions = State()
    viewing_questions_list = State()
    waiting_for_rating_to_change_template = State()
    waiting_for_template_text = State()
    waiting_for_old_password = State()
    waiting_for_new_password = State()
    waiting_for_new_password_confirmation = State()
    waiting_for_template_rating_selection = State()
    viewing_template_details = State()
    waiting_for_stop_words = State()
    waiting_for_minus_words = State()
    in_support_menu = State()

NOTIFICATION_FREQUENCIES = {
    1: "every_hour",
    3: "every_3_hours",
    6: "every_6_hours"
}

URGENT_THRESHOLDS = {
    1: "only_1_star",
    2: "1_2_stars",
    3: "1_3_stars",
    0: "disabled"
}

stores = [
    "Ozon", "Wildberries"
]

MODES = ["auto", "semi", "manual", "template"]

LANGUAGE_CHOICES = {
    "ru": "language_ru",
    "en": "language_en",
    "uz": "language_uz",
    "uk": "language_uk",
    "az": "language_az",
    "kz": "language_kz",
    "by": "language_by",
    "am": "language_am",
    "cn": "language_cn",
}