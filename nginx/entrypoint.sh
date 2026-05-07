#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_KEY="$CERT_DIR/server.key"
CERT_CRT="$CERT_DIR/server.crt"
SSL_CN="${SSL_CN:-localhost}"

mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_KEY" ] || [ ! -f "$CERT_CRT" ]; then
  echo "[nginx] Generating self-signed certificate for CN=$SSL_CN"
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$CERT_KEY" \
    -out "$CERT_CRT" \
    -days 365 \
    -subj "/CN=$SSL_CN"
else
  echo "[nginx] Using existing certificate from $CERT_DIR"
fi

exec nginx -g "daemon off;"
