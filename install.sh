#!/usr/bin/env bash
# ==============================================================================
# INSTALADOR AUTOMÁTICO - ANDROID HOME SERVER (Termux / Android aarch64 & arm)
# ==============================================================================
set -e

echo "=== 🚀 CONFIGURANDO ANDROID HOME SERVER ==="

# 1. Configurar variables de entorno críticas para compilación en Android
export ANDROID_API_LEVEL=31
if ! grep -q "ANDROID_API_LEVEL=31" "$HOME/.bashrc" 2>/dev/null; then
    echo "export ANDROID_API_LEVEL=31" >> "$HOME/.bashrc"
fi

# 2. Instalar paquetes base en Termux
if command -v pkg >/dev/null 2>&1; then
    echo "[*] Actualizando repositorios de Termux..."
    pkg update -y

    echo "[*] Instalando herramientas base, compiladores y paquetes nativos..."
    pkg install -y python python-pip nodejs-lts git openssh cronie termux-api \
                   rust binutils make clang libxml2 libxslt \
                   python-psutil python-cryptography python-lxml minidlna

    echo "[*] Instalando gestor de procesos PM2..."
    npm install -g pm2
fi

# 3. Preparar directorio $HOME/.hermes
echo "[*] Desplegando scripts, configuración y cron jobs en $HOME/.hermes..."
mkdir -p "$HOME/.hermes"
mkdir -p "$HOME/media/peliculas"
mkdir -p "$HOME/media/series"

cp -r scripts "$HOME/.hermes/"
cp -r cron "$HOME/.hermes/"
cp -r plugins "$HOME/.hermes/"
cp -r memories "$HOME/.hermes/" 2>/dev/null || true
cp config.yaml "$HOME/.hermes/"
cp SOUL.md "$HOME/.hermes/"
cp requirements.txt "$HOME/.hermes/requirements.txt"
chmod +x "$HOME/.hermes/scripts"/*.py 2>/dev/null || true

if [ ! -f "$HOME/.hermes/.env" ]; then
    if [ -f ".env" ]; then
        cp .env "$HOME/.hermes/.env"
    elif [ -f ".env.example" ]; then
        cp .env.example "$HOME/.hermes/.env"
        echo "[!] Se ha copiado .env.example a $HOME/.hermes/.env. Recuerda rellenar tus API keys."
    fi
fi

# 4. Crear entorno virtual Python principal
echo "[*] Creando entorno virtual Python en $HOME/.hermes-venv..."
python3 -m venv --system-site-packages "$HOME/.hermes-venv"
"$HOME/.hermes-venv/bin/pip" install --upgrade pip
"$HOME/.hermes-venv/bin/pip" install -r "$HOME/.hermes/requirements.txt"
"$HOME/.hermes-venv/bin/pip" install hermes-agent || echo "[!] Nota: Puedes usar los crons independientes o hermes-agent según prefieras."

# 5. Configurar auto-arranque en Termux:Boot si está disponible
echo "[*] Configurando auto-arranque en ~/.termux/boot/..."
mkdir -p "$HOME/.termux/boot"
cp start-services.sh "$HOME/.termux/boot/start-services.sh"
chmod +x "$HOME/.termux/boot/start-services.sh"

# 6. Registrar servicios en PM2
echo "[*] Registrando servicios en PM2..."

# 6.1 Agente Hermes (si está instalado)
if [ -f "$HOME/.hermes-venv/bin/hermes" ]; then
    pm2 start "$HOME/.hermes-venv/bin/python" --name "hermes" -- -m hermes_cli.main gateway run --accept-hooks
fi

# 6.2 Servidor Multimedia DLNA y Dashboard Web
if [ -d "media_server" ]; then
    bash media_server/setup_media_server.sh
fi

pm2 save

echo ""
echo "=== ✅ INSTALACIÓN COMPLETADA ==="
echo "Comandos útiles de gestión:"
echo "  pm2 status         -> Ver estado de los servicios en vivo"
echo "  pm2 logs           -> Ver logs de todos los demonios"
echo "  pm2 restart all    -> Reiniciar todos los servicios"
