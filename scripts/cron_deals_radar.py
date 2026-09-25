#!/usr/bin/env python3
"""
Radar Diario de Chollos y Errores de Precio para Android Home Server.
Rastrea ofertas reales de tecnología, consolas, hardware y liquidaciones.
Filtra con cualquier LLM compatible con OpenAI y envía alertas a Telegram.
"""
import sys
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from web_search_helper import robust_web_search
from hermes_config import get_env_var, get_llm_config

BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", "")
_chat_raw = get_env_var("TELEGRAM_HOME_CHANNEL") or get_env_var("TELEGRAM_ALLOWED_USERS", "")
CHAT_ID = _chat_raw.split(",")[0].strip() if _chat_raw else ""

KEYWORDS = get_env_var("DEALS_KEYWORDS", "Xbox, PlayStation, Apple, MacBook, GPU, liquidacion, error de precio")

DEFAULT_QUERIES = [
    'site:chollometro.com/ofertas/ ("Xbox" OR "PlayStation" OR "Game Pass")',
    'site:chollometro.com/ofertas/ ("Apple" OR "iPhone" OR "MacBook" OR "iPad")',
    'site:chollometro.com/ofertas/ ("error de precio" OR "liquidación" OR "mínimo histórico")',
    'site:chollometro.com/ofertas/ (tecnología OR gaming OR pc OR hardware)'
]


def clean_llm_response(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    for mark in ['━━━━', '🔹', '# ']:
        if mark in text:
            text = text[text.find(mark):]
            break
    cleaned = []
    for l in text.splitlines():
        if any(w in l.lower() for w in ['avísame', 'espero que te sirva', 'buena suerte', 'aquí tienes']):
            continue
        cleaned.append(l)
    return '\n'.join(cleaned).strip()


def process_with_llm(search_results: list) -> str:
    llm = get_llm_config()
    api_key = llm["api_key"]
    base_url = llm["base_url"]
    model = llm["model"]

    if not api_key:
        lines = ["🛒 *CHOLLOS DETECTADOS* 🛒\n"]
        for r in search_results[:8]:
            lines.append(f"🔹 *{r.get('title')}*\n🔗 {r.get('url')}\n")
        return "\n".join(lines)

    prompt = f"""Eres un asistente cazachollos personal experto en tecnología.
Filtra y selecciona las MEJORES ofertas individuales reales encontradas basándote en: {KEYWORDS}.

CLASIFICACIÓN DE CHOLLOS (omite secciones que queden vacías):

━━━━ 🟢 GAMING & CONSOLAS ━━━━
🔹 [Título del Juego / Dispositivo / Suscripción]
💰 Precio: [Precio de oferta €] (PVP Habitual / Descuento)
🏪 Tienda: [Amazon / PcComponentes / etc.]
🔗 [URL directa al chollo]
📝 [Detalles clave: cupón, condiciones]

━━━━ 🍎 TECNOLOGÍA & HARDWARE ━━━━
🔹 [Título del Dispositivo / Componente]
💰 Precio: [Precio €]
🏪 Tienda: [Tienda]
🔗 [URL directa al chollo]
📝 [Detalles clave: modelo, especificaciones]

━━━━ 🚨 ERRORES DE PRECIO Y LIQUIDACIONES ━━━━
🔹 [Título del Chollo]
💰 Precio: [Precio €]
🏪 Tienda: [Tienda]
🔗 [URL directa]
📝 [Detalles clave]

REGLAS OBLIGATORIAS:
- Extrae SIEMPRE ofertas con precio y producto concreto.
- Pon SIEMPRE el enlace exacto (URL) a la oferta.
- Cero introducciones, saludos ni despedidas. Directo en español.

RESULTADOS RECOLECTADOS DE LA WEB:
{json.dumps(search_results, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Eres un asistente cazachollos experto y directo en español."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    req = urllib.request.Request(f"{base_url}/chat/completions", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["choices"][0]["message"]["content"]
            return clean_llm_response(raw_text)
    except Exception as e:
        print(f"[ERROR] Error procesando chollos con LLM: {e}", file=sys.stderr)
        return ""


def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID or not text:
        print(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            print("[+] Notificación de chollos enviada a Telegram.")
    except Exception as e:
        print(f"[ERROR] Error enviando a Telegram: {e}", file=sys.stderr)


def main():
    all_results = []
    print("[*] Rastreador de chollos iniciado...")
    for q in DEFAULT_QUERIES:
        res = robust_web_search(q, max_results=3)
        all_results.extend(res)

    if not all_results:
        print("[-] No se pudieron obtener resultados de ofertas.")
        return

    print(f"[+] Total fichas recopiladas: {len(all_results)}. Filtrando con IA...")
    report = process_with_llm(all_results)
    if report:
        send_telegram(report)
    else:
        print("[-] Ningún chollo superó el filtro de calidad.")


if __name__ == "__main__":
    main()
