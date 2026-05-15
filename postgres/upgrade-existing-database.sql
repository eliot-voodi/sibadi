-- Обновление существующей БД: убрать у ролей «Пользователь» и «Лаборант»
-- лишние права на сущности «пользователи» и «permissions» (как в 01-schema.sql).
-- Выполнить от суперпользователя БД после резервной копии.
--
-- С хоста, Docker Compose (рекомендуется):
--   docker compose exec -u postgres -T db psql -v ON_ERROR_STOP=1 -d university -f - < postgres/upgrade-existing-database.sql
--
-- Локальный psql к проброшенному порту:
--   psql -h 127.0.0.1 -U postgres -d university -v ON_ERROR_STOP=1 -f postgres/upgrade-existing-database.sql
--
-- Отдельная роль приложения с ограниченными GRANT: см. postgres/docker-entrypoint-initdb.d/02-app-role.sh
-- (на уже заполненном томе её нужно выполнить вручную или восстановить из бэкапа с новым init).

BEGIN;

DELETE FROM Permissions AS p
USING Roles AS r, permission_entities AS e
WHERE p.role_id = r.id
  AND p.entity_id = e.id
  AND r.name IN ('Пользователь', 'Лаборант')
  AND e.code IN ('пользователи', 'permissions');

COMMIT;
