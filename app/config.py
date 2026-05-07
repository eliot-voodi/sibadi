import os
import secrets


def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", secrets.token_hex(32))


def get_db_config() -> dict:
    return {
        "host": os.getenv("DB_HOST", "db"),
        "database": os.getenv("DB_NAME", "university"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASS", "password"),
    }


def get_admin_bootstrap_config() -> dict:
    return {
        "enabled": os.getenv("ADMIN_BOOTSTRAP_ENABLED", "false").lower() == "true",
        "login": os.getenv("ADMIN_BOOTSTRAP_LOGIN", "admin"),
        "password": os.getenv("ADMIN_BOOTSTRAP_PASSWORD"),
    }
