import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "your_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "your_password"),
        port=os.getenv("DB_PORT", 5432)
    )
    conn.autocommit = False
    cursor = conn.cursor()
    logger.info("✅ Подключение к базе данных установлено")
except psycopg2.Error as e:
    logger.error(f"❌ Ошибка подключения к базе данных: {e}")
    exit(1)

try:
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    tables = [row[0] for row in cursor.fetchall()]
    logger.info(f"📋 Найдено таблиц: {len(tables)} ({', '.join(tables)})")
except psycopg2.Error as e:
    logger.error(f"❌ Ошибка при получении списка таблиц: {e}")
    conn.rollback()
    cursor.close()
    conn.close()
    exit(1)

for table in tables:
    try:
        logger.info(f"📦 Таблица: {table}")
        cursor.execute(sql.SQL("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
        """), [table])
        columns = cursor.fetchall()
        for col in columns:
            name, dtype, nullable, default = col
            logger.info(f"   └─ {name} ({dtype}) {'NULL' if nullable == 'YES' else 'NOT NULL'} | DEFAULT: {default}")
    except psycopg2.Error as e:
        logger.error(f"❌ Ошибка при получении схемы таблицы {table}: {e}")
        conn.rollback()
        continue

# ⚠️ Очистка таблиц в порядке, учитывающем зависимости
tables_to_clear = ['store_modes', 'stores', 'users']  # Порядок важен из-за внешних ключей
for table in tables_to_clear:
    if table in tables:
        try:
            cursor.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))
            logger.info(f"✅ Таблица {table} очищена")
        except psycopg2.Error as e:
            logger.error(f"❌ Ошибка при очистке таблицы {table}: {e}")
            conn.rollback()
            continue
    else:
        logger.warning(f"⚠️ Таблица {table} не найдена в базе данных")

# 🔍 Получить и сбросить все sequences
try:
    cursor.execute("""
        SELECT sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
    """)
    sequences = [row[0] for row in cursor.fetchall()]
    for seq in sequences:
        try:
            cursor.execute(sql.SQL("ALTER SEQUENCE {} RESTART WITH 1").format(sql.Identifier(seq)))
            logger.info(f"🔁 Последовательность {seq} сброшена до 1")
        except psycopg2.Error as e:
            logger.error(f"❌ Ошибка при сбросе последовательности {seq}: {e}")
            conn.rollback()
            continue
except psycopg2.Error as e:
    logger.error(f"❌ Ошибка при получении списка sequences: {e}")
    conn.rollback()

# 📝 Подтверждение транзакции
try:
    conn.commit()
    logger.info("✅ Все изменения успешно применены")
except psycopg2.Error as e:
    logger.error(f"❌ Ошибка при фиксации транзакции: {e}")
    conn.rollback()

# 🧹 Закрытие соединения
try:
    cursor.close()
    conn.close()
    logger.info("🔌 Соединение с базой данных закрыто")
except psycopg2.Error as e:
    logger.error(f"❌ Ошибка при закрытии соединения: {e}")

print("\n✅ Готово!")