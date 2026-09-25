#!/usr/bin/env python3
"""
Extrae la URL de og:image o twitter:image desde cualquier sitio web público.
Protegido contra SSRF: únicamente conexiones HTTPS a IPs públicas y seguras.
Retorna JSON { "ok": bool, "image_url": str, "error": str | None }
"""
from __future__ import annotations
import sys
import re
import json
import urllib.request
from urllib.parse import urljoin
from network_security import validate_safe_public_url, build_safe_opener, SSRFValidationError

def get_og_image(url: str) -> tuple[str, str | None]:
    """
    Inspecciona la cabecera HTML de una página web pública para extraer la imagen principal.
    Retorna (image_url, error_message).
    """
    try:
        validate_safe_public_url(url)
    except SSRFValidationError as e:
        return "", f"URL inválida o bloqueada por política de seguridad: {e}"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AndroidHomeServer/2.0; +https://github.com/moisesvalero)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        opener = build_safe_opener()
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=12) as resp:
            # Leer únicamente los primeros 300KB donde se ubica el <head>
            chunk = resp.read(300000)
            html = chunk.decode("utf-8", errors="replace")

        # Expresiones regulares para metadatos de imagen
        patterns = [
            r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
            r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        ]

        for p in patterns:
            m = re.search(p, html, re.IGNORECASE)
            if m:
                raw_img = m.group(1).strip()
                if raw_img and not raw_img.startswith("data:"):
                    candidate = urljoin(url, raw_img)
                    # Validar que la URL de imagen extraída también sea segura
                    try:
                        validate_safe_public_url(candidate)
                        return candidate, None
                    except SSRFValidationError:
                        continue

        return "", "No se encontró etiqueta og:image ni twitter:image válida"
    except Exception as e:
        return "", f"Error al procesar la página: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "image_url": "", "error": "Uso: get_og_image.py <url>"}))
        sys.exit(1)

    target_url = sys.argv[1]
    img_url, error = get_og_image(target_url)
    if img_url:
        print(json.dumps({"ok": True, "image_url": img_url, "error": None}))
        sys.exit(0)
    else:
        print(json.dumps({"ok": False, "image_url": "", "error": error or "No og:image found"}))
        sys.exit(1)
