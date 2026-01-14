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

os.makedirs('logs', exist_ok=True)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.propagate = False

setup_logging()

logger = logging.getLogger(__name__)

load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
    logger.info("Запуск бота...")
    await init_db()
    register_routers()
    asyncio.create_task(start_background_updater())
    try:
        logger.info("Бот начал работу")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        await close_db()
        await bot.session.close()
        logger.info("Бот остановлен, соединения с БД закрыты.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {e}", exc_info=True)