import secrets
import string
import sys
import os
import time
import logging
from collections import deque
from threading import Lock

from flask import abort, g, redirect, request, session, url_for
from psycopg2 import errors
from werkzeug.security import generate_password_hash


_get_db = None
_admin_bootstrap_config = {}
_admin_checked = False
_allowed_actions = {"view", "create", "edit", "delete"}
_PUBLIC_ENDPOINTS = frozenset({"login", "logout", "static", "healthz"})

_bf_lock = Lock()
_bf_recent_failures: dict[str, deque] = {}
_bf_lockout_until: dict[str, float] = {}

# Типичные требования ГОСТ Р 71753 / рекомендаций ФСТЭК к парольной защите:
# длина не менее 12 символов, использование не менее трёх классов символов
# (верхний/нижний регистр латиницы, цифры, специальные знаки).
_FSTEK_MIN_LEN = 12
_FSTEK_DEFAULT_LEN = 16


def generate_fstek_style_password(length: int = _FSTEK_DEFAULT_LEN) -> str:
    """Криптостойкий пароль длиной не менее 12 символов с четырьмя классами символов."""
    n = max(length, _FSTEK_MIN_LEN)
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%*+-=?^&"
    alphabet = lower + upper + digits + special
    rng = secrets.SystemRandom()
    parts = [
        rng.choice(lower),
        rng.choice(upper),
        rng.choice(digits),
        rng.choice(special),
    ]
    parts.extend(rng.choice(alphabet) for _ in range(n - len(parts)))
    rng.shuffle(parts)
    return "".join(parts)


def init_security(get_db_fn, admin_bootstrap_config: dict):
    global _get_db, _admin_bootstrap_config
    _get_db = get_db_fn
    _admin_bootstrap_config = admin_bootstrap_config


def get_client_ip() -> str:
    """IP клиента за reverse proxy (заголовки от Nginx) либо remote_addr."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()[:256] or "unknown"
    rip = request.headers.get("X-Real-IP")
    if rip:
        return rip.strip()[:256] or "unknown"
    return request.remote_addr or "unknown"


def _login_bf_window_sec() -> float:
    return max(60.0, float(os.getenv("LOGIN_BF_WINDOW_SEC", "600")))


def _login_bf_max_attempts() -> int:
    return max(1, int(os.getenv("LOGIN_BF_MAX_ATTEMPTS", "8")))


def _login_bf_lockout_sec() -> float:
    return max(60.0, float(os.getenv("LOGIN_BF_LOCKOUT_SEC", "900")))


def login_bruteforce_reset(ip: str) -> None:
    """Сброс счётчиков после успешного входа."""
    with _bf_lock:
        _bf_recent_failures.pop(ip, None)
        _bf_lockout_until.pop(ip, None)


def login_bruteforce_register_failure(ip: str) -> None:
    """Учесть неудачную попытку входа; при превышении порога — блокировка IP."""
    now = time.time()
    window = _login_bf_window_sec()
    lockout_dur = _login_bf_lockout_sec()
    max_fails = _login_bf_max_attempts()
    with _bf_lock:
        dq = _bf_recent_failures.setdefault(ip, deque())
        cutoff = now - window
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        if len(dq) >= max_fails:
            _bf_lockout_until[ip] = now + lockout_dur
            dq.clear()
            logging.warning(
                "Блокировка входа после неудачных попыток: ip=%s, lockout_sec=%s",
                ip,
                int(lockout_dur),
            )


def login_bruteforce_blocked(ip: str) -> tuple[bool, int]:
    """
    Заблокирован ли вход с IP и сколько секунд осталось до разблокировки.
    Истёкшая блокировка снимается при проверке.
    """
    now = time.time()
    with _bf_lock:
        until = _bf_lockout_until.get(ip)
        if until is None:
            return False, 0
        if now >= until:
            del _bf_lockout_until[ip]
            _bf_recent_failures.pop(ip, None)
            return False, 0
        return True, max(1, int(until - now))


def _try_insert_admin_user(cur, conn, login: str, plain_password: str) -> bool:
    """
    Создать администратора. True — запись добавлена; False — роль не найдена или логин уже занят (гонка воркеров).
    """
    cur.execute("SELECT id FROM Roles WHERE name = %s", ("Администратор",))
    admin_role = cur.fetchone()
    if not admin_role:
        print("[ERROR] Роль 'Администратор' не найдена в БД.", file=sys.stderr)
        return False

    try:
        cur.execute(
            """
            INSERT INTO "Пользователи" (Имя, Фамилия, Login, Password, role_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                "Админ",
                "Администратор",
                login,
                generate_password_hash(plain_password),
                admin_role[0],
            ),
        )
        conn.commit()
        return True
    except errors.UniqueViolation:
        conn.rollback()
        return False


def _ensure_admin_from_env():
    """ADMIN_BOOTSTRAP_ENABLED=true: пароль из окружения."""
    admin_password = _admin_bootstrap_config.get("password")
    if not admin_password:
        print(
            "[WARN] ADMIN_BOOTSTRAP_ENABLED=true, но ADMIN_BOOTSTRAP_PASSWORD не задан. Создание admin пропущено.",
            file=sys.stderr,
        )
        return

    login = _admin_bootstrap_config.get("login") or "admin"
    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT 1 FROM "Пользователи" WHERE Login = %s', (login,))
        if cur.fetchone():
            return

        if not _try_insert_admin_user(cur, conn, login, admin_password):
            return

        print("[INFO] Администратор создан автоматически через bootstrap-настройки.", file=sys.stderr)
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Не удалось создать администратора: {e}", file=sys.stderr)
    finally:
        cur.close()


def _ensure_admin_with_generated_password():
    """ADMIN_BOOTSTRAP_ENABLED=false: пароль по требованиям ГОСТ/ФСТЭК, одноразовый вывод в консоль."""
    login = _admin_bootstrap_config.get("login") or "admin"
    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT 1 FROM "Пользователи" WHERE Login = %s', (login,))
        if cur.fetchone():
            return

        plain = generate_fstek_style_password()
        if not _try_insert_admin_user(cur, conn, login, plain):
            return

        print("", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(
            "СОЗДАН АДМИНИСТРАТОР (ADMIN_BOOTSTRAP_ENABLED=false).",
            file=sys.stderr,
        )
        print(
            f"Одноразовый пароль (ГОСТ Р 71753 / рекомендации ФСТЭК: длина ≥{_FSTEK_MIN_LEN}, "
            "латиница верхний/нижний регистр, цифры, спецсимволы; генерация: secrets).",
            file=sys.stderr,
        )
        print(f"  Логин: {login}", file=sys.stderr)
        print(f"  Пароль: {plain}", file=sys.stderr)
        print("Сохраните учётные данные; в консоль они больше не выводятся.", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print("", file=sys.stderr)
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Не удалось создать администратора: {e}", file=sys.stderr)
    finally:
        cur.close()


def ensure_admin_exists():
    global _admin_checked

    if _admin_checked:
        return

    try:
        if _admin_bootstrap_config.get("enabled"):
            _ensure_admin_from_env()
        else:
            _ensure_admin_with_generated_password()
    finally:
        _admin_checked = True


def before_request_setup():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method == "POST":
        submitted_token = request.form.get("csrf_token")
        if not submitted_token or submitted_token != session.get("csrf_token"):
            abort(400, description="CSRF token missing or invalid")

    if request.endpoint != "static":
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

    if (
        request.endpoint is not None
        and request.endpoint not in _PUBLIC_ENDPOINTS
        and getattr(g, "user", None) is None
    ):
        return redirect(url_for("login"))


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
                WHEN 'view' THEN p.can_view
                WHEN 'create' THEN p.can_create
                WHEN 'edit' THEN p.can_edit
                WHEN 'delete' THEN p.can_delete
            END
            FROM Permissions p
            INNER JOIN permission_entities e ON p.entity_id = e.id
            WHERE p.role_id = %s AND e.code = %s
            """,
            (action, role_id, entity),
        )
        result = cur.fetchone()
        return result is not None and result[0] is True
    finally:
        cur.close()
