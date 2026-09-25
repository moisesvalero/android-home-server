#!/usr/bin/env bash
# ==============================================================================
# SCRIPT DE DESPLIEGUE CONTINUO (PC / Mac -> Smartphone Android)
# ==============================================================================
# Sincroniza el código fuente hacia el móvil por rsync sobre SSH sin
# sobrescribir bases de datos locales, entornos virtuales o ficheros de memoria.

set -e

# Configuración por defecto (sobrescribible con variables de entorno)
SERVER_HOST="${SERVER_HOST:-192.168.1.100}"
SERVER_PORT="${SERVER_PORT:-8022}"
SERVER_USER="${SERVER_USER:-$(whoami)}"
REMOTE_PATH="/data/data/com.termux/files/home/.hermes"

echo "=== 🔁 SINCRONIZANDO CON ANDROID HOME SERVER (${SERVER_HOST}:${SERVER_PORT}) ==="

rsync -avz --delete \
    --exclude=".git/" \
    --exclude=".env" \
    --exclude="*.log" \
    --exclude="seen_*.json" \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="media/" \
    --exclude="*.db" \
    --exclude="*.db-*" \
    -e "ssh -p ${SERVER_PORT}" \
    ./scripts/ \
    "${SERVER_USER}@${SERVER_HOST}:${REMOTE_PATH}/scripts/"

rsync -avz \
    -e "ssh -p ${SERVER_PORT}" \
    ./plugins/ \
    "${SERVER_USER}@${SERVER_HOST}:${REMOTE_PATH}/plugins/"

echo "[*] Reiniciando servicios en el móvil..."
ssh -p "${SERVER_PORT}" "${SERVER_USER}@${SERVER_HOST}" "pm2 restart all" || true

echo "=== ✅ DESPLIEGUE FINALIZADO CON ÉXITO ==="
