CREATE TABLE IF NOT EXISTS Группа (
    id_группы SERIAL PRIMARY KEY,
    название_группы VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS Дисциплина (
    id_дисциплины SERIAL PRIMARY KEY,
    название_дисциплины VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS Преподаватель (
    id_преподавателя SERIAL PRIMARY KEY,
    Фамилия VARCHAR(100) NOT NULL,
    Имя VARCHAR(100) NOT NULL,
    Отчество VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS Средство (
    id_средства SERIAL PRIMARY KEY,
    Название VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ПО (
    id_ПО SERIAL PRIMARY KEY,
    Название VARCHAR(255),
    Описание VARCHAR(255),
    FOREIGN KEY(Название) REFERENCES Средство(Название) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Оборудование (
    id_Оборудования SERIAL PRIMARY KEY,
    Название VARCHAR(255),
    Описание VARCHAR(255),
    Инвентарный_номер VARCHAR(255),
    Сертификат_ФСТЭК BOOLEAN,
    Наличие BOOLEAN,
    FOREIGN KEY(Название) REFERENCES Средство(Название) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Занятие (
    id_занятия SERIAL PRIMARY KEY,
    id_преподавателя INTEGER REFERENCES Преподаватель(id_преподавателя),
    id_группы INTEGER REFERENCES Группа(id_группы),
    id_дисциплины INTEGER REFERENCES Дисциплина(id_дисциплины),
    Семестр INTEGER CHECK (Семестр >= 1 AND Семестр <= 12),
    id_средства INTEGER REFERENCES Средство(id_средства),
    Описание VARCHAR(255),
    Дата DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS Сервер (
    id SERIAL PRIMARY KEY,
    Расположение VARCHAR(255),
    CPU INTEGER,
    vCPU INTEGER,
    RAM INTEGER,
    Disk INTEGER
);

CREATE TABLE IF NOT EXISTS Roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS Пользователи (
    id SERIAL PRIMARY KEY,
    Имя VARCHAR(100),
    Фамилия VARCHAR(100),
    Login VARCHAR(255) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL,
    Группа_доступа VARCHAR(255),
    role_id INTEGER NOT NULL REFERENCES Roles(id)
);

CREATE TABLE IF NOT EXISTS Permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER REFERENCES Roles(id) ON DELETE CASCADE,
    entity VARCHAR(50) NOT NULL,
    can_view BOOLEAN DEFAULT TRUE,
    can_create BOOLEAN DEFAULT FALSE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    UNIQUE(role_id, entity)
);

-- Роли
INSERT INTO Roles (name) VALUES ('Администратор'), ('Пользователь'), ('Лаборант') 
ON CONFLICT (name) DO NOTHING;

-- Полные права администратору
INSERT INTO Permissions (role_id, entity, can_view, can_create, can_edit, can_delete)
SELECT r.id, e.entity, TRUE, TRUE, TRUE, TRUE
FROM Roles r, (VALUES 
  ('группа'), ('дисциплина'), ('преподаватель'), ('средство'), ('по'), 
  ('оборудование'), ('занятие'), ('сервер'), ('пользователи'), ('permissions')
) AS e(entity)
WHERE r.name = 'Администратор'
ON CONFLICT DO NOTHING;

-- Только просмотр обычному пользователю
INSERT INTO Permissions (role_id, entity, can_view)
SELECT r.id, e.entity, TRUE
FROM Roles r, (VALUES 
  ('группа'), ('дисциплина'), ('преподаватель'), ('средство'), ('по'), 
  ('оборудование'), ('занятие'), ('сервер'), ('пользователи'), ('permissions')
) AS e(entity)
WHERE r.name = 'Пользователь'
ON CONFLICT DO NOTHING;

-- Права для лаборанта (role_id = 3)
INSERT INTO Permissions (role_id, entity, can_view, can_create, can_edit, can_delete)
SELECT r.id, e.entity,
       TRUE,
       CASE WHEN e.entity IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END,
       CASE WHEN e.entity IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END,
       CASE WHEN e.entity IN ('занятие', 'средство', 'по', 'оборудование') THEN TRUE ELSE FALSE END
FROM Roles r,
     (VALUES 
  ('группа'), ('дисциплина'), ('преподаватель'), ('средство'), ('по'), 
  ('оборудование'), ('занятие'), ('сервер'), ('пользователи'), ('permissions')
) AS e(entity)
WHERE r.name = 'Лаборант'
ON CONFLICT (role_id, entity) DO UPDATE
SET can_view = EXCLUDED.can_view,
    can_create = EXCLUDED.can_create,
    can_edit = EXCLUDED.can_edit,
    can_delete = EXCLUDED.can_delete;
