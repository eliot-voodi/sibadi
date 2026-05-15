import logging
from typing import Optional

from flask import g
import psycopg2
from psycopg2 import pool as pg_pool

_pool: Optional[pg_pool.ThreadedConnectionPool] = None


def init_db(config: dict):
    """Пул соединений к PostgreSQL + параметры канала и идентификации приложения."""
    global _pool

    sslmode = (config.get("sslmode") or "prefer").strip() or "prefer"
    conn_kw = {
        "host": config["host"],
        "dbname": config["database"],
        "user": config["user"],
        "password": config["password"],
        "sslmode": sslmode,
        "connect_timeout": int(config.get("connect_timeout", 10)),
        "application_name": (config.get("application_name") or "sibadi-web")[:64],
    }

    minconn = max(1, int(config.get("pool_min", 1)))
    maxconn = max(minconn, int(config.get("pool_max", 10)))

    _pool = pg_pool.ThreadedConnectionPool(minconn, maxconn, **conn_kw)
    logging.info(
        "PostgreSQL: пул %s–%s соединений, sslmode=%s, app=%s",
        minconn,
        maxconn,
        sslmode,
        conn_kw["application_name"],
    )

    def get_db():
        if "db_conn" not in g:
            g.db_conn = _pool.getconn()
        return g.db_conn

    def close_db(_error=None):
        conn = g.pop("db_conn", None)
        if conn is not None:
            _pool.putconn(conn)

    return get_db, close_db
