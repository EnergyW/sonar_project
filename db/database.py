import os
import re
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: Optional[asyncpg.Pool] = None

async def init_db():
    global _pool
    dsn = (
        f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','')}@"
        f"{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/"
        f"{os.getenv('DB_NAME','postgres')}"
    )
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    logging.info("DB pool initialized")

async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        logging.info("DB pool closed")

class AsyncDatabase:
    def __init__(self):
        self.conn: Optional[asyncpg.connection.Connection] = None

    async def __aenter__(self):
        if _pool is None:
            raise RuntimeError("Database not initialized. Call await init_db()")
        self.conn = await _pool.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn and _pool:
            await _pool.release(self.conn)
        self.conn = None

    async def create_system_user(self) -> None:
        try:
            await self.conn.execute(
                "INSERT INTO users (account_id, language) VALUES ($1, $2) "
                "ON CONFLICT (account_id) DO NOTHING",
                "0", "ru"  # account_id как строка
            )
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error create_system_user: {e}")

    async def get_user(self, account_id: str) -> Optional[Dict[str, Any]]:  # account_id как str
        try:
            row = await self.conn.fetchrow(
                "SELECT account_id, phone, language, role FROM users WHERE account_id = $1",
                account_id  # передаем как строку
            )
            return dict(row) if row else None
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_user: {e} | account_id={account_id}")
            return None

    async def create_user(self,
                          account_id: str,  # account_id как str
                          phone: Optional[str] = None,
                          language: str = "ru",
                          role: Optional[str] = None) -> None:
        try:
            await self.conn.execute(
                """
                INSERT INTO users (account_id, phone, language, role)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (account_id) DO UPDATE SET
                  phone = EXCLUDED.phone,
                  language = EXCLUDED.language,
                  role = EXCLUDED.role
                """,
                account_id, phone, language, role  # account_id как строка
            )
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error create_user: {e} | account_id={account_id}")

    async def update_user_phone(self, account_id: str, phone: str) -> None:  # account_id как str
        try:
            await self.conn.execute("UPDATE users SET phone = $1 WHERE account_id = $2",
                                   phone, account_id)  # account_id как строка
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_user_phone: {e} | account_id={account_id}")

    async def update_user_language(self, account_id: str, language: str) -> None:  # account_id как str
        try:
            await self.conn.execute("UPDATE users SET language = $1 WHERE account_id = $2",
                                   language, account_id)  # account_id как строка
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_user_language: {e} | account_id={account_id}")

    async def get_user_language(self, account_id: str) -> str:  # account_id как str
        try:
            row = await self.conn.fetchrow("SELECT language FROM users WHERE account_id = $1",
                                          account_id)  # account_id как строка
            return row["language"] if row and row.get("language") else "ru"
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_user_language: {e} | account_id={account_id}")
            return "ru"

    # ------------------ STORES ------------------

    async def get_user_stores(self, account_id: str) -> List[Tuple[int, str, str]]:  # account_id как str
        try:
            rows = await self.conn.fetch("SELECT store_id, store_name, type FROM stores WHERE account_id = $1",
                                        account_id)  # account_id как строка
            return [ (r["store_id"], r["store_name"], r["type"]) for r in rows ]
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_user_stores: {e} | account_id={account_id}")
            return []

    async def get_all_stores(self) -> List[int]:
        try:
            rows = await self.conn.fetch("SELECT store_id FROM stores")
            return [r["store_id"] for r in rows]
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_all_stores: {e}")
            return []

    async def create_store(self,
                           account_id: str,  # account_id как str
                           store_name: Any,
                           store_type: Any,
                           api_key: Any,
                           client_id: Optional[Any] = None) -> Optional[int]:

        account_id_str = account_id  # account_id уже строка
        store_name_str = str(store_name)
        store_type_str = str(store_type)
        api_key_str = str(api_key)
        client_id_str = str(client_id) if client_id is not None else None

        valid_types = {"Ozon", "Wildberries", "Yandex Market"}
        if store_type_str not in valid_types:
            raise ValueError(f"Invalid store type: {store_type_str!r}")

        if store_type_str == "Wildberries":
            client_id_str = None

        try:
            row = await self.conn.fetchrow(
                """
                INSERT INTO stores (
                    account_id, store_name, type, api_key, client_id,
                    reviews_enabled, questions_enabled, questions_mode
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                RETURNING store_id
                """,
                account_id_str,  # передаем как строку
                store_name_str,
                store_type_str,
                api_key_str,
                client_id_str,
                False,
                False,
                "manual"
            )
        except asyncpg.PostgresError as e:
            logging.error(
                "SQL error create_store: %s | params: account_id=%r store_name=%r store_type=%r api_key=%r client_id=%r",
                e, account_id_str, store_name_str, store_type_str, api_key_str, client_id_str)
            return None

        if not row:
            logging.error("Failed to create store — insert returned None (no exception)")
            return None

        store_id = row["store_id"]

        try:
            await self.conn.execute(
                """
                INSERT INTO store_settings (store_id, templates)
                VALUES ($1, $2)
                """,
                store_id, json.dumps({})
            )
            logging.info(f"✅ Created default store_settings for store_id={store_id}")
        except Exception as e:
            logging.error(f"❌ Error creating default store settings: {e} | store_id={store_id}")

        for rating in range(1, 6):
            try:
                await self.conn.execute(
                    "INSERT INTO store_modes (store_id, mode_key, mode_value) VALUES ($1,$2,$3)",
                    store_id, str(rating), "manual"
                )
            except asyncpg.PostgresError as e:
                logging.error("SQL error inserting store_mode: %s | store_id=%r rating=%r", e, store_id, rating)

        logging.info(f"✅ Successfully created store: store_id={store_id}, name={store_name_str}, type={store_type_str}")
        return store_id

    async def get_store_details(self, store_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = await self.conn.fetchrow(
                """
                SELECT store_id, account_id, store_name, type, api_key, client_id,
                       reviews_enabled, questions_enabled, questions_mode
                FROM stores WHERE store_id = $1
                """,
                store_id
            )
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_store_details: {e} | store_id={store_id}")
            return None

        if not row:
            return None

        store = dict(row)

        settings = await self.get_store_settings(store_id)
        if settings:
            store["templates"] = settings.get("templates", {})
            store.update({k: v for k, v in settings.items() if k != 'store_id'})
        else:
            store["templates"] = {}

        try:
            modes_rows = await self.conn.fetch("SELECT mode_key, mode_value FROM store_modes WHERE store_id = $1",
                                               store_id)
            store["modes"] = {r["mode_key"]: r["mode_value"] for r in modes_rows}
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error loading store_modes: {e} | store_id={store_id}")
            store["modes"] = {}

        tmpl = store.get("templates")
        if isinstance(tmpl, str):
            try:
                tmpl = json.loads(tmpl)
            except Exception:
                tmpl = {}
        if tmpl is None:
            tmpl = {}
        store["templates"] = {str(k): v for k, v in tmpl.items()} if isinstance(tmpl, dict) else {}

        return store

    async def update_store_mode(self, store_id: int, rating: int, mode: str) -> None:
        try:
            await self.conn.execute(
                """
                INSERT INTO store_modes (store_id, mode_key, mode_value)
                VALUES ($1,$2,$3)
                ON CONFLICT (store_id, mode_key) DO UPDATE SET mode_value = EXCLUDED.mode_value
                """,
                store_id, str(rating), str(mode)
            )
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_store_mode: {e} | store_id={store_id} rating={rating} mode={mode}")

    async def update_questions_mode(self, store_id: int, mode: str) -> None:
        try:
            await self.conn.execute("UPDATE stores SET questions_mode = $1 WHERE store_id = $2", str(mode), store_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_questions_mode: {e} | store_id={store_id} mode={mode}")

    async def toggle_store_setting(self, store_id: int, setting: str, value: Optional[bool] = None) -> Optional[bool]:
        if setting not in ("reviews_enabled", "questions_enabled"):
            raise ValueError(f"Invalid setting: {setting}")

        try:
            if value is None:
                row = await self.conn.fetchrow(f"UPDATE stores SET {setting} = NOT {setting} WHERE store_id = $1 RETURNING {setting}", store_id)
            else:
                row = await self.conn.fetchrow(f"UPDATE stores SET {setting} = $1 WHERE store_id = $2 RETURNING {setting}", value, store_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error toggle_store_setting: {e} | store_id={store_id} setting={setting} value={value}")
            return None

        return row[setting] if row else None

    async def update_store_field(self, store_id: int, field: str, value: Any) -> None:
        if field not in ("store_name", "api_key", "client_id"):
            raise ValueError(f"Invalid field: {field}")

        val = str(value) if value is not None else None

        try:
            await self.conn.execute(f"UPDATE stores SET {field} = $1 WHERE store_id = $2", val, store_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_store_field: {e} | store_id={store_id} field={field} value={value}")

    async def delete_store(self, store_id: int) -> bool:
        try:
            res = await self.conn.execute("DELETE FROM stores WHERE store_id = $1", store_id)
            return res is not None and "DELETE" in str(res)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error delete_store: {e} | store_id={store_id}")
            return False

    async def get_all_users_with_stores(self) -> List[Dict[str, Any]]:
        try:
            rows = await self.conn.fetch(
                """
                SELECT u.account_id, u.phone, u.language,
                       s.store_id, s.store_name, s.type, s.api_key, s.client_id,
                       s.reviews_enabled, s.questions_enabled, s.questions_mode
                FROM users u
                LEFT JOIN stores s ON u.account_id = s.account_id
                ORDER BY u.account_id, s.store_id
                """
            )
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_all_users_with_stores: {e}")
            return []

        users: Dict[str, Dict[str, Any]] = {}  # ключ - account_id как строка
        for r in rows:
            row = dict(r)
            acct = str(row["account_id"])  # преобразуем к строке
            if acct not in users:
                users[acct] = {"account_id": acct, "phone": row.get("phone"), "language": row.get("language"), "stores": []}
            if row.get("store_id") is not None:
                users[acct]["stores"].append({
                    "store_id": row["store_id"],
                    "store_name": row["store_name"],
                    "type": row["type"],
                    "api_key": row["api_key"] or "",
                    "client_id": row["client_id"],
                    "reviews_enabled": row["reviews_enabled"],
                    "questions_enabled": row["questions_enabled"],
                    "questions_mode": row["questions_mode"],
                })

        return list(users.values())

    # ------------------ EMPLOYEES ------------------

    async def init_schema(self) -> None:
        try:
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    employee_id SERIAL PRIMARY KEY,
                    account_id TEXT,  -- изменено на TEXT
                    full_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    access_code TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    UNIQUE (phone, access_code),
                    FOREIGN KEY (account_id) REFERENCES users(account_id) ON DELETE CASCADE
                )
            """)
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS employee_stores (
                    employee_id INTEGER NOT NULL,
                    store_id INTEGER NOT NULL,
                    PRIMARY KEY (employee_id, store_id),
                    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
                    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE
                )
            """)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error init_schema: {e}")

    async def create_employee(self, account_id: str, full_name: str, phone: str, access_code: str) -> Optional[int]:  # account_id как str
        if not re.match(r"^\d{4}$", str(access_code)):
            raise ValueError("Access code must be 4 digits")
        try:
            row = await self.conn.fetchrow(
                "INSERT INTO employees (account_id, full_name, phone, access_code, is_active) VALUES ($1,$2,$3,$4,$5) RETURNING employee_id",
                account_id, full_name, phone, access_code, True  # account_id как строка
            )
            return row["employee_id"] if row else None
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error create_employee: {e} | account_id={account_id}")
            return None

    async def get_employee_by_phone_and_code(self, phone: str, access_code: str) -> Optional[Dict[str, Any]]:
        try:
            row = await self.conn.fetchrow(
                "SELECT employee_id, account_id, full_name, phone, access_code, is_active FROM employees WHERE phone = $1 AND access_code = $2",
                phone, access_code
            )
            if row:
                result = dict(row)
                result["account_id"] = str(result["account_id"]) if result.get("account_id") else None
                return result
            return None
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_employee_by_phone_and_code: {e}")
            return None

    async def get_employees_by_owner(self, account_id: str) -> List[Dict[str, Any]]:  # account_id как str
        try:
            rows = await self.conn.fetch(
                """
                SELECT e.employee_id, e.full_name, e.phone, e.access_code, e.is_active,
                       ARRAY_AGG(s.store_id) AS store_ids, ARRAY_AGG(s.store_name) AS store_names
                FROM employees e
                LEFT JOIN employee_stores es ON e.employee_id = es.employee_id
                LEFT JOIN stores s ON es.store_id = s.store_id
                WHERE e.account_id = $1
                GROUP BY e.employee_id
                """,
                account_id  # передаем как строку
            )
            return [dict(r) for r in rows] if rows else []
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_employees_by_owner: {e} | account_id={account_id}")
            return []

    async def assign_employee_to_stores(self, employee_id: int, store_ids: List[int]) -> None:
        try:
            await self.conn.execute("DELETE FROM employee_stores WHERE employee_id = $1", employee_id)
            valid_ids = [sid for sid in store_ids if sid is not None]
            for sid in valid_ids:
                try:
                    await self.conn.execute("INSERT INTO employee_stores (employee_id, store_id) VALUES ($1,$2)", employee_id, sid)
                except asyncpg.PostgresError as e:
                    logging.error(f"SQL error assign_employee_to_stores insert: {e} | employee_id={employee_id} store_id={sid}")
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error assign_employee_to_stores: {e} | employee_id={employee_id}")

    async def update_employee_field(self, employee_id: int, field: str, value: Any) -> None:
        if field not in ("full_name", "phone", "access_code", "is_active"):
            raise ValueError(f"Invalid field: {field}")
        if field == "access_code" and not re.match(r"^\d{4}$", str(value)):
            raise ValueError("Access code must be 4 digits")
        try:
            await self.conn.execute(f"UPDATE employees SET {field} = $1 WHERE employee_id = $2", value, employee_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_employee_field: {e} | employee_id={employee_id} field={field}")

    async def delete_employee(self, employee_id: int) -> bool:
        try:
            res = await self.conn.execute("DELETE FROM employees WHERE employee_id = $1", employee_id)
            return res is not None and "DELETE" in str(res)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error delete_employee: {e} | employee_id={employee_id}")
            return False

    async def get_employee_stores(self, employee_id: int) -> List[Tuple[int, str, str]]:
        try:
            rows = await self.conn.fetch(
                "SELECT s.store_id, s.store_name, s.type FROM stores s JOIN employee_stores es ON s.store_id = es.store_id WHERE es.employee_id = $1",
                employee_id
            )
            return [ (r["store_id"], r["store_name"], r["type"]) for r in rows ] if rows else []
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_employee_stores: {e} | employee_id={employee_id}")
            return []

    async def update_user_role(self, account_id: str, role: str) -> None:  # account_id как str
        try:
            await self.conn.execute("UPDATE users SET role = $1 WHERE account_id = $2", role, account_id)  # account_id как строка
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_user_role: {e} | account_id={account_id}")

    async def update_store_template(self, store_id: int, rating: int, template_text: Optional[str]) -> None:
        if rating < 1 or rating > 5:
            raise ValueError("rating must be 1..5")

        success = await self.update_store_template_in_settings(store_id, rating, template_text)
        if success:
            logging.info(f"Template updated in store_settings store_id={store_id} rating={rating}")
        else:
            logging.error(f"Failed to update template in store_settings store_id={store_id} rating={rating}")

    async def get_store_templates(self, store_id: int) -> Dict[str, Any]:
        store = await self.get_store_details(store_id)
        return store.get("templates", {}) if store else {}

    async def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        try:
            row = await self.conn.fetchrow("SELECT * FROM users WHERE phone = $1", phone)
            if row:
                result = dict(row)
                result["account_id"] = str(result["account_id"]) if result.get("account_id") else None
                return result
            return None
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_user_by_phone: {e} | phone={phone}")
            return None

    async def get_store_settings(self, store_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = await self.conn.fetchrow(
                """
                SELECT * FROM store_settings 
                WHERE store_id = $1
                """,
                store_id
            )
            if row:
                settings = dict(row)
                if isinstance(settings.get('templates'), str):
                    try:
                        settings['templates'] = json.loads(settings['templates'])
                    except Exception:
                        settings['templates'] = {}
                return settings
            else:
                return await self.create_default_store_settings(store_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error get_store_settings: {e} | store_id={store_id}")
            return None

    async def create_default_store_settings(self, store_id: int) -> Optional[Dict[str, Any]]:
        try:
            store = await self.get_store_details(store_id)
            templates = store.get('templates', {}) if store else {}

            await self.conn.execute(
                """
                INSERT INTO store_settings (store_id, templates)
                VALUES ($1, $2)
                """,
                store_id, json.dumps(templates)
            )

            return await self.get_store_settings(store_id)
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error create_default_store_settings: {e} | store_id={store_id}")
            return None

    async def update_store_settings(self, store_id: int, updates: Dict[str, Any]) -> bool:
        if not updates:
            return False

        try:
            set_clauses = []
            values = []
            param_count = 1

            for key, value in updates.items():
                if key == 'templates' and isinstance(value, dict):
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(json.dumps(value))
                elif key in ['stop_words', 'minus_words'] and isinstance(value, list):
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
                else:
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
                param_count += 1

            values.append(store_id)

            query = f"""
                UPDATE store_settings 
                SET {', '.join(set_clauses)}
                WHERE store_id = ${param_count}
            """

            await self.conn.execute(query, *values)
            return True

        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_store_settings: {e} | store_id={store_id} updates={updates}")
            return False

    async def update_store_settings_field(self, store_id: int, field: str, value: Any) -> bool:
        return await self.update_store_settings(store_id, {field: value})

    async def update_store_array_setting(self, store_id: int, array_field: str, words: List[str]) -> bool:
        try:
            await self.conn.execute(
                f"UPDATE store_settings SET {array_field} = $1 WHERE store_id = $2",
                words, store_id
            )
            return True
        except asyncpg.PostgresError as e:
            logging.error(f"SQL error update_store_array_setting: {e} | store_id={store_id} field={array_field}")
            return False

    async def get_store_templates_from_settings(self, store_id: int) -> Dict[str, Any]:
        settings = await self.get_store_settings(store_id)
        if settings and 'templates' in settings:
            templates = settings['templates']
            if isinstance(templates, str):
                try:
                    return json.loads(templates)
                except Exception:
                    return {}
            return templates
        return {}

    async def update_store_template_in_settings(self, store_id: int, rating: int, template_text: Optional[str]) -> bool:
        try:
            settings = await self.get_store_settings(store_id)
            if not settings:
                return False

            templates = settings.get('templates', {})
            if isinstance(templates, str):
                try:
                    templates = json.loads(templates)
                except Exception:
                    templates = {}

            rating_str = str(rating)
            if template_text is None:
                templates.pop(rating_str, None)
            else:
                templates[rating_str] = template_text

            return await self.update_store_settings_field(store_id, 'templates', templates)

        except Exception as e:
            logging.error(f"Error update_store_template_in_settings: {e} | store_id={store_id}")
            return False