-- Схема БД: нормализованные связи ПО/Оборудование → Средство по id,
-- справочник сущностей прав, индексы, аудит updated_at для ПО и Оборудования.

CREATE TABLE IF NOT EXISTS Группа (
    id_группы SERIAL PRIMARY KEY,
    название_группы VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Дисциплина (
    id_дисциплины SERIAL PRIMARY KEY,
    название_дисциплины VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Преподаватель (
    id_преподавателя SERIAL PRIMARY KEY,
    Фамилия VARCHAR(100) NOT NULL,
    Имя VARCHAR(100) NOT NULL,
    Отчество VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Средство (
    id_средства SERIAL PRIMARY KEY,
    Название VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ПО (
    id_ПО SERIAL PRIMARY KEY,
    id_средства INTEGER NOT NULL REFERENCES Средство(id_средства) ON DELETE CASCADE,
    Описание VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Оборудование (
    id_Оборудования SERIAL PRIMARY KEY,
    id_средства INTEGER NOT NULL REFERENCES Средство(id_средства) ON DELETE CASCADE,
    Описание VARCHAR(255),
    Инвентарный_номер VARCHAR(255),
    Сертификат_ФСТЭК BOOLEAN,
    Наличие BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Занятие (
    id_занятия SERIAL PRIMARY KEY,
    id_преподавателя INTEGER REFERENCES Преподаватель(id_преподавателя),
    id_группы INTEGER REFERENCES Группа(id_группы),
    id_дисциплины INTEGER REFERENCES Дисциплина(id_дисциплины),
    Семестр INTEGER CHECK (Семестр >= 1 AND Семестр <= 12),
    id_средства INTEGER REFERENCES Средство(id_средства),
    Описание VARCHAR(255),
    Дата DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Сервер (
    id_сервера SERIAL PRIMARY KEY,
    Расположение VARCHAR(255),
    CPU INTEGER CHECK (CPU IS NULL OR CPU >= 0),
    vCPU INTEGER CHECK (vCPU IS NULL OR vCPU >= 0),
    RAM INTEGER CHECK (RAM IS NULL OR RAM >= 0),
    Disk INTEGER CHECK (Disk IS NULL OR Disk >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS permission_entities (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

INSERT INTO permission_entities (code, sort_order) VALUES
  ('группа', 10),
  ('дисциплина', 20),
  ('преподаватель', 30),
  ('средство', 40),
  ('по', 50),
  ('оборудование', 60),
  ('занятие', 70),
  ('сервер', 80),
  ('пользователи', 90),
  ('permissions', 100)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS Пользователи (
    id SERIAL PRIMARY KEY,
    Имя VARCHAR(100),
    Фамилия VARCHAR(100),
    Login VARCHAR(255) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL,
    role_id INTEGER NOT NULL REFERENCES Roles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS Permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER REFERENCES Roles(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES permission_entities(id),
    can_view BOOLEAN DEFAULT TRUE,
    can_create BOOLEAN DEFAULT FALSE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    UNIQUE(role_id, entity_id)
);

-- Индексы для типичных запросов и FK
CREATE INDEX IF NOT EXISTS idx_занятие_группа ON Занятие(id_группы);
CREATE INDEX IF NOT EXISTS idx_занятие_дисциплина ON Занятие(id_дисциплины);
CREATE INDEX IF NOT EXISTS idx_занятие_преподаватель ON Занятие(id_преподавателя);
CREATE INDEX IF NOT EXISTS idx_занятие_средство ON Занятие(id_средства);
CREATE INDEX IF NOT EXISTS idx_занятие_дата ON Занятие(Дата DESC);
CREATE INDEX IF NOT EXISTS idx_занятие_семестр ON Занятие(Семестр);
CREATE INDEX IF NOT EXISTS idx_permissions_role_entity ON Permissions(role_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_по_средство ON ПО(id_средства);
CREATE INDEX IF NOT EXISTS idx_оборудование_средство ON Оборудование(id_средства);

-- Автообновление updated_at для Занятие, ПО, Оборудование, Сервер, Пользователи
CREATE OR REPLACE FUNCTION trg_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_занятие_updated ON Занятие;
CREATE TRIGGER trg_занятие_updated
    BEFORE UPDATE ON Занятие
    FOR EACH ROW EXECUTE PROCEDURE trg_touch_updated_at();

DROP TRIGGER IF EXISTS trg_по_updated ON ПО;
CREATE TRIGGER trg_по_updated
    BEFORE UPDATE ON ПО
    FOR EACH ROW EXECUTE PROCEDURE trg_touch_updated_at();

DROP TRIGGER IF EXISTS trg_оборудование_updated ON Оборудование;
CREATE TRIGGER trg_оборудование_updated
    BEFORE UPDATE ON Оборудование
    FOR EACH ROW EXECUTE PROCEDURE trg_touch_updated_at();

DROP TRIGGER IF EXISTS trg_сервер_updated ON Сервер;
CREATE TRIGGER trg_сервер_updated
    BEFORE UPDATE ON Сервер
    FOR EACH ROW EXECUTE PROCEDURE trg_touch_updated_at();

DROP TRIGGER IF EXISTS trg_пользователи_updated ON "Пользователи";
CREATE TRIGGER trg_пользователи_updated
    BEFORE UPDATE ON "Пользователи"
    FOR EACH ROW EXECUTE PROCEDURE trg_touch_updated_at();

-- Роли приложения
INSERT INTO Roles (name) VALUES ('Администратор'), ('Пользователь'), ('Лаборант')
ON CONFLICT (name) DO NOTHING;

-- Полные права администратору
INSERT INTO Permissions (role_id, entity_id, can_view, can_create, can_edit, can_delete)
SELECT r.id, e.id, TRUE, TRUE, TRUE, TRUE
FROM Roles r
CROSS JOIN permission_entities e
WHERE r.name = 'Администратор'
ON CONFLICT (role_id, entity_id) DO NOTHING;

-- Пользователь: только учебные сущности (без пользователей и permissions)
INSERT INTO Permissions (role_id, entity_id, can_view)
SELECT r.id, e.id, TRUE
FROM Roles r
JOIN permission_entities e ON e.code IN (
    'группа', 'дисциплина', 'преподаватель', 'средство', 'по',
    'оборудование', 'занятие', 'сервер'
)
WHERE r.name = 'Пользователь'
ON CONFLICT (role_id, entity_id) DO NOTHING;

-- Лаборант
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
