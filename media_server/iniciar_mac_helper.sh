#!/usr/bin/env bash
# ==============================================================================
# INICIAR ASISTENTE LOCAL EN EL MAC PARA ANDROID MEDIA SERVER
# ==============================================================================
# Inicia el micro-servicio que permite al Dashboard convertir archivos .avi
# con el botón mágico en tu Mac y subirlos automáticamente al servidor Android.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== 🪄 INICIANDO MAC CONVERSION HELPER ==="
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[!] Advertencia: ffmpeg no parece estar instalado en tu Mac. Instálalo con: brew install ffmpeg"
fi

python3 "$SCRIPT_DIR/mac_helper.py"
