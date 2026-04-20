# ReviewBot Web — Веб-панель управления

Полноценная веб-альтернатива Telegram-боту. React фронтенд + FastAPI бэкенд поверх существующей PostgreSQL базы.

---

## Структура

```
reviewbot/
├── backend/          # FastAPI API (НОВОЕ)
│   ├── main.py
│   ├── auth_utils.py
│   ├── requirements.txt
│   └── routers/
│       ├── auth.py
│       ├── stores.py
│       ├── reviews.py
│       ├── questions.py
│       ├── settings.py
│       ├── employees.py
│       └── analytics.py
│
├── frontend/         # React приложение (НОВОЕ)
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── index.css
│       ├── main.jsx
│       ├── services/api.js
│       ├── components/
│       │   ├── Layout.jsx
│       │   └── ReviewCard.jsx
│       └── pages/
│           ├── LoginPage.jsx
│           ├── DashboardPage.jsx
│           ├── ReviewsPage.jsx
│           ├── QuestionsPage.jsx
│           ├── StoreSettingsPage.jsx
│           ├── EmployeesPage.jsx
│           └── AnalyticsPage.jsx
│
├── bot.py            # Telegram бот (существующий)
├── db/               # (существующий)
└── utils/            # (существующий)
```

---

## Быстрый старт

### 1. Бэкенд (FastAPI)

```bash
# Установить зависимости (из корня проекта)
pip install fastapi uvicorn python-jose passlib python-multipart

# Добавить в .env:
# JWT_SECRET_KEY=your-secret-key-here
# FRONTEND_URL=http://localhost:5173

# Запустить (из корня проекта — чтобы импорты db/ и utils/ работали)
uvicorn backend.main:app --reload --port 8000
```

Документация API будет доступна на http://localhost:8000/docs

### 2. Фронтенд (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Откроется на http://localhost:5173

### 3. Войти в систему

Используйте тот же номер телефона, что зарегистрирован в Telegram-боте.

---

## Возможности

| Страница | Что умеет |
|---|---|
| Обзор | Метрики, последние отзывы |
| Отзывы | Просмотр, ответ вручную или ИИ |
| Вопросы | Просмотр, ответ вручную или ИИ |
| Настройки ИИ | Режимы 1-5★, шаблоны, тон, стоп/минус-слова |
| Аналитика | Статистика по магазинам, распределение рейтингов |
| Сотрудники | Добавить, редактировать, деактивировать |

---

## Продакшн-деплой

```bash
# Собрать фронтенд
cd frontend && npm run build

# Раздавать через nginx или FastAPI StaticFiles:
# app.mount("/", StaticFiles(directory="frontend/dist", html=True))

# Запустить бэкенд через gunicorn:
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker
```
