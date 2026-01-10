import gettext
import logging
from pathlib import Path
from typing import Union
from aiogram.fsm.context import FSMContext
from db.database import AsyncDatabase

class I18N:
    def __init__(self):
        self.locale_dir = Path(__file__).parent / "locale"
        self.languages = {}
        self.default_lang = "ru"
        self.supported_langs = {"az", "en", "kz", "uz", "ru", "by", "am", "cn", "kg"}
        self._load_translations()

    def _load_translations(self):
        for lang in self.supported_langs:
            translation_file = self.locale_dir / lang / "LC_MESSAGES" / "bot.po"
            logging.info(f"Attempting to load translation file: {translation_file}")
            try:
                trans = gettext.translation(
                    'bot',
                    localedir=str(self.locale_dir),
                    languages=[lang]
                )
                self.languages[lang] = trans
                logging.info(f"Loaded translations for '{lang}'")
            except FileNotFoundError:
                self.languages[lang] = gettext.NullTranslations()
                logging.warning(f"Translation file {translation_file} not found. Using null translations.")
            except Exception as e:
                self.languages[lang] = gettext.NullTranslations()
                logging.error(f"Error loading translations for '{lang}': {str(e)}")

    def get_translator(self, lang_code: str) -> Union[gettext.GNUTranslations, gettext.NullTranslations]:
        if lang_code not in self.supported_langs:
            logging.warning(f"Unsupported language code '{lang_code}', falling back to '{self.default_lang}'")
            lang_code = self.default_lang

        return self.languages.get(lang_code, gettext.NullTranslations())

    async def get_text(self, lang: str, key: str) -> str:
        translator = self.get_translator(lang)
        translated = translator.gettext(key)
        logging.debug(f"Translated key '{key}' for lang '{lang}': {translated}")
        return translated

async def _(account_id: str, key: str, state: FSMContext = None, **kwargs) -> str:
    try:
        lang = None
        if state:
            data = await state.get_data()
            lang = data.get("chosen_language")

        if not lang:
            async with AsyncDatabase() as db:
                user = await db.get_user(account_id)
                lang = await db.get_user_language(account_id) if user else "ru"

        translated = await i18n.get_text(lang, key)
        if not translated or translated == key:
            logging.warning(f"Missing translation: lang={lang}, key={key}")
            if lang != "en":
                translated = await i18n.get_text("en", key)
                if translated and translated != key:
                    logging.info(f"Falling back to English translation for key {key}")
                    try:
                        return translated % kwargs if kwargs else translated
                    except (KeyError, ValueError) as e:
                        logging.error(f"Error in translation formatting: key={key}, kwargs={kwargs}, error={e}")
                        return translated
            return f"⚠️ Missing translation: {key}"

        try:
            return translated % kwargs if kwargs else translated
        except (KeyError, ValueError) as e:
            logging.error(f"Error in translation formatting: key={key}, kwargs={kwargs}, error={e}")
            return translated

    except Exception as e:
        logging.error(f"Translation error for user {account_id}, key {key}: {str(e)}")
        return f"⚠️ Error: {key}"


i18n = I18N()