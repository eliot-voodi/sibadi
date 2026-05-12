from flask import Flask, render_template, request, redirect, url_for, flash, session, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from psycopg2 import sql
from flask import send_file
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font
from datetime import datetime
import logging
from config import get_secret_key, get_db_config, get_admin_bootstrap_config
from database import init_db
from security import init_security, has_permission, before_request_setup, inject_admin

app = Flask(__name__)
app.secret_key = get_secret_key()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _optional_query_int(val):
    """Безопасное целое из query string: только цифры, иначе None (для фильтров вместе с %s)."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _optional_form_fk(val):
    """Необязательный FK из формы: пусто → None, иначе положительное int или ValueError."""
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    try:
        i = int(val)
    except (ValueError, TypeError) as exc:
        raise ValueError("Некорректный идентификатор") from exc
    if i < 1:
        raise ValueError("Некорректный идентификатор")
    return i

get_db, close_db = init_db(get_db_config())
init_security(get_db, get_admin_bootstrap_config())
app.teardown_appcontext(close_db)
app.before_request(before_request_setup)
app.context_processor(inject_admin)

# ==================== АВТОРИЗАЦИЯ ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_val = request.form['Login']
        password = request.form['Password']
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, Password, role_id FROM "Пользователи" WHERE Login = %s', (login_val,))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['role_id'] = user[2]
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/healthz')
def healthz():
    return {"status": "ok"}, 200

# ==================== ВСПОМОГАТЕЛЬНЫЕ ДАННЫЕ ====================
def get_common_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id_группы, название_группы FROM Группа ORDER BY название_группы")
    группы = cur.fetchall() or []
    cur.execute("SELECT id_дисциплины, название_дисциплины FROM Дисциплина ORDER BY название_дисциплины")
    дисциплины = cur.fetchall() or []
    cur.execute("SELECT id_преподавателя, TRIM(Фамилия || ' ' || Имя || COALESCE(' ' || Отчество, '')) FROM Преподаватель ORDER BY Фамилия")
    преподаватели = cur.fetchall() or []
    cur.execute("SELECT id_средства, Название FROM Средство ORDER BY Название")
    средства = cur.fetchall() or []
    cur.close()
    return {
        'группы': группы,
        'дисциплины': дисциплины,
        'преподаватели': преподаватели,
        'средства': средства
    }

# ==================== УДАЛЕНИЕ ====================
def register_delete_route(entity, table_name, pk_name):
    allowed_deletes = {
        'группа': ('Группа', 'id_группы'),
        'дисциплина': ('Дисциплина', 'id_дисциплины'),
        'преподаватель': ('Преподаватель', 'id_преподавателя'),
        'средство': ('Средство', 'id_средства'),
        'по': ('ПО', 'id_ПО'),
        'оборудование': ('Оборудование', 'id_Оборудования'),
        'занятие': ('Занятие', 'id_занятия'),
        'сервер': ('Сервер', 'id'),
        'пользователи': ('Пользователи', 'id'),
    }

    if entity not in allowed_deletes:
        raise ValueError(f"Unsupported entity for delete route: {entity}")

    safe_table, safe_pk = allowed_deletes[entity]
    if table_name != safe_table or pk_name != safe_pk:
        raise ValueError(f"Invalid delete mapping for entity: {entity}")

    # Уникальное имя endpoint на основе entity
    endpoint_name = f'delete_{entity}'

    @app.route(f'/{entity}/delete/<int:item_id>', methods=['POST'], endpoint=endpoint_name)
    def delete_handler(item_id):
        if not has_permission(entity, 'delete'):
            abort(403)
        conn = get_db()
        cur = conn.cursor()
        try:
            query = sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                sql.Identifier(table_name),
                sql.Identifier(pk_name),
            )
            cur.execute(query, (item_id,))
            conn.commit()
            flash('Запись успешно удалена', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Ошибка при удалении: {str(e)}', 'error')
        finally:
            cur.close()
        return redirect(url_for(entity))

    # Присваиваем уникальное имя функции (опционально, для отладки)
    delete_handler.__name__ = endpoint_name

register_delete_route('группа', 'Группа', 'id_группы')
register_delete_route('дисциплина', 'Дисциплина', 'id_дисциплины')
register_delete_route('преподаватель', 'Преподаватель', 'id_преподавателя')
register_delete_route('средство', 'Средство', 'id_средства')
register_delete_route('по', 'ПО', 'id_ПО')
register_delete_route('оборудование', 'Оборудование', 'id_Оборудования')
register_delete_route('занятие', 'Занятие', 'id_занятия')
register_delete_route('сервер', 'Сервер', 'id')
register_delete_route('пользователи', 'Пользователи', 'id')

# ==================== CRUD РОУТЫ ====================

# Группы
@app.route('/группа', methods=['GET', 'POST'])
@app.route('/группа/<int:item_id>', methods=['GET', 'POST'])
def группа(item_id=None):
    entity = 'группа'
    if not has_permission(entity, 'view'):
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        название = request.form['название_группы'].strip()
        if item_id:
            cur.execute("UPDATE Группа SET название_группы = %s WHERE id_группы = %s", (название, item_id))
            flash('Группа обновлена', 'success')
        else:
            cur.execute("INSERT INTO Группа (название_группы) VALUES (%s)", (название,))
            flash('Группа добавлена', 'success')
        conn.commit()
        cur.close()
        return redirect(url_for('группа'))

    item = None
    if item_id:
        cur.execute("SELECT id_группы, название_группы FROM Группа WHERE id_группы = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT id_группы, название_группы FROM Группа ORDER BY id_группы")
    data = cur.fetchall()
    cur.close()

    return render_template('группа.html', data=data, item=item,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Дисциплины
@app.route('/дисциплина', methods=['GET', 'POST'])
@app.route('/дисциплина/<int:item_id>', methods=['GET', 'POST'])
def дисциплина(item_id=None):
    entity = 'дисциплина'
    if not has_permission(entity, 'view'):
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        название = request.form['название_дисциплины'].strip()
        if item_id:
            cur.execute("UPDATE Дисциплина SET название_дисциплины = %s WHERE id_дисциплины = %s", (название, item_id))
            flash('Дисциплина обновлена', 'success')
        else:
            cur.execute("INSERT INTO Дисциплина (название_дисциплины) VALUES (%s)", (название,))
            flash('Дисциплина добавлена', 'success')
        conn.commit()
        return redirect(url_for('дисциплина'))

    item = None
    if item_id:
        cur.execute("SELECT id_дисциплины, название_дисциплины FROM Дисциплина WHERE id_дисциплины = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT id_дисциплины, название_дисциплины FROM Дисциплина ORDER BY id_дисциплины")
    data = cur.fetchall()
    cur.close()

    return render_template('дисциплина.html', data=data, item=item,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Преподаватели
@app.route('/преподаватель', methods=['GET', 'POST'])
@app.route('/преподаватель/<int:item_id>', methods=['GET', 'POST'])
def преподаватель(item_id=None):
    entity = 'преподаватель'
    if not has_permission(entity, 'view'):
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        фамилия = request.form['Фамилия'].strip()
        имя = request.form['Имя'].strip()
        отчество = request.form.get('Отчество', '').strip() or None

        if item_id:
            cur.execute("UPDATE Преподаватель SET Фамилия = %s, Имя = %s, Отчество = %s WHERE id_преподавателя = %s",
                        (фамилия, имя, отчество, item_id))
            flash('Преподаватель обновлён', 'success')
        else:
            cur.execute("INSERT INTO Преподаватель (Фамилия, Имя, Отчество) VALUES (%s, %s, %s)",
                        (фамилия, имя, отчество))
            flash('Преподаватель добавлен', 'success')
        conn.commit()
        return redirect(url_for('преподаватель'))

    item = None
    if item_id:
        cur.execute("SELECT id_преподавателя, Фамилия, Имя, Отчество FROM Преподаватель WHERE id_преподавателя = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT id_преподавателя, Фамилия, Имя, Отчество FROM Преподаватель ORDER BY Фамилия, Имя")
    data = cur.fetchall()
    cur.close()

    return render_template('преподаватель.html', data=data, item=item,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Средства
@app.route('/средство', methods=['GET', 'POST'])
@app.route('/средство/<int:item_id>', methods=['GET', 'POST'])
def средство(item_id=None):
    entity = 'средство'
    if not has_permission(entity, 'view'):
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        название = request.form['Название'].strip()
        if item_id:
            cur.execute("UPDATE Средство SET Название = %s WHERE id_средства = %s", (название, item_id))
        else:
            cur.execute("INSERT INTO Средство (Название) VALUES (%s) ON CONFLICT (Название) DO NOTHING", (название,))
        conn.commit()
        flash('Средство сохранено', 'success')
        return redirect(url_for('средство'))

    item = None
    if item_id:
        cur.execute("SELECT id_средства, Название FROM Средство WHERE id_средства = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT id_средства, Название FROM Средство ORDER BY Название")
    data = cur.fetchall()
    cur.close()

    return render_template('средство.html', data=data, item=item,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# ПО
@app.route('/по', methods=['GET', 'POST'])
@app.route('/по/<int:item_id>', methods=['GET', 'POST'])
def по(item_id=None):
    entity = 'по'
    if not has_permission(entity, 'view'):
        abort(403)

    common = get_common_data()
    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        название = request.form['Название']
        описание = request.form.get('Описание', '').strip() or None

        if item_id:
            cur.execute("UPDATE ПО SET Название = %s, Описание = %s WHERE id_ПО = %s", (название, описание, item_id))
            flash('ПО обновлено', 'success')
        else:
            cur.execute("INSERT INTO ПО (Название, Описание) VALUES (%s, %s)", (название, описание))
            flash('ПО добавлено', 'success')
        conn.commit()
        return redirect(url_for('по'))

    item = None
    if item_id:
        cur.execute("SELECT id_ПО, Название, Описание FROM ПО WHERE id_ПО = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT p.id_ПО, s.Название, p.Описание FROM ПО p JOIN Средство s ON p.Название = s.Название ORDER BY p.id_ПО")
    data = cur.fetchall()
    cur.close()

    return render_template('по.html', data=data, item=item, средства=common['средства'],
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Оборудование
@app.route('/оборудование', methods=['GET', 'POST'])
@app.route('/оборудование/<int:item_id>', methods=['GET', 'POST'])
def оборудование(item_id=None):
    entity = 'оборудование'
    if not has_permission(entity, 'view'):
        abort(403)

    common = get_common_data()
    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        название = request.form['Название']
        описание = request.form.get('Описание', '').strip() or None
        инв_номер = request.form.get('Инвентарный_номер', '').strip() or None
        фстэк = 'Сертификат_ФСТЭК' in request.form
        наличие = 'Наличие' in request.form

        if item_id:
            cur.execute("""UPDATE Оборудование SET Название = %s, Описание = %s, Инвентарный_номер = %s,
                           Сертификат_ФСТЭК = %s, Наличие = %s WHERE id_Оборудования = %s""",
                        (название, описание, инв_номер, фстэк, наличие, item_id))
            flash('Оборудование обновлено', 'success')
        else:
            cur.execute("""INSERT INTO Оборудование (Название, Описание, Инвентарный_номер, Сертификат_ФСТЭК, Наличие)
                           VALUES (%s, %s, %s, %s, %s)""", (название, описание, инв_номер, фстэк, наличие))
            flash('Оборудование добавлено', 'success')
        conn.commit()
        return redirect(url_for('оборудование'))

    item = None
    if item_id:
        cur.execute("""SELECT id_Оборудования, Название, Описание, Инвентарный_номер, Сертификат_ФСТЭК, Наличие
                       FROM Оборудование WHERE id_Оборудования = %s""", (item_id,))
        item = cur.fetchone()

    cur.execute("""SELECT o.id_Оборудования, s.Название, o.Описание, o.Инвентарный_номер,
                   o.Сертификат_ФСТЭК, o.Наличие
                   FROM Оборудование o JOIN Средство s ON o.Название = s.Название ORDER BY o.id_Оборудования""")
    data = cur.fetchall()
    cur.close()

    return render_template('оборудование.html', data=data, item=item, средства=common['средства'],
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Занятия
@app.route('/занятие', methods=['GET', 'POST'])
@app.route('/занятие/<int:item_id>', methods=['GET', 'POST'])
def занятие(item_id=None):
    entity = 'занятие'
    if not has_permission(entity, 'view'):
        abort(403)

    common = get_common_data()
    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        try:
            prep = _optional_form_fk(request.form.get('id_преподавателя'))
            group = _optional_form_fk(request.form.get('id_группы'))
            disc = _optional_form_fk(request.form.get('id_дисциплины'))
            sred = _optional_form_fk(request.form.get('id_средства'))
        except ValueError:
            flash('Некорректные идентификаторы в форме', 'error')
            return redirect(url_for('занятие', item_id=item_id) if item_id else url_for('занятие'))

        sem = request.form['Семестр']
        desc = request.form.get('Описание', '').strip() or None
        date = request.form['Дата']

        if item_id:
            cur.execute("""UPDATE Занятие SET id_преподавателя = %s, id_группы = %s, id_дисциплины = %s,
                           Семестр = %s, id_средства = %s, Описание = %s, Дата = %s
                           WHERE id_занятия = %s""",
                        (prep, group, disc, sem, sred, desc, date, item_id))
            flash('Занятие обновлено', 'success')
        else:
            cur.execute("""INSERT INTO Занятие (id_преподавателя, id_группы, id_дисциплины, Семестр,
                           id_средства, Описание, Дата)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (prep, group, disc, sem, sred, desc, date))
            flash('Занятие добавлено', 'success')
        conn.commit()
        return redirect(url_for('занятие'))

    item = None
    if item_id:
        cur.execute("""SELECT id_занятия, id_преподавателя, id_группы, id_дисциплины, Семестр,
                       id_средства, Описание, Дата FROM Занятие WHERE id_занятия = %s""", (item_id,))
        item = cur.fetchone()

    cur.execute("""SELECT z.id_занятия,
                          TRIM(p.Фамилия || ' ' || p.Имя || COALESCE(' ' || p.Отчество, '')) as prep,
                          g.название_группы,
                          d.название_дисциплины,
                          z.Семестр,
                          s.Название as sredstvo,
                          z.Описание,
                          z.Дата
                   FROM Занятие z
                   LEFT JOIN Преподаватель p ON z.id_преподавателя = p.id_преподавателя
                   LEFT JOIN Группа g ON z.id_группы = g.id_группы
                   LEFT JOIN Дисциплина d ON z.id_дисциплины = d.id_дисциплины
                   LEFT JOIN Средство s ON z.id_средства = s.id_средства
                   ORDER BY z.id_занятия""")
    data = cur.fetchall()
    cur.close()

    return render_template('занятие.html', data=data, item=item, common=common,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Серверы
@app.route('/сервер', methods=['GET', 'POST'])
@app.route('/сервер/<int:item_id>', methods=['GET', 'POST'])
def сервер(item_id=None):
    entity = 'сервер'
    if not has_permission(entity, 'view'):
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        if item_id and not has_permission(entity, 'edit'):
            abort(403)
        if not item_id and not has_permission(entity, 'create'):
            abort(403)

        расположение = request.form['Расположение'].strip() or None
        cpu = request.form.get('CPU') or None
        vcpu = request.form.get('vCPU') or None
        ram = request.form.get('RAM') or None
        disk = request.form.get('Disk') or None

        if item_id:
            cur.execute("""UPDATE Сервер SET Расположение = %s, CPU = %s, vCPU = %s, RAM = %s, Disk = %s
                           WHERE id = %s""", (расположение, cpu, vcpu, ram, disk, item_id))
            flash('Сервер обновлён', 'success')
        else:
            cur.execute("INSERT INTO Сервер (Расположение, CPU, vCPU, RAM, Disk) VALUES (%s, %s, %s, %s, %s)",
                        (расположение, cpu, vcpu, ram, disk))
            flash('Сервер добавлен', 'success')
        conn.commit()
        return redirect(url_for('сервер'))

    item = None
    if item_id:
        cur.execute("SELECT id, Расположение, CPU, vCPU, RAM, Disk FROM Сервер WHERE id = %s", (item_id,))
        item = cur.fetchone()

    cur.execute("SELECT id, Расположение, CPU, vCPU, RAM, Disk FROM Сервер ORDER BY id")
    data = cur.fetchall()
    cur.close()

    return render_template('сервер.html', data=data, item=item,
                           can_create=has_permission(entity, 'create'),
                           can_edit=has_permission(entity, 'edit'),
                           can_delete=has_permission(entity, 'delete'))

# Пользователи (только admin может редактировать пароли и роли)
@app.route('/пользователи', methods=['GET', 'POST'])
@app.route('/пользователи/<int:id>', methods=['GET', 'POST'])
def пользователи(id=None):
    if g.user is None:
        return redirect(url_for('login'))

    # Проверка прав — предполагаем, что используете has_permission
    entity = 'пользователи'
    can_view = has_permission(entity, 'view')
    can_create = has_permission(entity, 'create')
    can_edit = has_permission(entity, 'edit')
    can_delete = has_permission(entity, 'delete')

    if not can_view:
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    # ВСЕГДА загружаем список ролей для формы
    cur.execute("SELECT id, name FROM Roles ORDER BY id")
    roles = cur.fetchall()
    role_ids = {role[0] for role in roles}

    cur.execute("SELECT id FROM Roles WHERE name = 'Пользователь'")
    default_role = cur.fetchone()
    default_role_id = default_role[0] if default_role else None

    item = None

    if request.method == 'POST':
        name = request.form['Имя']
        surname = request.form['Фамилия']
        login = request.form['Login']
        password = request.form.get('Password')

        # role_id может отсутствовать только если кто-то подделал форму — поставим default роль "Пользователь" из БД
        role_id = request.form.get('role_id')
        if role_id:
            try:
                role_id = int(role_id)
            except ValueError:
                role_id = default_role_id
        else:
            role_id = default_role_id

        if role_id not in role_ids:
            flash('Выбрана недопустимая роль', 'error')
            return redirect(url_for('пользователи'))

        if id:  # Редактирование
            if not can_edit:
                abort(403)

            if password:  # Если пароль указан — хэшируем
                hashed = generate_password_hash(password)
                cur.execute("""
                    UPDATE "Пользователи"
                    SET Имя=%s, Фамилия=%s, Login=%s, Password=%s, role_id=%s
                    WHERE id=%s
                """, (name, surname, login, hashed, role_id, id))
            else:  # Пароль не меняем
                cur.execute("""
                    UPDATE "Пользователи"
                    SET Имя=%s, Фамилия=%s, Login=%s, role_id=%s
                    WHERE id=%s
                """, (name, surname, login, role_id, id))

            flash('Пользователь обновлён', 'success')
        else:  # Создание
            if not can_create:
                abort(403)

            if not password:
                flash('Пароль обязателен при создании', 'error')
                return redirect(url_for('пользователи'))

            hashed = generate_password_hash(password)

            cur.execute("""
                INSERT INTO "Пользователи" (Имя, Фамилия, Login, Password, role_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (name, surname, login, hashed, role_id))

            flash('Пользователь создан', 'success')

        conn.commit()
        return redirect(url_for('пользователи'))

    # GET-запрос
    if id:
        if not can_edit:
            abort(403)
        cur.execute("""
            SELECT id, Имя, Фамилия, Login, role_id
            FROM "Пользователи" WHERE id = %s
        """, (id,))
        item = cur.fetchone()
        if not item:
            abort(404)

    # Список пользователей
    cur.execute("""
        SELECT u.id, u.Имя, u.Фамилия, u.Login, r.name
        FROM "Пользователи" u
        LEFT JOIN Roles r ON u.role_id = r.id
        ORDER BY u.id
    """)
    data = cur.fetchall()

    cur.close()

    return render_template('пользователи.html',
                           data=data,
                           item=item,
                           can_create=can_create,
                           can_edit=can_edit,
                           can_delete=can_delete,
                           roles=roles)

# Страница управления правами (только для admin)
@app.route('/permissions', methods=['GET', 'POST'])
def permissions():
    if g.user is None or not g.is_admin:  # Только админ
        abort(403)

    conn = get_db()
    cur = conn.cursor()

    # Список сущностей — определяем ОДНИМ РАЗОМ в начале, доступен и в GET, и в POST
    entities = ['группа','дисциплина','преподаватель','средство','по','оборудование','занятие','сервер','пользователи','permissions']

    if request.method == 'POST':
        # Находим ID роли Администратор
        cur.execute("SELECT id FROM Roles WHERE name = 'Администратор'")
        admin_role = cur.fetchone()
        admin_role_id = admin_role[0] if admin_role else None

        # Получаем все роли
        cur.execute("SELECT id, name FROM Roles")
        roles = cur.fetchall()

        for role_id, role_name in roles:
            # Никогда не трогаем права администратора
            if role_id == admin_role_id:
                continue

            # Удаляем старые права для этой роли (кроме админа)
            cur.execute("DELETE FROM Permissions WHERE role_id = %s", (role_id,))

            # Вставляем новые
            for ent in entities:
                view = f"{role_id}_{ent}_view" in request.form
                create = f"{role_id}_{ent}_create" in request.form
                edit = f"{role_id}_{ent}_edit" in request.form
                delete = f"{role_id}_{ent}_delete" in request.form

                cur.execute("""
                    INSERT INTO Permissions (role_id, entity, can_view, can_create, can_edit, can_delete)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (role_id, entity) DO UPDATE
                    SET can_view = EXCLUDED.can_view,
                        can_create = EXCLUDED.can_create,
                        can_edit = EXCLUDED.can_edit,
                        can_delete = EXCLUDED.can_delete
                """, (role_id, ent, view, create, edit, delete))

        conn.commit()
        flash('Права доступа обновлены', 'success')

    # ------------------- Блок GET (или после POST) -------------------
    cur.execute("SELECT id, name FROM Roles")
    roles = cur.fetchall()

    perms = {}
    for role_id, _ in roles:
        perms[role_id] = {}
        for ent in entities:
            cur.execute("SELECT can_view, can_create, can_edit, can_delete FROM Permissions WHERE role_id = %s AND entity = %s", (role_id, ent))
            row = cur.fetchone()
            if row:
                perms[role_id][ent] = row
            else:
                perms[role_id][ent] = (False, False, False, False)

    cur.close()

    return render_template('permissions.html', roles=roles, entities=entities, perms=perms)

@app.route('/занятия_пользователь')
def занятия_пользователь():
    if g.user is None:
        return redirect(url_for('login'))

    common = get_common_data()
    conn = get_db()
    cur = conn.cursor()

    # Базовый запрос — ДОБАВЛЕНА Дата и изменён порядок полей
    query = """
        SELECT z.id_занятия,
               TRIM(COALESCE(p.Фамилия || ' ' || p.Имя || COALESCE(' ' || p.Отчество, ''), '—')) as prep,
               g.название_группы,
               d.название_дисциплины,
               z.Семестр,
               s.Название as sredstvo,
               z.Описание,
               z.Дата
        FROM Занятие z
        LEFT JOIN Преподаватель p ON z.id_преподавателя = p.id_преподавателя
        LEFT JOIN Группа g ON z.id_группы = g.id_группы
        LEFT JOIN Дисциплина d ON z.id_дисциплины = d.id_дисциплины
        LEFT JOIN Средство s ON z.id_средства = s.id_средства
        WHERE 1=1
    """
    params = []

    group = _optional_query_int(request.args.get('group'))
    if group is not None:
        query += " AND z.id_группы = %s"
        params.append(group)

    disc = _optional_query_int(request.args.get('disc'))
    if disc is not None:
        query += " AND z.id_дисциплины = %s"
        params.append(disc)

    kurs = _optional_query_int(request.args.get('kurs'))
    if kurs is not None:
        query += " AND z.Семестр = %s"
        params.append(kurs)

    # Сортировка по дате (сначала новые)
    query += " ORDER BY z.Дата DESC, z.id_занятия DESC"

    cur.execute(query, params)
    data = cur.fetchall()
    cur.close()

    return render_template('занятия_пользователь.html', data=data, common=common)

@app.route('/занятия_пользователь_export')
def export_zanyatiya_user():
    if g.user is None:
        return redirect(url_for('login'))

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT 
               COALESCE(TRIM(p.Фамилия || ' ' || p.Имя || COALESCE(' ' || p.Отчество, '')), '—') AS Преподаватель,
               COALESCE(g.название_группы, '—') AS Группа,
               COALESCE(d.название_дисциплины, '—') AS Дисциплина,
               z.Семестр AS Курс,
               COALESCE(TO_CHAR(z.Дата, 'DD.MM.YYYY'), '—') AS Дата,
               COALESCE(s.Название, '—') AS Средство,
               COALESCE(z.Описание, '—') AS Описание
        FROM Занятие z
        LEFT JOIN Преподаватель p ON z.id_преподавателя = p.id_преподавателя
        LEFT JOIN Группа g ON z.id_группы = g.id_группы
        LEFT JOIN Дисциплина d ON z.id_дисциплины = d.id_дисциплины
        LEFT JOIN Средство s ON z.id_средства = s.id_средства
        WHERE 1=1
    """
    params = []

    group = _optional_query_int(request.args.get('group'))
    if group is not None:
        query += " AND z.id_группы = %s"
        params.append(group)

    disc = _optional_query_int(request.args.get('disc'))
    if disc is not None:
        query += " AND z.id_дисциплины = %s"
        params.append(disc)

    kurs = _optional_query_int(request.args.get('kurs'))
    if kurs is not None:
        query += " AND z.Семестр = %s"
        params.append(kurs)

    query += " ORDER BY z.Дата DESC, z.id_занятия DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()

    if not rows:
        flash('Нет данных для экспорта с текущими фильтрами', 'info')
        return redirect(url_for('занятия_пользователь'))

    # Создание Excel-файла
    wb = Workbook()
    ws = wb.active
    ws.title = "Мои занятия"

    headers = ["Преподаватель", "Группа", "Дисциплина", "Курс", "Дата", "Средство", "Описание"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        ws.append(row)

    # Автоподгонка ширины колонок
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    # Сохранение в память и отправка
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"мои_занятия_{datetime.now().strftime('%d-%m-%Y')}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.errorhandler(403)
def handle_forbidden(_error):
    flash('У вас нет прав для выполнения этого действия', 'error')
    if g.user is None:
        return redirect(url_for('login'))
    return redirect(url_for('index'))


@app.errorhandler(404)
def handle_not_found(_error):
    flash('Страница не найдена', 'error')
    if g.user is None:
        return redirect(url_for('login'))
    return redirect(url_for('index'))


@app.errorhandler(500)
def handle_internal_error(error):
    app.logger.exception("Unhandled server error: %s", error)
    flash('Внутренняя ошибка сервера. Попробуйте позже.', 'error')
    if g.user is None:
        return redirect(url_for('login'))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
