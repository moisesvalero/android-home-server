#!/usr/bin/env python3
"""
Cron: Monitor de Batería y Temperatura para Android Home Server.
Comprueba el estado del dispositivo con termux-battery-status.
Incluye deduplicación y enfriamiento (cooldown) para evitar spam repetitivo por Telegram.
"""
import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.parse

from hermes_config import get_hermes_home, get_env_var

SERVER_NAME = get_env_var("SERVER_NAME", "Android Home Server")
BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", "")
_chat_raw = get_env_var("TELEGRAM_HOME_CHANNEL") or get_env_var("TELEGRAM_ALLOWED_USERS", "")
CHAT_ID = _chat_raw.split(",")[0].strip() if _chat_raw else ""

STATE_FILE = os.path.join(get_hermes_home(), ".battery_state.json")
COOLDOWN_SECONDS = 3 * 3600  # 3 horas de enfriamiento para la misma alerta


def load_state() -> dict:
    if os.path.isfile(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[WARN] No se pudo guardar el estado de batería: {e}", file=sys.stderr)


def send_telegram_alert(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"[ERROR] No se pudo enviar alerta a Telegram: {e}", file=sys.stderr)


def get_battery_info():
    """Obtiene datos de batería vía termux-battery-status."""
    try:
        out = subprocess.check_output(["termux-battery-status"], timeout=5).decode("utf-8")
        data = json.loads(out)
        pct = int(data.get("percentage", 100))
        status = data.get("status", "UNKNOWN")
        plugged = data.get("plugged", "UNKNOWN")
        temp = data.get("temperature")
        if temp is not None:
            temp = float(temp)
            # En ciertos kernels de Android la temperatura viene en décimas de grado (ej. 350 = 35.0°C)
            if temp > 150:
                temp = temp / 10.0
        return pct, status, plugged, temp
    except Exception:
        pass
    return None, None, None, None


def main():
    pct, status, plugged, temp = get_battery_info()
    if pct is None:
        return

    now = time.time()
    state = load_state()

    # 1. Evaluación de Temperatura
    if temp is not None:
        if temp >= 45.0:
            current_temp_level = "CRITICA" if temp >= 48.0 else "ELEVADA"
            last_temp_alert_ts = state.get("last_temp_alert_ts", 0)
            last_temp_level = state.get("last_temp_level")

            # Enviar si expiró el cooldown o si la severidad subió a CRÍTICA
            should_send_temp = (
                (now - last_temp_alert_ts >= COOLDOWN_SECONDS)
                or (current_temp_level == "CRITICA" and last_temp_level != "CRITICA")
            )

            if should_send_temp:
                sev_icon = "🚨 CRÍTICA" if current_temp_level == "CRITICA" else "⚠️ ELEVADA"
                msg = (
                    f"🔥 *¡ALERTA DE TEMPERATURA {sev_icon} EN {SERVER_NAME}!* 🔥\n\n"
                    f"🌡️ *Temperatura actual:* `{temp:.1f} °C`\n"
                    f"🔋 *Nivel de batería:* `{pct}%`\n"
                    f"🔌 *Estado:* `{status}` ({plugged})\n\n"
                    f"La temperatura ha superado el umbral de 45 °C. "
                    f"Revisa la ventilación del móvil o retira el cargador temporalmente."
                )
                send_telegram_alert(msg)
                state["last_temp_alert_ts"] = now
                state["last_temp_level"] = current_temp_level
                print(f"Alerta de temperatura enviada: {temp:.1f} °C ({current_temp_level})")
        elif temp < 40.0 and state.get("last_temp_level"):
            # Notificación de normalización de temperatura
            send_telegram_alert(
                f"✅ *TEMPERATURA NORMALIZADA EN {SERVER_NAME}*\n\n"
                f"🌡️ *Temperatura actual:* `{temp:.1f} °C`\n"
                f"El dispositivo ha vuelto a parámetros térmicos seguros."
            )
            state["last_temp_level"] = None
            state["last_temp_alert_ts"] = 0

    # 2. Evaluación de Batería Baja
    if pct <= 25:
        current_bat_level = "CRITICA" if pct <= 15 else "BAJA"
        last_bat_alert_ts = state.get("last_battery_alert_ts", 0)
        last_bat_level = state.get("last_battery_level")

        # Enviar si expiró el cooldown o si cayó a nivel CRÍTICO (<=15%)
        should_send_bat = (
            (now - last_bat_alert_ts >= COOLDOWN_SECONDS)
            or (current_bat_level == "CRITICA" and last_bat_level != "CRITICA")
        )

        if should_send_bat:
            icon = "🚨 BATERÍA CRÍTICA" if current_bat_level == "CRITICA" else "⚠️ BATERÍA BAJA"
            msg = (
                f"{icon} *EN {SERVER_NAME}!* ⚠️\n\n"
                f"🔋 *Nivel actual:* `{pct}%`\n"
                f"🔌 *Estado:* `{status}` ({plugged})\n"
                + (f"🌡️ *Temperatura:* `{temp:.1f} °C`\n\n" if temp is not None else "\n")
                + "El nivel de batería es bajo. Conecta el cargador para evitar que el servidor se apague."
            )
            send_telegram_alert(msg)
            state["last_battery_alert_ts"] = now
            state["last_battery_level"] = current_bat_level
            print(f"Alerta de batería enviada: {pct}% ({current_bat_level})")
    elif pct > 35 and state.get("last_battery_level") and "CHARGING" in status.upper():
        # Recuperación de batería
        send_telegram_alert(
            f"✅ *BATERÍA RECUPERADA EN {SERVER_NAME}*\n\n"
            f"🔋 *Nivel actual:* `{pct}%` ({status})\n"
            f"El servidor dispone de suficiente energía para continuar operando."
        )
        state["last_battery_level"] = None
        state["last_battery_alert_ts"] = 0

    save_state(state)


if __name__ == "__main__":
    main()
