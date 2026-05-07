import psycopg2
from flask import g


def init_db(config: dict):
    def get_db():
        if "db" not in g:
            g.db = psycopg2.connect(
                host=config["host"],
                database=config["database"],
                user=config["user"],
                password=config["password"],
            )
        return g.db

    def close_db(_error):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    return get_db, close_db
