import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from handlers.start import router as start_router
from handlers.employee import router as employee_router
from handlers.store import router as store_router
from handlers.review import router as review_router
from handlers.question import router as question_router
from handlers.profile import router as profile_router
from handlers.store_settings import router as store_settings_router
from db.database import init_db, close_db
from utils.cache import start_background_updater


LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    handlers=[
        RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not API_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не найден в .env")

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


def register_routers():
    dp.include_router(profile_router)
    dp.include_router(start_router)
    dp.include_router(employee_router)
    dp.include_router(store_router)
    dp.include_router(review_router)
    dp.include_router(question_router)
    dp.include_router(store_settings_router)


async def main():
    logger.info("🚀 Запуск бота")

    await init_db()
    logger.info("✅ База данных инициализирована")

    register_routers()
    logger.info("✅ Роутеры зарегистрированы")

    asyncio.create_task(start_background_updater())
    logger.info("🧠 Фоновый апдейтер кеша запущен")

    try:
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        logger.info("🛑 Бот остановлен, соединения закрыты")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("⛔ Бот остановлен вручную")
