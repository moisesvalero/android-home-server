#!/usr/bin/env bash
# ==============================================================================
# SETUP MINI-DLNA PARA ANDROID HOME SERVER
# ==============================================================================
# Configura el servidor multimedia MiniDLNA para Smart TVs (Samsung, LG, etc.).
# Totalmente aislado de Hermes Agent y sus entornos virtuales.
# ==============================================================================
set -euo pipefail

echo "=== 🎬 CONFIGURANDO MINI-DLNA EN ANDROID ==="

# 1. Comprobar que estamos en Termux
if ! command -v pkg >/dev/null 2>&1; then
    echo "[!] Error: Este script debe ejecutarse en Termux en el dispositivo Android."
    exit 1
fi

# 2. Instalar minidlna
echo "[*] Instalando minidlna..."
pkg update -y
pkg install -y minidlna

# 3. Crear estructura de carpetas en $HOME/media
MEDIA_DIR="$HOME/media"
CONFIG_DIR="$HOME/.config/minidlna"

echo "[*] Creando estructura de directorios en $MEDIA_DIR..."
mkdir -p "$MEDIA_DIR/peliculas"
mkdir -p "$MEDIA_DIR/series"
mkdir -p "$CONFIG_DIR/cache"
mkdir -p "$CONFIG_DIR/log"

# 4. Copiar configuración de minidlna
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/minidlna.conf" ]; then
    cp "$SCRIPT_DIR/minidlna.conf" "$CONFIG_DIR/minidlna.conf"
    echo "[✓] Configuración copiada a $CONFIG_DIR/minidlna.conf"
fi

# 5. Copiar script de carátulas
if [ -f "$SCRIPT_DIR/fetch_cover.py" ]; then
    cp "$SCRIPT_DIR/fetch_cover.py" "$MEDIA_DIR/fetch_cover.py"
    chmod +x "$MEDIA_DIR/fetch_cover.py"
    echo "[✓] Script de carátulas instalado en $MEDIA_DIR/fetch_cover.py"
fi

# 6. Copiar interfaz web y servidor del Dashboard
if [ -f "$SCRIPT_DIR/dashboard_server.py" ]; then
    cp "$SCRIPT_DIR/dashboard_server.py" "$MEDIA_DIR/dashboard_server.py"
    chmod +x "$MEDIA_DIR/dashboard_server.py"
    mkdir -p "$MEDIA_DIR/dashboard"
    if [ -f "$SCRIPT_DIR/dashboard/index.html" ]; then
        cp "$SCRIPT_DIR/dashboard/index.html" "$MEDIA_DIR/dashboard/index.html"
    fi
    echo "[✓] Dashboard Web instalado en $MEDIA_DIR/dashboard"
fi

# 7. Registrar e iniciar MiniDLNA con PM2
echo "[*] Registrando servicio dlna-server en PM2..."
pm2 delete dlna-server >/dev/null 2>&1 || true

MINIDLNA_BIN="/data/data/com.termux/files/usr/bin/minidlnad"
pm2 start "$MINIDLNA_BIN" --name "dlna-server" -- -S -f "$CONFIG_DIR/minidlna.conf" -P "$CONFIG_DIR/minidlna.pid"

# 8. Registrar e iniciar Media Dashboard en PM2 (puerto 8090)
echo "[*] Registrando servicio media-dashboard en PM2..."
pm2 delete media-dashboard >/dev/null 2>&1 || true
pm2 start "$MEDIA_DIR/dashboard_server.py" --name "media-dashboard" --interpreter python3

pm2 save

echo ""
echo "=== 🛡️ ESTADO DE LOS SERVICIOS ==="
pm2 status

echo ""
echo "=== ✅ INSTALACIÓN DE STREAMING Y DASHBOARD COMPLETADA ==="
echo "1. Tu Smart TV detectará 'Android Media Server' en Fuentes / Dispositivos Conectados."
echo "2. Dashboard visual disponible en la IP de tu red local: http://<IP-DEL-MOVIL>:8090"
echo "3. Películas en: $MEDIA_DIR/peliculas"
echo "4. Series en:    $MEDIA_DIR/series"
echo "5. Ambos servicios consumen < 30 MB de RAM y 0% CPU en reposo."
