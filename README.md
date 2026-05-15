# Учебная инфраструктура (Sibadi v4)

Веб-приложение для учёта учебной и лабораторной инфраструктуры: группы, дисциплины, преподаватели, средства, ПО, оборудование, занятия, серверы и пользователи. Ролевая модель с правами на сущности (таблица `Permissions`), экспорт занятий в Excel. Доступ к данным после **входа** (`/login`); часть маршрутов ограничена матрицей прав.

## Стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.11, Flask 3.1, Flask-Limiter, psycopg2 |
| БД | PostgreSQL 18 (официальный образ Docker) |
| Frontend | Jinja2, статика через CDN |
| Прод | Docker Compose, Nginx (TLS, reverse proxy на Flask `:8080`) |
| Экспорт | OpenPyXL (`.xlsx`) |

## Структура репозитория

```
├── docker-compose.yml          # сервисы db, web, nginx
├── .env.example                # образец переменных (скопировать в .env)
├── postgres/
│   ├── pg_hba.conf             # SCRAM-SHA-256 для TCP, peer для local
│   ├── docker-entrypoint-initdb.d/
│   │   ├── 01-schema.sql       # DDL, роли, permission_entities, начальные Permissions
│   │   └── 02-app-role.sh      # роль приложения + GRANT (не postgres)
│   └── upgrade-existing-database.sql  # сужение прав на уже развёрнутой БД
├── migrations/
│   └── 001_existing_database.sql     # данные поверх актуального DDL (роли, права, жёсткость Users)
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py, config.py, database.py, security.py
│   └── templates/
└── nginx/
    ├── Dockerfile
    ├── nginx.conf
    └── entrypoint.sh           # самоподписанный сертификат при первом старте
```

Том PostgreSQL в Compose: **`pgdata:/var/lib/postgresql`** — [рекомендуемая разметка для образов PostgreSQL 18+](https://github.com/docker-library/postgres/pull/1259).

## Быстрый старт (Docker Compose)

1. Клонируйте репозиторий и перейдите в корень проекта.

2. Создайте `.env`:
   ```bash
   cp .env.example .env
   ```

3. Отредактируйте `.env`:
   - **`DB_USER`** — роль приложения в БД; **не `postgres`** (скрипт [`02-app-role.sh`](postgres/docker-entrypoint-initdb.d/02-app-role.sh) завершится с ошибкой). Рекомендуется **`sibadi_app`**.
   - **`DB_PASS`** — пароль этой роли; при первом init передаётся в контейнер БД как `APP_DB_PASSWORD`.
   - **`POSTGRES_SUPER_PASSWORD`** — пароль суперпользователя `postgres` в контейнере. Если пусто, в Compose подставляется **`DB_PASS`**.
   - **`SECRET_KEY`** — в продакшене не короче **32** символов; при слабом значении приложение пишет предупреждение в лог.

4. Первый администратор:
   - **`ADMIN_BOOTSTRAP_ENABLED=false`** (по умолчанию): пароль генерируется (требования в духе ГОСТ Р 71753 / ФСТЭК) и **один раз** выводится в **stderr** контейнера `web` после первого HTTP-запроса (`docker compose logs web`).
   - **`ADMIN_BOOTSTRAP_ENABLED=true`**: задайте **`ADMIN_BOOTSTRAP_PASSWORD`**.

5. Запуск:
   ```bash
   docker compose up -d --build
   ```

6. Откройте **HTTPS** (см. [`docker-compose.yml`](docker-compose.yml) → `nginx`):

   | Порт хоста | Назначение |
   |------------|------------|
   | **443** | HTTPS → Nginx → Flask |
   | **80** | HTTP (часто редирект на HTTPS) |

Самоподписанный сертификат Nginx задаётся через **`SSL_CN`** в `.env`.

## Переменные окружения

Полный перечень и пояснения — в [`.env.example`](.env.example). Кратко:

| Переменная | Назначение |
|------------|------------|
| `DB_NAME` | Имя базы |
| `DB_USER`, `DB_PASS` | Роль и пароль **приложения** в PostgreSQL |
| `POSTGRES_SUPER_PASSWORD` | Пароль `postgres` в контейнере БД |
| `PGSSLMODE`, `DB_SSLMODE` | TLS к БД (libpq); **`DB_SSLMODE` имеет приоритет** над `PGSSLMODE` для приложения |
| `DB_POOL_MIN`, `DB_POOL_MAX` | Пул соединений psycopg2 |
| `DB_CONNECT_TIMEOUT`, `DB_APPLICATION_NAME` | Таймаут и имя в `pg_stat_activity` |
| `SECRET_KEY` | Секрет сессий Flask |
| `LOGIN_RATE_LIMIT`, `LOGIN_RATE_LIMIT_POST`, `RATE_LIMIT_STORAGE_URI` | Flask-Limiter на `/login` |
| `LOGIN_BF_*` | Анти-брутфорс по IP после серии неудачных входов |
| `ADMIN_BOOTSTRAP_*` | Создание первого администратора |
| `SSL_CN` | CN самоподписанного сертификата Nginx |

## PostgreSQL и том данных

- Скрипты в **`postgres/docker-entrypoint-initdb.d/`** выполняются **только при первом init** на пустом томе `pgdata`.
- Повторный прогон init: **`docker compose down -v`** (данные БД удалятся) и снова `docker compose up -d`.
- Порт **5432** снаружи по умолчанию **закрыт**; для администрирования с хоста раскомментируйте `ports` у `db` в `docker-compose.yml`.

## Основные URL

| Путь | Описание |
|------|----------|
| `/` | Главная (после входа) |
| `/login`, `/logout` | Вход / выход |
| `/healthz` | `{"status":"ok"}` (без лимита на `/login`) |
| `/группа`, `/дисциплина`, … | CRUD (права через `Permissions`) |
| `/permissions` | Матрица прав (только роль **Администратор** в приложении) |
| `/занятия_пользователь` | Занятия с фильтрами `group`, `disc`, `kurs` |
| `/занятия_пользователь_export` | Экспорт в Excel |

Удаление: POST на `/<сущность>/delete/<id>` с CSRF в форме. Первичные ключи в UI: например сервер — `id_сервера`.

## Модель данных (основное)

- **ПО** и **Оборудование** → **Средство** по **`id_средства`** (FK, `ON DELETE CASCADE`). В формах — выбор средства по id.
- **Сервер**: PK **`id_сервера`**; для CPU/vCPU/RAM/Disk заданы ограничения неотрицательности в DDL.
- **`permission_entities`**: справочник сущностей для прав (`code`, `sort_order`). Таблица **`Permissions`** хранит **`entity_id`**, **`UNIQUE(role_id, entity_id)`**. В коде проверка идёт по **`code`** (строки вроде `по`, `сервер`).
- На странице **`/permissions`** в матрице **не показывается** сущность с кодом **`permissions`** (управление правами остаётся за администратором через факт входа как admin); в БД у администратора при init выдаются все строки `permission_entities`, включая `permissions`.
- **Занятие**, **ПО**, **Оборудование**, **Сервер**, **Пользователи** и справочники имеют **`created_at`**; у перечисленных сущностей (кроме справочников без `updated_at` в DDL) поддерживается **`updated_at`** через триггер `trg_touch_updated_at`.
- У **Пользователи** нет **`Группа_доступа`**; доступ — **`role_id`** + **`Permissions`**.

## Роли приложения (начальные данные)

После [`01-schema.sql`](postgres/docker-entrypoint-initdb.d/01-schema.sql):

- **Администратор** — полные права на все коды из `permission_entities`.
- **Пользователь** — просмотр учебных сущностей без `пользователи` и без `permissions`.
- **Лаборант** — как в скрипте: расширенные операции по занятиям, средствам, ПО и оборудованию; без `пользователи` и `permissions`.

Учётные записи в init не создаются: первый админ — **`ADMIN_BOOTSTRAP_*`** или ручная вставка в `"Пользователи"`.

## Миграции и обновление живой БД

- **[`migrations/001_existing_database.sql`](migrations/001_existing_database.sql)** — для БД, у которой **DDL уже совпадает** с текущим [`01-schema.sql`](postgres/docker-entrypoint-initdb.d/01-schema.sql) (есть `permission_entities`, `Permissions.entity_id`, обновлённые `ПО`/`Оборудование`/`Сервер`/и т.д.). Дополняет/нормализует данные и ограничения (см. комментарии в файле).

  Пример запуска из корня проекта (важно: от пользователя **`postgres`** внутри контейнера, иначе peer-аутентификация по сокету отклонит подключение):

  ```bash
  docker compose exec -u postgres -T db psql -v ON_ERROR_STOP=1 -d university -f - < migrations/001_existing_database.sql
  ```

  Подставьте имя базы, если отличается от `university`.

- **[`postgres/upgrade-existing-database.sql`](postgres/upgrade-existing-database.sql)** — удалить лишние строки `Permissions` у «Пользователь»/«Лаборант» для кодов `пользователи` и `permissions`. Пример:

  ```bash
  docker compose exec -u postgres -T db psql -v ON_ERROR_STOP=1 -d university -f - < postgres/upgrade-existing-database.sql
  ```

- Переход со **старой** схемы (связи ПО/оборудования по текстовому названию, колонка `entity` в `Permissions` и т.д.) на новую без потери данных требует **отдельного** пошагового SQL: проще поднять чистый том (`down -v`) для dev; для прода — бэкап и согласованный план миграции.

- Роль приложения и **GRANT**: [`02-app-role.sh`](postgres/docker-entrypoint-initdb.d/02-app-role.sh).

## Локальная разработка без Nginx

1. PostgreSQL локально или только контейнер `db`.
2. По порядку: [`01-schema.sql`](postgres/docker-entrypoint-initdb.d/01-schema.sql) и [`02-app-role.sh`](postgres/docker-entrypoint-initdb.d/02-app-role.sh) (или временный доступ суперпользователя только для dev).
3. В каталоге `app/`:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   export DB_HOST=127.0.0.1 DB_NAME=university DB_USER=sibadi_app DB_PASS=... SECRET_KEY=...
   python app.py
   ```
   По умолчанию слушает `http://0.0.0.0:8080`.

## Разработка и GitHub

Рабочая ветка для проверки перед основной линией разработки: **`test`**.

```bash
git checkout main
git pull origin main
git checkout -b test   # если ветки ещё нет локально
# … изменения …
git add -A
git status
git commit -m "Краткое описание изменений"
git push -u origin test
```

Открыть PR из **`test`** в **`main`** можно через веб-интерфейс GitHub или CLI:

```bash
gh pr create --base main --head test --title "Заголовок" --body "Описание и план проверки."
```

Для **нового** репозитория (если истории ещё нет):

```bash
git init
git add .
git commit -m "Initial commit: Sibadi v4"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

## Безопасность (кратко)

- Отдельная роль БД с минимальными **GRANT**; приложение не подключается как суперпользователь.
- **pg_hba.conf**: SCRAM для TCP; доступ к БД с хоста ограничен отсутствием проброса порта по умолчанию.
- Пул соединений, таймауты, опциональный TLS (`PGSSLMODE` / `DB_SSLMODE`).
- CSRF на POST; пароли — Werkzeug; лимиты и **`LOGIN_BF_*`** на `/login`; **`ProxyFix`** под доверенным прокси.
- Ошибки БД при удалении не показываются клиенту (пишутся в лог сервера).
- Бэкапы: `pg_dump` / том `pgdata`. **`.env` не коммитить** (`chmod 600` на сервере).

## Устранение неполадок

| Симптом | Что проверить |
|---------|----------------|
| `Peer authentication failed for user "postgres"` при `docker compose exec db psql -U postgres` | Запускайте от пользователя ОС postgres в контейнере: **`docker compose exec -u postgres -T db psql ...`** или подключение по TCP **`psql -h 127.0.0.1 -U postgres`** с паролем из **`POSTGRES_PASSWORD`**. |
| Контейнер `db` не стартует после смены образа | Том смонтирован в **`/var/lib/postgresql`**. При конфликте данных — бэкап и **`docker compose down -v`** или `pg_upgrade`. |
| «APP_DB_USER не должен быть postgres» | В `.env`: **`DB_USER=sibadi_app`**. |
| Нет пароля первого админа | **`docker compose logs web`** после первого запроса при `ADMIN_BOOTSTRAP_ENABLED=false`. |
| Лимиты входа «плавают» между воркерами | **`RATE_LIMIT_STORAGE_URI=redis://…`**. **`LOGIN_BF_*`** остаются в памяти процесса. |

## Лицензия

Проект публикуется как есть; при открытой публикации добавьте файл `LICENSE` при необходимости.
