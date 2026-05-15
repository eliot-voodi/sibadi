-- Миграция для УЖЕ существующей БД (PostgreSQL), после приведения DDL к актуальной схеме приложения
-- (см. postgres/docker-entrypoint-initdb.d/01-schema.sql): таблицы permission_entities и Permissions(role_id, entity_id),
-- ПО/Оборудование со столбцом id_средства, Сервер.id_сервера, без столбца Группа_доступа в Пользователи.
-- Запуск (из корня проекта, контейнер db работает). Нужен пользователь ОС postgres внутри
-- контейнера (иначе локальный сокет даст peer authentication failed):
--   docker compose exec -u postgres -T db psql -v ON_ERROR_STOP=1 -d university -f - < migrations/001_existing_database.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) Роли (идемпотентно)
-- ---------------------------------------------------------------------------
INSERT INTO Roles (name) VALUES ('Администратор'), ('Пользователь'), ('Лаборант')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2) Права администратора, пользователя и лаборанта (как в postgres/docker-entrypoint-initdb.d/01-schema.sql)
-- ---------------------------------------------------------------------------
INSERT INTO Permissions (role_id, entity_id, can_view, can_create, can_edit, can_delete)
SELECT r.id, e.id, TRUE, TRUE, TRUE, TRUE
FROM Roles r
CROSS JOIN permission_entities e
WHERE r.name = 'Администратор'
ON CONFLICT (role_id, entity_id) DO NOTHING;

INSERT INTO Permissions (role_id, entity_id, can_view)
SELECT r.id, e.id, TRUE
FROM Roles r
JOIN permission_entities e ON e.code IN (
    'группа', 'дисциплина', 'преподаватель', 'средство', 'по',
    'оборудование', 'занятие', 'сервер'
)
WHERE r.name = 'Пользователь'
ON CONFLICT (role_id, entity_id) DO NOTHING;

INSERT INTO Permissions (role_id, entity_id, can_view, can_create, can_edit, can_delete)
SELECT r.id, e.id,
       TRUE,
       CASE WHEN e.code IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END,
       CASE WHEN e.code IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END,
       CASE WHEN e.code IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END
FROM Roles r
JOIN permission_entities e ON e.code IN (
    'группа', 'дисциплина', 'преподаватель', 'средство', 'по',
    'оборудование', 'занятие', 'сервер'
)
WHERE r.name = 'Лаборант'
ON CONFLICT (role_id, entity_id) DO UPDATE
SET can_view = EXCLUDED.can_view,
    can_create = EXCLUDED.can_create,
    can_edit = EXCLUDED.can_edit,
    can_delete = EXCLUDED.can_delete;

-- ---------------------------------------------------------------------------
-- 3) Данные Пользователи перед NOT NULL
-- ---------------------------------------------------------------------------
UPDATE Пользователи u
SET role_id = (SELECT id FROM Roles WHERE name = 'Пользователь' LIMIT 1)
WHERE u.role_id IS NULL;

UPDATE Пользователи
SET Login = ('migrated_user_' || id::text)
WHERE Login IS NULL OR btrim(Login) = '';

-- Пароль: для пустых полей подставляется хэш Werkzeug от временного пароля MustChangeNow
-- (сгенерировано werkzeug; пользователь должен сменить пароль после входа).
UPDATE Пользователи
SET Password = $mustchange$scrypt:32768:8:1$pgd6kwvVRVUIJAL6$5be40445ef9a39a8c0e970ee55433e0eb0c855cd7134a4a76cb09b5e73b6d2600d38e52ce753d169f2aa064b1e3693359240f9944c8ab095ef23575679c64799$mustchange$
WHERE Password IS NULL OR btrim(Password) = '';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM Пользователи
    WHERE Password IS NULL OR btrim(Password) = ''
  ) THEN
    RAISE EXCEPTION 'После подстановки placeholder-пароля остались пустые Password — проверьте данные вручную.';
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4) Ужесточение схемы Пользователи
-- ---------------------------------------------------------------------------
ALTER TABLE Пользователи ALTER COLUMN Login SET NOT NULL;
ALTER TABLE Пользователи ALTER COLUMN Password SET NOT NULL;
ALTER TABLE Пользователи ALTER COLUMN role_id SET NOT NULL;
ALTER TABLE Пользователи ALTER COLUMN role_id DROP DEFAULT;

COMMIT;
