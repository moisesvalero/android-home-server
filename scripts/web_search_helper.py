#!/usr/bin/env python3
"""
Motor de Búsqueda Web Resiliente con Triple Redundancia para Android Home Server.
1. Rotación de múltiples claves de Tavily (si una devuelve 429 o agota cuota, conmuta a la siguiente).
2. Fallback automático a DuckDuckGo (100% nativo, gratuito y sin claves requeridas).
3. Contrato uniforme de salida con claves 'title', 'url', 'content' y 'description'.
"""
import sys
import json
import urllib.request
import urllib.error

from hermes_config import get_env_var

# Recoger todas las claves posibles de Tavily
raw_keys = get_env_var("TAVILY_KEYS", "")
single_key = get_env_var("TAVILY_API_KEY", "")

TAVILY_KEYS = []
if raw_keys:
    TAVILY_KEYS.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
if single_key and single_key not in TAVILY_KEYS:
    TAVILY_KEYS.append(single_key)


def search_tavily(query: str, max_results: int = 5):
    if not TAVILY_KEYS:
        return []

    for key in TAVILY_KEYS:
        payload = {
            "api_key": key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False
        }
        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                if results:
                    normalized = []
                    for r in results:
                        text_body = r.get("content", "")
                        normalized.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": text_body,
                            "description": text_body
                        })
                    return normalized
        except urllib.error.HTTPError as e:
            print(f"[WARN] Tavily clave {key[:10]}... dio error {e.code}, probando siguiente respaldo...", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[WARN] Tavily fallo en '{query[:30]}...': {e}", file=sys.stderr)
            continue

    return []


def search_duckduckgo(query: str, max_results: int = 5):
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
            normalized = []
            for r in raw:
                body = r.get("body", "")
                normalized.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": body,
                    "description": body
                })
            return normalized
    except Exception as e:
        print(f"[WARN] DuckDuckGo fallo: {e}", file=sys.stderr)
        return []


def robust_web_search(query: str, max_results: int = 5):
    """
    Intenta Tavily (con todas las claves disponibles en rotación).
    Si falla o se agotan las cuotas, salta automáticamente a DuckDuckGo.
    Devuelve siempre diccionarios con claves 'title', 'url', 'content' y 'description'.
    """
    results = search_tavily(query, max_results)
    if not results:
        results = search_duckduckgo(query, max_results)
    return results


if __name__ == "__main__":
    q = "tecnologia noticias"
    print(f"[*] Claves de Tavily cargadas: {len(TAVILY_KEYS)}")
    res = robust_web_search(q, 2)
    print(f"[+] Total resultados para '{q}': {len(res)}")
    for r in res:
        print(f" * {r['title']} -> {r['url']}")
