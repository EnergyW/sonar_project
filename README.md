# 🤖 ReviewBot — AI-помощник для маркетплейсов

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=for-the-badge&logo=openai&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-asyncpg-336791?style=for-the-badge&logo=postgresql&logoColor=white)

**Telegram-бот для автоматической обработки отзывов и вопросов на Ozon и Wildberries с помощью ИИ**

[Возможности](#-возможности) · [Быстрый старт](#-быстрый-старт) · [Конфигурация](#-конфигурация) · [Архитектура](#-архитектура) · [Языки](#-поддерживаемые-языки)

</div>

---

## ✨ Возможности

### 🛍️ Поддерживаемые платформы
| Платформа | Отзывы | Вопросы | Автоответы |
|-----------|--------|---------|------------|
| **Ozon** | ✅ | ✅ | ✅ |
| **Wildberries** | ✅ | ✅ | ✅ |

### 🤖 Режимы работы с отзывами и вопросами

| Режим | Описание |
|-------|----------|
| 🤖 **Автоматический** | Бот сам генерирует и отправляет ответ без участия продавца |
| ⚙️ **Полуавтоматический** | Бот предлагает ответ, продавец подтверждает или редактирует |
| ✋ **Ручной** | Продавец пишет ответ самостоятельно |
| 📄 **По шаблону** | Бот отвечает заданным шаблоном для конкретного рейтинга |

### 🧠 Умная генерация ответов

- Учитывает **рейтинг**, **текст отзыва**, **плюсы и минусы** (WB) и **характеристики товара** (Ozon)
- Настраиваемый **тон** ответа: деловой, приветливый, строгий
- Настраиваемая **длина** ответа: краткий / стандартный / развёрнутый
- **Форма обращения**: Вы / вы / ты
- Поддержка **эмодзи** в ответах
- **Минус-слова**: ИИ не будет использовать заданные слова
- **Стоп-слова**: отключение генерации при наличии ключевых слов
- Ненавязчивое **упоминание других товаров** магазина (для положительных отзывов)

### 👥 Управление командой

- Добавление **сотрудников** с индивидуальным PIN-кодом
- Назначение сотрудникам конкретных магазинов
- Управление доступом и статусом активности

### 🌍 Мультиязычность

Полный интерфейс на **9 языках** с автоматическим определением языка пользователя.

---

## 🚀 Быстрый старт

### Требования

- Python 3.11+
- PostgreSQL 14+
- `msgfmt` (gettext) для компиляции переводов

### Установка

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/your-org/reviewbot.git
cd reviewbot

# 2. Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Скомпилируйте переводы
python locale/compile.py

# 5. Создайте файл .env (см. раздел Конфигурация)
cp .env.example .env

# 6. Инициализируйте базу данных
# Примените SQL-миграции из папки /db/migrations

# 7. Запустите бота
python bot.py
```

### Параллельный запуск автоответчика

```bash
# В отдельном терминале — цикл обработки магазинов
python utils/auto_otvet.py
```

---

## ⚙️ Конфигурация

Создайте файл `.env` в корне проекта:

```env
# Telegram
TELEGRAM_TOKEN=your_telegram_bot_token

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# База данных (PostgreSQL)
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=reviewbot

# (Опционально) Прокси для OpenAI
PROXY=socks5://user:pass@host:port
```

---

## 🏗️ Архитектура

```
reviewbot/
├── bot.py                    # Точка входа, регистрация роутеров
├── i18n.py                   # Система интернационализации
│
├── handlers/                 # Обработчики команд и callback'ов
│   ├── start.py              # Авторизация, выбор языка и роли
│   ├── store.py              # Управление магазинами
│   ├── review.py             # Работа с отзывами
│   ├── review_utils.py       # Вспомогательные функции для отзывов
│   ├── question.py           # Работа с вопросами
│   ├── store_settings.py     # Настройки ИИ, шаблоны, стоп-слова
│   ├── employee.py           # Управление сотрудниками
│   └── profile.py            # Профиль пользователя
│
├── keyboards/                # Inline-клавиатуры
│   ├── kb_for_stores.py
│   ├── kb_for_reviews.py
│   ├── kb_for_questions.py
│   ├── kb_for_store_settings.py
│   ├── kb_for_employees.py
│   ├── kb_for_profiles.py
│   └── kb_for_start.py
│
├── utils/
│   ├── ai_utils.py           # Генерация ответов через OpenAI
│   ├── api_utils.py          # Интеграция с API Ozon и Wildberries
│   ├── auto_otvet.py         # Фоновый цикл автоответов
│   └── cache.py              # Кэш непрочитанных отзывов/вопросов
│
├── db/
│   └── database.py           # AsyncDatabase — весь слой данных
│
├── states/
│   └── states.py             # FSM-состояния aiogram
│
└── locale/                   # Файлы переводов (.po / .mo)
    ├── ru/, en/, uz/, az/
    ├── kz/, by/, am/, cn/, kg/
    └── compile.py
```

### Ключевые технические решения

**Кэширование счётчиков**
`StoreCache` в `utils/cache.py` хранит в памяти количество непрочитанных отзывов и вопросов для каждого магазина. Обновление происходит в фоне каждые 2 минуты, что избавляет от избыточных API-запросов при открытии интерфейса магазина.

**FSM-навигация**
Весь пользовательский флоу реализован через конечный автомат состояний aiogram (`StatesGroup`). Каждый экран — отдельное состояние, переходы управляются callback-данными кнопок.

**Мультиплатформенный API-клиент**
`PLATFORM_CONFIG` в `api_utils.py` — словарь конфигураций для Ozon и Wildberries. Добавление новой платформы сводится к описанию конфигурации в одном месте без изменения остального кода.

---

## 🌍 Поддерживаемые языки

| Код | Язык | Код | Язык |
|-----|------|-----|------|
| `ru` | 🇷🇺 Русский | `kz` | 🇰🇿 Казахский |
| `en` | 🇬🇧 Английский | `by` | 🇧🇾 Белорусский |
| `uz` | 🇺🇿 Узбекский | `am` | 🇦🇲 Армянский |
| `az` | 🇦🇿 Азербайджанский | `cn` | 🇨🇳 Китайский |
| `kg` | 🇰🇬 Кыргызский | | |

Для добавления нового языка создайте файл `locale/<код>/LC_MESSAGES/bot.po` и скомпилируйте командой `python locale/compile.py`.

---

## 🗃️ Схема базы данных

```
users                stores              store_settings
├── account_id       ├── store_id        ├── store_id
├── phone            ├── account_id      ├── templates (JSON)
├── language         ├── store_name      ├── address_style
└── role             ├── type            ├── response_length
                     ├── api_key         ├── use_emojis
employees            ├── client_id       ├── tone
├── employee_id      ├── reviews_enabled ├── minus_words[]
├── account_id       ├── questions_en.   └── stop_words[]
├── full_name        └── questions_mode
├── phone
├── access_code      store_modes
└── is_active        ├── store_id
                     ├── mode_key (1–5)
employee_stores      └── mode_value
├── employee_id
└── store_id
```

---

## 📡 Интеграция с маркетплейсами

### Ozon
Использует официальный [Ozon Seller API](https://docs.ozon.ru/api/seller/). Для подключения необходимы `Client-Id` и `Api-Key`.

```
Отзывы:  POST /v1/review/list
Ответ:   POST /v1/review/comment/create
Вопросы: POST /v1/question/list
Ответ:   POST /v1/question/answer/create
Товары:  POST /v3/product/list + /v3/product/info/list
```

### Wildberries
Использует [Wildberries Feedbacks API](https://openapi.wildberries.ru/). Для подключения достаточно `API-Token`.

```
Отзывы:  GET  /api/v1/feedbacks
Ответ:   POST /api/v1/feedbacks/answer
Вопросы: GET  /api/v1/questions
Ответ:   POST /api/v1/questions/answer
Товары:  POST /content/v2/get/cards/list
```

---

## 🔄 Жизненный цикл автоответа

```
Новый отзыв на платформе
        │
        ▼
get_store_reviews() ──► Фильтрация уже отвеченных
        │
        ▼
Проверка режима (modes[rating])
        │
   ┌────┴────────────────────────────┐
   │ auto          │ template        │ semi/manual
   ▼               ▼                 ▼
generate_reply()  templates[rating]  Ожидание действия
   │               │                 продавца в боте
   ▼               ▼
post_review_answer() ──► Ответ опубликован
```

---

## 🛠️ Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Telegram Bot | [aiogram 3.x](https://docs.aiogram.dev/) |
| AI-генерация | [OpenAI API](https://platform.openai.com/) (GPT-4o) |
| База данных | PostgreSQL + [asyncpg](https://github.com/MagicStack/asyncpg) |
| HTTP-клиент | [aiohttp](https://docs.aiohttp.org/) |
| Прокси | [httpx-socks](https://github.com/romis2012/httpx-socks) |
| Переводы | Python `gettext` (.po/.mo) |
| Конфигурация | [python-dotenv](https://github.com/theskumar/python-dotenv) |

---

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для фичи: `git checkout -b feature/new-platform`
3. Зафиксируйте изменения: `git commit -m 'Add new platform support'`
4. Отправьте PR в `main`

При добавлении новых строк интерфейса обновите все `.po`-файлы и перекомпилируйте переводы.

---

## 📄 Лицензия

Проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).

---

<div align="center">
  Сделано с ❤️ для продавцов на маркетплейсах
</div>
