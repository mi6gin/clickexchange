#!/bin/sh
# Генерирует самоподписанный сертификат для локальной разработки.
# В реальном проде замените на Let's Encrypt (certbot).
set -e

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/selfsigned.crt" ] && [ -f "$CERT_DIR/selfsigned.key" ]; then
    echo "Сертификат уже существует: $CERT_DIR"
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$CERT_DIR/selfsigned.key" \
    -out "$CERT_DIR/selfsigned.crt" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "Создан самоподписанный сертификат: $CERT_DIR/selfsigned.crt"
