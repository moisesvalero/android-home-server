#!/usr/bin/env bash
# ==============================================================================
# INSTALADOR DEL SERVICIO EN SEGUNDO PLANO (LAUNCHAGENT) PARA MACOS
# ==============================================================================
# Configura el asistente local como servicio nativo de macOS para que siempre
# esté activo en segundo plano sin consumir CPU ni apenas RAM (~12 MB).
# De esta forma, el botón [ 🪄 Convertir y Subir ] funciona siempre en 1 clic.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(which python3 || echo "/usr/bin/python3")"
HELPER_SCRIPT="$SCRIPT_DIR/mac_helper.py"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.androidhomeserver.mac-helper.plist"

echo "=== 🪄 INSTALANDO ASISTENTE AUTOMÁTICO EN MACOS ==="

mkdir -p "$PLIST_DIR"

# Descargar servicio anterior si ya estuviese cargado
launchctl unload "$PLIST_FILE" 2>/dev/null || true

# Escribir la configuración con las rutas exactas
cat <<EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.androidhomeserver.mac-helper</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${HELPER_SCRIPT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/android_server_mac_helper.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/android_server_mac_helper_err.log</string>
</dict>
</plist>
EOF

chmod 644 "$PLIST_FILE"
launchctl load -w "$PLIST_FILE"

sleep 1

# Verificar si responde en localhost:8095
if curl -s http://127.0.0.1:8095/api/status | grep -q '"status": "ok"'; then
    echo "✅ ¡Servicio instalado y activo con éxito!"
    echo "   - Puerto: http://127.0.0.1:8095"
    echo "   - Consumo en reposo: 0.0% CPU y ~12 MB de RAM"
    echo "   - Inicia solo con tu sesión de Mac."
    echo "   - El botón [ 🪄 Convertir y Subir ] estará siempre verde y listo en el Dashboard."
else
    echo "⚠️ El servicio se ha cargado pero aún no responde en el puerto 8095. Comprueba /tmp/android_server_mac_helper_err.log"
fi
