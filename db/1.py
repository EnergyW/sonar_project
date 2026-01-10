import psycopg2
from psycopg2 import Error

DB_HOST = 'localhost'
DB_NAME = 'sonar_db_utf8'
DB_USER = 'postgres'
DB_PASSWORD = '123'
DB_PORT = '5432'

try:

    connection = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    cursor = connection.cursor()

    query = """
    SELECT 
        table_name, 
        column_name, 
        data_type, 
        is_nullable,
        column_default
    FROM 
        information_schema.columns
    WHERE 
        table_schema = 'public'
    ORDER BY 
        table_name, ordinal_position;
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    if not rows:
        print("В базе данных не найдено таблиц или столбцов.")
    else:
        current_table = None
        for row in rows:
            table_name, column_name, data_type, is_nullable, column_default = row
            if current_table != table_name:
                current_table = table_name
                print(f"\n--- Таблица: {table_name} ---")
            print(f"  Столбец: {column_name:<25} Тип: {data_type:<15} "
                  f"NULL: {is_nullable:<3} По умолчанию: {column_default}")

except Error as e:
    print(f"Ошибка при работе с PostgreSQL: {e}")
finally:
    if connection:
        cursor.close()
        connection.close()
        print("\nСоединение с базой данных закрыто.")