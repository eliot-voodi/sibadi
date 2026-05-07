import secrets
from flask import abort, g, request, session
from werkzeug.security import generate_password_hash


_get_db = None
_admin_bootstrap_config = {}
_admin_checked = False
_allowed_actions = {"view", "create", "edit", "delete"}


def init_security(get_db_fn, admin_bootstrap_config: dict):
    global _get_db, _admin_bootstrap_config
    _get_db = get_db_fn
    _admin_bootstrap_config = admin_bootstrap_config


def ensure_admin_exists():
    global _admin_checked

    if _admin_checked or not _admin_bootstrap_config.get("enabled"):
        return

    admin_password = _admin_bootstrap_config.get("password")
    if not admin_password:
        print("[WARN] ADMIN_BOOTSTRAP_ENABLED=true, но ADMIN_BOOTSTRAP_PASSWORD не задан. Создание admin пропущено.")
        _admin_checked = True
        return

    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM Roles WHERE name = %s", ("Администратор",))
        admin_role = cur.fetchone()
        if not admin_role:
            print("[ERROR] Роль 'Администратор' не найдена в БД.")
            _admin_checked = True
            return

        cur.execute('SELECT 1 FROM "Пользователи" WHERE Login = %s', (_admin_bootstrap_config.get("login"),))
        if cur.fetchone():
            _admin_checked = True
            return

        cur.execute(
            """
            INSERT INTO "Пользователи" (Имя, Фамилия, Login, Password, Группа_доступа, role_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                "Админ",
                "Администратор",
                _admin_bootstrap_config.get("login"),
                generate_password_hash(admin_password),
                "Администраторы",
                admin_role[0],
            ),
        )
        conn.commit()
        _admin_checked = True
        print("[INFO] Администратор создан автоматически через bootstrap-настройки.")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Не удалось создать администратора: {e}")
    finally:
        cur.close()


def before_request_setup():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method == "POST":
        submitted_token = request.form.get("csrf_token")
        if not submitted_token or submitted_token != session.get("csrf_token"):
            abort(400, description="CSRF token missing or invalid")

    if request.endpoint not in ("login", "static"):
        ensure_admin_exists()

    g.user = None
    g.login = None
    g.role_id = None
    g.role_name = None
    g.is_admin = False

    if "user_id" in session:
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT u.id, u.Login, u.role_id, r.name
                FROM "Пользователи" u
                LEFT JOIN Roles r ON u.role_id = r.id
                WHERE u.id = %s
                """,
                (session["user_id"],),
            )
            user = cur.fetchone()
            if user:
                g.user = user
                g.user_id = user[0]
                g.login = user[1]
                g.role_id = user[2]
                g.role_name = user[3]
                g.is_admin = user[3] == "Администратор"
                session["role_id"] = user[2]
            else:
                session.clear()
        except Exception as e:
            print(f"Ошибка загрузки пользователя: {e}")
            session.clear()
        finally:
            cur.close()


def inject_admin():
    return {
        "is_admin": bool(getattr(g, "is_admin", False)),
        "csrf_token": session.get("csrf_token"),
    }


def has_permission(entity, action):
    if not entity or action not in _allowed_actions or "role_id" not in session:
        return False

    if getattr(g, "is_admin", False):
        return True

    role_id = session.get("role_id")
    if not isinstance(role_id, int):
        return False

    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT CASE %s
                WHEN 'view' THEN can_view
                WHEN 'create' THEN can_create
                WHEN 'edit' THEN can_edit
                WHEN 'delete' THEN can_delete
            END
            FROM Permissions
            WHERE role_id = %s AND entity = %s
            """,
            (action, role_id, entity),
        )
        result = cur.fetchone()
        return result is not None and result[0] is True
    finally:
        cur.close()
