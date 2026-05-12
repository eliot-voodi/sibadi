# Учебная инфраструктура (Sibadi v4)

Веб-приложение для учёта учебной и лабораторной инфраструктуры: группы, дисциплины, преподаватели, средства, ПО, оборудование, занятия, серверы и пользователи. Ролевая модель с гибкими правами на сущности, экспорт расписания занятий в Excel.

## Стек

- **Backend:** Python 3.11, Flask 3.1, psycopg2  
- **БД:** PostgreSQL (в Compose — образ `postgres:18`)  
- **Фронт:** Jinja2-шаблоны, статика через CDN  
- **Прод-обвязка:** Docker Compose, Nginx (TLS, reverse proxy к Flask)  
- **Экспорт:** OpenPyXL (.xlsx)

## Структура репозитория

```
├── docker-compose.yml      # db + web + nginx
├── .env.example            # образец переменных окружения (скопировать в .env)
├── init-db.sql             # схема БД и начальные роли/права
├── migrations/
│   └── 001_existing_database.sql   # миграция для уже существующей БД
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py              # маршруты и логика
│   ├── config.py
│   ├── database.py
│   ├── security.py
│   └── templates/
└── nginx/
    ├── Dockerfile
    ├── nginx.conf
    └── entrypoint.sh       # генерация самоподписанного сертификата при старте
```

## Быстрый старт (Docker Compose)

1. Склонируйте репозиторий и перейдите в корень проекта.

2. Создайте файл окружения:
   ```bash
   cp .env.example .env
   ```

3. Отредактируйте `.env`: задайте надёжные `DB_PASS` и `SECRET_KEY`. Для **первого** входа в систему включите создание администратора:
   ```env
   ADMIN_BOOTSTRAP_ENABLED=true
   ADMIN_BOOTSTRAP_PASSWORD=your_strong_password_here
   ```
   После первого успешного входа рекомендуется выставить `ADMIN_BOOTSTRAP_ENABLED=false` и перезапустить контейнер `web`.

4. Соберите и запустите:
   ```bash
   docker compose up -d --build
   ```

5. Откройте в браузере **HTTPS**, порт проброшен на хосте как **8082**:
   - `https://localhost:8082/` (или `https://<IP-сервера>:8082/`)

HTTP-порт **8081** переводится на HTTPS (редирект 301).

> Самоподписанный сертификат генерируется при первом старте Nginx (`SSL_CN` в `.env`, по умолчанию `localhost`). Браузер покажет предупреждение — это ожидаемо до замены на сертификат от вашего ЦС.

## Переменные окружения

| Переменная | Описание |
|------------|-----------|
| `DB_NAME`, `DB_USER`, `DB_PASS` | Параметры PostgreSQL для сервисов `db` и `web`. |
| `SECRET_KEY` | Секрет сессий Flask; должен быть стабильным между перезапусками в продакшене. |
| `ADMIN_BOOTSTRAP_ENABLED` | `true`/`false` — включить автосоздание первого пользователя с ролью «Администратор». |
| `ADMIN_BOOTSTRAP_LOGIN` | Логин bootstrap-администратора (по умолчанию `admin`). |
| `ADMIN_BOOTSTRAP_PASSWORD` | Пароль bootstrap-администратора (обязателен при включённом bootstrap). |
| `SSL_CN` | CN для самоподписанного TLS-сертификата Nginx. |

Переменные `DB_*` и `SECRET_KEY` для сервиса `web` задаются через Compose из `.env` или окружения хоста.

## Порты Compose

| Порт хоста | Назначение |
|------------|------------|
| 8083 | HTTP → редирект на HTTPS |
| 8084 | HTTPS, прокси на Flask (:8080 внутри сети) |

Прямой доступ к PostgreSQL с хоста по умолчанию **выключен** (секция `ports` у `db` закомментирована). При необходимости раскомментируйте `5432:5432` в `docker-compose.yml`.

## Основные URL приложения

- `/` — главная  
- `/login`, `/logout` — вход / выход  
- `/healthz` — проверка «живости» сервиса (JSON `{ "status": "ok" }`)  
- `/группа`, `/дисциплина`, `/преподаватель`, `/средство`, `/по`, `/оборудование`, `/занятие`, `/сервер`, `/пользователи` — CRUD по сущностям  
- `/permissions` — настройка прав по ролям (только **Администратор**)  
- `/занятия_пользователь` — просмотр занятий с фильтрами (`group`, `disc`, `kurs`)  
- `/занятия_пользователь_export` — выгрузка в Excel с теми же фильтрами  

Удаление записей выполняется отдельным POST на `/<сущность>/delete/<id>`.

## Роли по умолчанию (из `init-db.sql`)

После первой инициализации БД создаются роли:

- **Администратор** — полные права на все сущности и страницу прав.  
- **Пользователь** — в основном просмотр.  
- **Лаборант** — расширенные create/edit/delete на занятия, средства, ПО и оборудование.

Строк пользователей в `init-db.sql` нет: первый вход — через bootstrap либо ручную вставку в таблицу `"Пользователи"`.

## Миграция существующей базы данных

Если у вас уже есть PostgreSQL с прежней схемой, см. комментарий в начале файла [`migrations/001_existing_database.sql`](migrations/001_existing_database.sql) и выполните скрипт через `psql` (пример для Compose):

```bash
docker compose exec -T db psql -U postgres -d university -v ON_ERROR_STOP=1 < migrations/001_existing_database.sql
```

Имя БД замените на своё при необходимости.

## Локальная разработка без Nginx

1. Установите PostgreSQL локально или поднимите только контейнер БД.  
2. Выполните `init-db.sql` один раз в вашей базе.  
3. В каталоге `app/`:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   export DB_HOST=127.0.0.1 DB_NAME=university DB_USER=postgres DB_PASS=... SECRET_KEY=...
   python app.py
   ```
   Приложение слушает `http://0.0.0.0:8080`.

## Безопасность

- Пароли хранятся в виде хэша Werkzeug.  
- Для всех POST-запросов проверяется CSRF-токен в форме (`security.py`).  
- Не коммитьте файл `.env` — он добавлен в `.gitignore`; в репозитории есть только `.env.example`.

## Публикация на GitHub

На машине с установленным Git:

```bash
cd /path/to/sibadi_v4
git init
git add .
git commit -m "Initial commit: учебная инфраструктура, Docker Compose"
git branch -M main
git remote add origin https://github.com/<USERNAME>/<REPO>.git
git push -u origin main
```

Создайте пустой репозиторий на GitHub и подставьте свой URL в `git remote add origin`.

## Лицензия

Проект публикуется как есть; при добавлении в открытый репозиторий имеет смысл указать лицензию отдельно — при необходимости добавьте файл `LICENSE` под вашей организацией.
