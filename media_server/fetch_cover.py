#!/usr/bin/env python3
"""
fetch_cover.py — Descargador automático de carátulas para MiniDLNA / Samsung TV
=============================================================================
Obtiene la carátula oficial en alta definición desde las APIs públicas de TVMaze,
IMDb e iTunes (sin registro, gratuitas, sin API key) y la guarda asociada al vídeo.
Totalmente protegido contra nombres de carpetas reservadas ("peliculas", "series", etc.).
"""

from __future__ import annotations

import sys
import os
import re
import json
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Tuple, Optional

# Nombres de carpetas reservadas del sistema que jamás deben usarse como término de búsqueda
CARPETAS_RESERVADAS = {"peliculas", "series", "media", "dashboard", "root", "home", "downloads"}


def limpiar_nombre(nombre_crudo: str) -> Tuple[str, Optional[str], bool]:
    """
    Limpia la basura típica de los nombres de torrents y descargas:
    resoluciones, códecs, formatos, grupos de ripeo, marcas de episodio, etc.
    Devuelve: (titulo_limpio, año, es_serie)
    """
    base = Path(nombre_crudo).stem

    # 1. Detectar si es una serie (soporta español e inglés: S01E02, 1x03, Temporada 1, Season 1, Cap.402, Ep. 1, etc.)
    regex_serie = r'(?i)(s\d+e\d+|\d+x\d+|temporada\s*\d+|season\s*\d+|cap(?:itulo)?\s*\.?\s*\d+|ep(?:isodio)?\s*\.?\s*\d+)'
    es_serie = bool(re.search(regex_serie, base))

    # Cortar a partir del marcador de serie si existe para aislar el título
    match_serie = re.search(r'(?i)(.*?)[.\s_\[-]+(?:s\d+e\d+|\d+x\d+|temporada|season|cap(?:itulo)?|ep(?:isodio)?)', base)
    if match_serie and match_serie.group(1).strip():
        base = match_serie.group(1)

    # 2. Detectar año (1900-2099)
    año = None
    match_año = re.search(r'\b(19\d\d|20\d\d)\b', base)
    if match_año:
        año = match_año.group(1)
        partes = re.split(r'\b(?:19\d\d|20\d\d)\b', base, maxsplit=1)
        if partes[0].strip():
            base = partes[0]

    # 3. Reemplazar separadores por espacios
    texto = re.sub(r'[._+]', ' ', base)

    # 4. Lista exhaustiva de etiquetas de torrent y metadatos a descartar
    patrones_basura = [
        r'(?i)\b(1080p|720p|2160p|4k|uhd|bluray|bdrip|brrip|dvdrip|web-?dl|webrip|hdtv|hdrip)\b',
        r'(?i)\b(x264|x265|h264|h265|hevc|avc|10bit|hdr|hdr10|dolby|vision|atmos)\b',
        r'(?i)\b(ac3|dts|aac|mp3|eac3|truehd|dual|latino|castellano|spanish|español|multi|sub|subs)\b',
        r'(?i)\b(extended|remastered|unrated|directors|cut|proper|repack)\b',
        r'\[.*?\]|\(.*?\)',  # corchetes o paréntesis residuales
    ]

    for p in patrones_basura:
        texto = re.sub(p, ' ', texto)

    titulo_limpio = ' '.join(texto.split()).strip()
    return titulo_limpio, año, es_serie


def buscar_caratula_tvmaze(titulo: str) -> Optional[str]:
    """Busca carátula oficial en TVMaze (API abierta y especializada en series de TV)."""
    try:
        url = f"https://api.tvmaze.com/singlesearch/shows?{urllib.parse.urlencode({'q': titulo})}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MiniDLNA-CoverBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            img = data.get("image") or {}
            return img.get("original") or img.get("medium")
    except Exception:
        return None


def buscar_caratula_imdb(titulo: str, año: Optional[str] = None, solo_series: bool = False) -> Optional[str]:
    """
    Busca carátula oficial en alta definición en la API pública de IMDb.
    """
    try:
        query = titulo.lower().strip()
        query_normalizada = re.sub(r'[^a-z0-9_]', '_', query.replace(' ', '_'))
        query_normalizada = re.sub(r'_+', '_', query_normalizada).strip('_')

        if not query_normalizada:
            return None

        primer_caracter = query_normalizada[0]
        url = f"https://v3.sg.media-imdb.com/suggestion/{primer_caracter}/{query_normalizada}.json"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
        )

        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            resultados = data.get("d", [])
            if not resultados:
                return None

            # Si se busca serie, priorizar entradas de TV
            if solo_series:
                for res in resultados:
                    q = (res.get("q") or "").lower()
                    if "series" in q or "tv" in q:
                        img_url = res.get("i", {}).get("imageUrl")
                        if img_url:
                            return img_url

            # Si se indicó año, buscar coincidencia de año
            if año:
                for res in resultados:
                    if str(res.get("y")) == str(año) and res.get("i", {}).get("imageUrl"):
                        return res["i"]["imageUrl"]

            # Si no hay año o no coincidió exactamente, tomar el primer resultado con póster
            for res in resultados:
                img_url = res.get("i", {}).get("imageUrl")
                if img_url:
                    return img_url

    except Exception as e:
        print(f"[!] Error buscando en IMDb para '{titulo}': {e}", file=sys.stderr)
        return None


def buscar_caratula_itunes(titulo: str) -> Optional[str]:
    """Busca póster de películas en alta resolución (1000x1500) en iTunes Search API."""
    try:
        url = f"https://itunes.apple.com/search?{urllib.parse.urlencode({'term': titulo, 'media': 'movie', 'limit': 1})}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            results = data.get("results", [])
            if results and "artworkUrl100" in results[0]:
                # Escalar la carátula de 100x100 a 1000x1500
                return results[0]["artworkUrl100"].replace("100x100bb", "1000x1500bb")
    except Exception:
        pass
    return None


def buscar_caratula(titulo: str, año: Optional[str], es_serie: bool) -> Optional[str]:
    """
    Busca la mejor carátula en alta definición combinando TVMaze, IMDb e iTunes.
    """
    # 1. Si es serie, priorizar TVMaze (fuente limpia de series de TV)
    if es_serie:
        url = buscar_caratula_tvmaze(titulo)
        if url:
            return url
        url = buscar_caratula_imdb(titulo, año, solo_series=True)
        if url:
            return url

    # 2. Si es película o falló búsqueda de series, probar IMDb
    url = buscar_caratula_imdb(titulo, año, solo_series=False)
    if url:
        return url

    # 3. Probar iTunes para películas
    url = buscar_caratula_itunes(titulo)
    if url:
        return url

    # 4. Fallback final a TVMaze
    return buscar_caratula_tvmaze(titulo)


def descargar_imagen(url: str, destino: Path) -> bool:
    """Descarga la imagen en la ruta indicada."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MiniDLNA-CoverBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            destino.write_bytes(content)
            return True
    except Exception as e:
        print(f"[!] Error descargando imagen desde {url}: {e}", file=sys.stderr)
        return False


def procesar_ruta(ruta_objetivo: str, categoria_sugerida: Optional[str] = None) -> bool:
    p = Path(ruta_objetivo).expanduser().resolve()
    if not p.exists():
        print(f"[!] La ruta no existe: {ruta_objetivo}", file=sys.stderr)
        return False

    directorio = p if p.is_dir() else p.parent

    # Si se pasa una carpeta reservada del sistema (ej: /media/peliculas), abortar
    if p.is_dir() and p.name.lower() in CARPETAS_RESERVADAS:
        print(f"[!] '{p.name}' es una carpeta de sistema reservada. No se descargará carátula genérica.", file=sys.stderr)
        return False

    if p.is_file():
        # Siempre preferir el nombre del archivo para no confundir con carpetas padre
        nombre_para_buscar = p.stem

        # Caso especial: Si el archivo solo contiene código de capítulo (ej: S01E01.mkv)
        # y la carpeta padre NO es reservada (ej: series/Ted Lasso/S01E01.mkv), usar la carpeta padre
        if re.match(r'(?i)^(s\d+e\d+|\d+x\d+|cap(?:itulo)?\s*\.?\s*\d+|ep\s*\.?\s*\d+)$', p.stem.strip()):
            if p.parent.name.lower() not in CARPETAS_RESERVADAS:
                nombre_para_buscar = p.parent.name
    else:
        nombre_para_buscar = p.name

    titulo, año, detectada_serie = limpiar_nombre(nombre_para_buscar)
    es_serie = detectada_serie or (categoria_sugerida == "series")

    if not titulo or titulo.lower() in CARPETAS_RESERVADAS:
        print(f"[-] Nombre no válido para buscar: '{titulo}'", file=sys.stderr)
        return False

    print(f"[*] Buscando carátula oficial para: '{titulo}' (Año: {año or 'N/A'}, Serie: {es_serie})...")

    img_url = buscar_caratula(titulo, año, es_serie)
    if not img_url:
        print(f"[-] No se encontró carátula en línea para '{titulo}'.")
        return False

    print(f"[+] Carátula encontrada: {img_url}")

    if p.is_file():
        # Guardar como <nombre_archivo>.jpg (asociación directa para Samsung TV y Dashboard)
        file_cover_path = directorio / f"{p.stem}.jpg"
        if descargar_imagen(img_url, file_cover_path):
            print(f"[✓] Guardado para vídeo: {file_cover_path}")

        # SOLO guardar 'cover.jpg' si estamos dentro de una subcarpeta dedicada (ej: /media/series/Ted Lasso/)
        # NUNCA en la raíz de 'peliculas/' o 'series/'
        if directorio.name.lower() not in CARPETAS_RESERVADAS:
            folder_cover = directorio / "cover.jpg"
            try:
                shutil.copy(file_cover_path, folder_cover)
                print(f"[✓] Guardado en subcarpeta: {folder_cover}")
            except Exception:
                pass
        return True
    else:
        # Si es un directorio dedicado (ej: /media/series/Ted Lasso)
        folder_cover = directorio / "cover.jpg"
        ok = descargar_imagen(img_url, folder_cover)
        if ok:
            print(f"[✓] Guardado en carpeta: {folder_cover}")
        return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 fetch_cover.py <ruta_archivo_o_carpeta> [categoria]")
        sys.exit(1)
    cat = sys.argv[2] if len(sys.argv) > 2 else None
    procesar_ruta(sys.argv[1], cat)
