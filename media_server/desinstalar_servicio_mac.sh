#!/usr/bin/env bash
# ==============================================================================
# DESINSTALADOR DEL SERVICIO EN SEGUNDO PLANO PARA MACOS
# ==============================================================================
set -euo pipefail

PLIST_FILE="$HOME/Library/LaunchAgents/com.androidhomeserver.mac-helper.plist"

echo "=== 🛑 DESINSTALANDO ASISTENTE DE MACOS ==="

if [ -f "$PLIST_FILE" ]; then
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm -f "$PLIST_FILE"
    echo "✅ Servicio detenido y eliminado de LaunchAgents."
else
    echo "ℹ️ El servicio no estaba instalado en $PLIST_FILE."
fi
