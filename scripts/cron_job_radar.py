#!/usr/bin/env python3
"""
Radar Diario de Empleo para Android Home Server.
Rastrea ofertas de empleo en portales clave (InfoJobs, Indeed, Tecnoempleo, Trabajos.com, portales remotos).
1. Deduplicación inteligente con memoria persistente (seen_jobs.json).
2. Curación, filtrado de ruido y categorización con cualquier LLM compatible con OpenAI.
3. Notificación diaria estructurada por Telegram.
"""
import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from urllib.parse import urlparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from web_search_helper import robust_web_search
from hermes_config import get_hermes_home, get_env_var, get_llm_config

HERMES_DIR = get_hermes_home()
SEEN_FILE = os.path.join(HERMES_DIR, "cron", "seen_jobs.json")

BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", "")
_chat_raw = get_env_var("TELEGRAM_HOME_CHANNEL") or get_env_var("TELEGRAM_ALLOWED_USERS", "")
CHAT_ID = _chat_raw.split(",")[0].strip() if _chat_raw else ""

LOCATIONS = get_env_var("JOB_SEARCH_LOCATIONS", "Madrid, Barcelona, Valencia, Remoto")
KEYWORDS = get_env_var("JOB_SEARCH_KEYWORDS", "web junior, frontend, soporte tecnico, helpdesk, administrativo")
REMOTE_ENABLED = get_env_var("JOB_REMOTE_ENABLED", "true").lower() == "true"

ALLOWED_DOMAINS = {
    "infojobs.net",
    "indeed.com",
    "trabajos.com",
    "tecnoempleo.com",
    "infoempleo.com",
    "remotojob.com",
    "remotolist.com",
    "jooble.org",
    "jobsora.com",
    "linkedin.com"
}


def load_seen_jobs() -> dict:
    if os.path.isfile(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_seen_jobs(seen: dict) -> None:
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Error guardando seen_jobs.json: {e}", file=sys.stderr)


def is_valid_job_url(url: str) -> bool:
    if not url:
        return False
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def build_search_queries():
    queries = []
    # 1. Búsqueda local / regional
    loc_terms = " OR ".join([f'"{l.strip()}"' for l in LOCATIONS.split(",") if l.strip()])
    kw_terms = " OR ".join([f'"{k.strip()}"' for k in KEYWORDS.split(",") if k.strip()])
    
    if loc_terms and kw_terms:
        queries.append(f'(site:infojobs.net OR site:es.indeed.com OR site:trabajos.com) ({loc_terms}) ({kw_terms}) -senior')
    
    # 2. Búsqueda remota (si está activada)
    if REMOTE_ENABLED and kw_terms:
        queries.append(f'(site:tecnoempleo.com OR site:infojobs.net OR site:remotojob.com) "remoto" ({kw_terms}) -senior -lead')

    return queries


def process_with_llm(raw_jobs: list) -> str:
    llm = get_llm_config()
    api_key = llm["api_key"]
    base_url = llm["base_url"]
    model = llm["model"]

    if not api_key:
        # Si no hay clave de LLM, devolvemos un resumen directo sin formateo IA
        lines = ["💼 *OFERTAS DE EMPLEO DETECTADAS* 💼\n"]
        for j in raw_jobs[:10]:
            lines.append(f"🔹 *{j.get('title')}*\n🔗 {j.get('url')}\n")
        return "\n".join(lines)

    prompt = f"""Eres un asistente de empleo personal.
Analiza las ofertas de empleo recolectadas y selecciona las más relevantes según estos criterios:
- Ubicaciones objetivo: {LOCATIONS}
- Puestos buscados: {KEYWORDS}
- Teletrabajo: {"Permitido / Recomendado" if REMOTE_ENABLED else "Solo presencial"}

REGLAS DE FORMATO:
- Descarta puestos de nivel Senior, Directivos o con exigencias irreales.
- Organiza el reporte con este formato limpio de Telegram:

💼 *RADAR DE EMPLEO RECIENTE*

🔹 [Título del Puesto]
🏢 Empresa: [Nombre si aparece, o 'Confidencial']
📍 Ubicación: [Ciudad / 100% Remoto]
🔗 [URL limpia directa a la oferta]
📝 [Requisitos clave o tecnologías en 1 línea]

RESULTADOS CRUDOS:
{json.dumps(raw_jobs, ensure_ascii=False, indent=2)}
"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Eres un asistente de empleo experto y directo en español."},
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
            text = data["choices"][0]["message"]["content"]
            # Limpiar etiquetas de razonamiento tipo <think>
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            return text
    except Exception as e:
        print(f"[ERROR] Fallo al procesar ofertas con LLM: {e}", file=sys.stderr)
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
            print("[+] Notificación de empleo enviada a Telegram.")
    except Exception as e:
        print(f"[ERROR] Error enviando a Telegram: {e}", file=sys.stderr)


def main():
    seen = load_seen_jobs()
    queries = build_search_queries()
    new_jobs = []

    print(f"[*] Lanzando rastreo de empleo en {len(queries)} consultas...")
    for q in queries:
        results = robust_web_search(q, max_results=6)
        for r in results:
            url = r.get("url", "")
            if not is_valid_job_url(url):
                continue
            if url in seen:
                continue
            new_jobs.append(r)
            seen[url] = datetime.now().isoformat()

    print(f"[+] Total ofertas nuevas encontradas: {len(new_jobs)}")
    if new_jobs:
        report = process_with_llm(new_jobs[:15])
        if report:
            send_telegram(report)
        save_seen_jobs(seen)
    else:
        print("[-] No hay ofertas nuevas en este ciclo.")


if __name__ == "__main__":
    main()
