import logging
import os
import secrets

_WEAK_SECRET_KEYS = frozenset(
    {
        "",
        "change_me",
        "changeme",
        "secret",
        "secret_key",
        "password",
        "admin",
    }
)


def warn_if_weak_secret_key(secret_key: str) -> None:
    """Предупреждение при типовых или коротких значениях SECRET_KEY (продакшен)."""
    if not secret_key:
        logging.warning("SECRET_KEY не задан — сессии не защищены предсказуемо.")
        return
    sk = secret_key.strip()
    if sk.lower() in _WEAK_SECRET_KEYS or len(sk) < 32:
        logging.warning(
            "SECRET_KEY слабый или значение по умолчанию (ожидается ≥32 символов случайной строки для продакшена)."
        )


def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", secrets.token_hex(32))


def get_db_config() -> dict:
    # DB_SSLMODE переопределяет PGSSLMODE, если задан явно
    ssl_env = (os.getenv("DB_SSLMODE") or os.getenv("PGSSLMODE") or "prefer").strip()
    return {
        "host": os.getenv("DB_HOST", "db"),
        "database": os.getenv("DB_NAME", "university"),
        "user": os.getenv("DB_USER", "sibadi_app"),
        "password": os.getenv("DB_PASS", "password"),
        "sslmode": ssl_env or "prefer",
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        "application_name": os.getenv("DB_APPLICATION_NAME", "sibadi-web"),
        "pool_min": int(os.getenv("DB_POOL_MIN", "1")),
        "pool_max": int(os.getenv("DB_POOL_MAX", "10")),
    }


def get_admin_bootstrap_config() -> dict:
    return {
        "enabled": os.getenv("ADMIN_BOOTSTRAP_ENABLED", "false").lower() == "true",
        "login": os.getenv("ADMIN_BOOTSTRAP_LOGIN", "admin"),
        "password": os.getenv("ADMIN_BOOTSTRAP_PASSWORD"),
    }
