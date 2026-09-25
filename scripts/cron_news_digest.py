#!/usr/bin/env python3
"""
Digest Diario de Noticias Tecnológicas y de IA para Android Home Server.
Rastrea noticias de última hora, extrae resúmenes estructurados con LLM y las envía a Telegram.
"""
import sys
import json
import re
import urllib.request
import urllib.parse
from web_search_helper import robust_web_search
from hermes_config import get_env_var, get_llm_config

BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", "")
_chat_raw = get_env_var("TELEGRAM_HOME_CHANNEL") or get_env_var("TELEGRAM_ALLOWED_USERS", "")
CHAT_ID = _chat_raw.split(",")[0].strip() if _chat_raw else ""

NEWS_QUERY = "inteligencia artificial avances tecnologia noticias hoy"


def summarize_with_llm(articles: list) -> str:
    llm = get_llm_config()
    api_key = llm["api_key"]
    base_url = llm["base_url"]
    model = llm["model"]

    if not api_key:
        lines = ["📰 *NOTICIAS TECNOLÓGICAS DEL DÍA* 📰\n"]
        for a in articles[:5]:
            lines.append(f"🔹 *{a.get('title')}*\n🔗 {a.get('url')}\n")
        return "\n".join(lines)

    prompt = f"""Eres un periodista tecnológico experto.
Redacta un resumen matutino con las 3-4 noticias más impactantes de hoy basándote en los datos recopilados.

Formato requerido para Telegram:
📰 *NOTICIAS DESTACADAS DE TECNOLOGÍA & IA*

🔹 *[Titular claro en español]*
📝 [Resumen conciso en 2 frases de por qué importa]
🔗 [Enlace directo a la fuente]

DATOS CRUDOS:
{json.dumps(articles, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Eres un redactor tecnológico conciso y riguroso."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    req = urllib.request.Request(f"{base_url}/chat/completions", data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw = data["choices"][0]["message"]["content"]
            return re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"[ERROR] Error resumiendo noticias: {e}", file=sys.stderr)
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
            print("[+] Resumen de noticias enviado a Telegram.")
    except Exception as e:
        print(f"[ERROR] Error enviando a Telegram: {e}", file=sys.stderr)


def main():
    print("[*] Buscando noticias tecnológicas de última hora...")
    results = robust_web_search(NEWS_QUERY, max_results=6)
    if not results:
        print("[-] No se encontraron noticias recientes.")
        return
    summary = summarize_with_llm(results)
    if summary:
        send_telegram(summary)


if __name__ == "__main__":
    main()
