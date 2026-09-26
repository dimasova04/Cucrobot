# Cucrobot

Telegram-бот «фото с актёром»: пользователь присылает фото людей, выбирает актёров и сцену,
бот генерирует совместное фото через Runware. Кристаллики, подписки, Tribute и Telegram Stars.

## Локально
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    cp .env.example .env   # заполнить BOT_TOKEN, RUNWARE_API_KEY
    .venv/bin/python -m pytest -q
    .venv/bin/python main.py

Без DATABASE_URL используется SQLite-файл `cucrobot.db`, без REDIS_URL — память (FSM теряется при рестарте).

## Railway
1. Создать проект, добавить PostgreSQL и Redis; сервис бота из этого репозитория (Dockerfile).
2. Переменные: все из `.env.example`; `DATABASE_URL` и `REDIS_URL` взять из плагинов Railway
   (`postgres://` переписывается автоматически).
3. Сгенерировать домен сервиса, в Tribute указать вебхук `https://<домен>/webhooks/tribute`.
4. В Tribute создать 3 цифровых товара и 3 подписки, вписать их ссылки и id в переменные.
5. Первый запуск применяет миграции Alembic (создаёт таблицы) и заводит стартовые сцены.
   Актёров добавляйте через `/actors`: имя, описание внешности, 2–4 фото.
6. Бот работает в одном экземпляре (long polling); не запускайте несколько реплик.

### Новая миграция
После изменения моделей в `database/models.py`:

    DATABASE_URL=sqlite+aiosqlite:///./cucrobot.db BOT_TOKEN=x \
      .venv/bin/alembic revision --autogenerate -m "что изменилось"

Файл появится в `alembic/versions/`, его нужно просмотреть и закоммитить; на Railway
миграция применится при следующем деплое.

## Админ-команды
Пошаговая инструкция по добавлению актёров и сцен: [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md).

`/stats`, `/give <id> <n>`, `/sub <id> <sub_week|sub_month|sub_3month>`, `/user <id>`,
`/block <id>`, `/unblock <id>`, `/actors`, `/scenes`.

## Сравнение моделей
    .venv/bin/python scripts/bench_models.py --person me.jpg --actor "Имя:описание:ref1.jpg,ref2.jpg" --scene "on a yacht"

Описание актёра может содержать двоеточия; пути к файлам не должны содержать запятых.
