#!/usr/bin/env bash
set -euo pipefail

# Роль приложения с минимальными правами (без SUPERUSER).
APP_DB_USER="${APP_DB_USER:-sibadi_app}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-password}"
POSTGRES_DB="${POSTGRES_DB:-university}"

if [[ "${APP_DB_USER}" == "postgres" ]]; then
  echo "ERROR: APP_DB_USER не должен быть «postgres» (суперпользователь кластера). Задайте DB_USER=sibadi_app в .env." >&2
  exit 1
fi

if [[ ! "${APP_DB_USER}" =~ ^[a-zA-Z_][a-zA-Z0-9_]{0,62}$ ]]; then
  echo "ERROR: недопустимое имя APP_DB_USER: ${APP_DB_USER}" >&2
  exit 1
fi

if [[ ! "${POSTGRES_DB}" =~ ^[a-zA-Z_][a-zA-Z0-9_]{0,62}$ ]]; then
  echo "ERROR: недопустимое имя POSTGRES_DB: ${POSTGRES_DB}" >&2
  exit 1
fi

sql_escape() {
  printf '%s' "$1" | sed "s/'/''/g"
}
_esc_pass="$(sql_escape "${APP_DB_PASSWORD}")"

exists="$(psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${APP_DB_USER}'" --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}")"

if [[ "${exists}" =~ ^[[:space:]]*1[[:space:]]*$ ]]; then
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    -c "ALTER ROLE ${APP_DB_USER} LOGIN PASSWORD '${_esc_pass}'"
else
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    -c "CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${_esc_pass}'"
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${APP_DB_USER};
GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_DB_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};
EOSQL
