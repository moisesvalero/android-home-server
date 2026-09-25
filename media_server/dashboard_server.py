#!/usr/bin/env python3
"""
dashboard_server.py — Servidor Web Visual para Android Media Server
===================================================================
Proporciona la interfaz visual (Drag & Drop, galería de carátulas,
gestor de almacenamiento y borrado) en el puerto 8090.

Aislamiento:
- Streaming a disco por bloques de 64 KB (memoria constante < 15 MB de RAM).
- Ejecución desatendida en PM2 (nombre: media-dashboard).
- No bloquea a Hermes Agent ni a MiniDLNA.
"""

from __future__ import annotations

import sys
import os
import json
import shutil
import socket
import urllib.parse
import subprocess
from pathlib import Path
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

# Rutas del entorno (se adaptan si se ejecutan en Termux o localmente en Mac)
HOME_DIR = Path.home()
TERMUX_HOME = Path("/data/data/com.termux/files/home")
MEDIA_ROOT = (TERMUX_HOME / "media" if TERMUX_HOME.exists() else HOME_DIR / "media").resolve()

PELICULAS_DIR = (MEDIA_ROOT / "peliculas").resolve()
SERIES_DIR = (MEDIA_ROOT / "series").resolve()
FETCH_COVER_SCRIPT = (MEDIA_ROOT / "fetch_cover.py").resolve()

# En caso de que se ejecute en el repo
REPO_DIR = Path(__file__).resolve().parent
DASHBOARD_HTML = REPO_DIR / "dashboard" / "index.html"
if not DASHBOARD_HTML.exists():
    DASHBOARD_HTML = MEDIA_ROOT / "dashboard" / "index.html"

# Extensiones reconocidas de vídeo e imagen
VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v", ".ts"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def format_bytes(size: int) -> str:
    """Convierte bytes a formato legible (MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit in ['MB', 'GB'] else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def get_system_metrics() -> Dict[str, Any]:
    """Recopila métricas reales de hardware: Batería (termux), RAM (psutil), almacenamiento y DLNA."""
    # 1. Almacenamiento
    try:
        total_b, used_b, free_b = shutil.disk_usage(str(MEDIA_ROOT if MEDIA_ROOT.exists() else HOME_DIR))
        storage = {
            "total_gb": round(total_b / (1024 ** 3), 1),
            "used_gb": round(used_b / (1024 ** 3), 1),
            "free_gb": round(free_b / (1024 ** 3), 1),
            "percent_used": round((used_b / total_b) * 100, 1) if total_b > 0 else 0.0
        }
    except Exception:
        storage = {"total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0, "percent_used": 0.0}

    # 2. Batería (vía termux-battery-status en Android)
    battery: Dict[str, Any] = {
        "percentage": 100,
        "temperature": 0.0,
        "status": "DESCONOCIDO",
        "plugged": "UNPLUGGED",
        "health": "GOOD",
        "voltage": 0,
        "available": False
    }
    try:
        output = subprocess.check_output(["termux-battery-status"], timeout=2)
        b_data = json.loads(output.decode("utf-8"))
        battery = {
            "percentage": int(b_data.get("percentage", 0)),
            "temperature": float(b_data.get("temperature", 0.0)),
            "status": str(b_data.get("status", "UNKNOWN")),
            "plugged": str(b_data.get("plugged", "UNPLUGGED")),
            "health": str(b_data.get("health", "GOOD")),
            "voltage": int(b_data.get("voltage", 0)),
            "available": True
        }
    except Exception:
        pass

    # 3. Memoria RAM (vía psutil si está disponible)
    ram: Dict[str, Any] = {
        "percent": 0.0,
        "used_gb": 0.0,
        "total_gb": 0.0,
        "available": False
    }
    try:
        import psutil
        vm = psutil.virtual_memory()
        ram = {
            "percent": round(vm.percent, 1),
            "used_gb": round(vm.used / (1024 ** 3), 1),
            "total_gb": round(vm.total / (1024 ** 3), 1),
            "available": True
        }
    except Exception:
        pass

    # 4. Estado de MiniDLNA (puerto 8200 local)
    dlna_online = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        res = sock.connect_ex(("127.0.0.1", 8200))
        dlna_online = (res == 0)
        sock.close()
    except Exception:
        pass

    # 5. Uptime del sistema (vía comando uptime)
    uptime_str = "Activo"
    try:
        out = subprocess.check_output(["uptime"], timeout=2).decode("utf-8").strip()
        if "up " in out:
            part = out.split("up ")[1].split(",")[0].strip()
            uptime_str = part
    except Exception:
        pass

    return {
        "storage": storage,
        "battery": battery,
        "ram": ram,
        "dlna_online": dlna_online,
        "uptime": uptime_str
    }


class MediaDashboardHandler(BaseHTTPRequestHandler):
    server_version = "AndroidMediaDashboard/1.0"

    # Segundos de inactividad tolerados mientras se recibe una subida. Evita que
    # una conexión que anuncia bytes y nunca los envía retenga un hilo del
    # servidor para siempre. Se aplica SÓLO a /api/upload: si se pusiera en
    # setup() afectaría también al streaming, y un vídeo en pausa más de este
    # tiempo dejaría de drenar el socket y se cortaría la reproducción.
    UPLOAD_TIMEOUT_SECONDS = 180

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status=status)

    def do_OPTIONS(self) -> None:
        """Soporte para preflight CORS."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. Servir interfaz HTML principal
        if path in ["/", "/index.html"]:
            if not DASHBOARD_HTML.exists():
                self.send_error(404, "Dashboard HTML no encontrado.")
                return
            content = DASHBOARD_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. API: Estado del almacenamiento (usado / libre)
        if path == "/api/storage":
            try:
                # shutil.disk_usage es nativo en Python estándar
                total, used, free = shutil.disk_usage(str(MEDIA_ROOT if MEDIA_ROOT.exists() else HOME_DIR))
                self._send_json({
                    "total_gb": total / (1024 ** 3),
                    "used_gb": used / (1024 ** 3),
                    "free_gb": free / (1024 ** 3),
                    "percent_used": (used / total) * 100 if total > 0 else 0
                })
            except Exception as e:
                self._send_error_json(f"Error consultando almacenamiento: {e}", 500)
            return

        # 2b. API: Métricas en tiempo real de hardware (Batería, RAM, Storage, DLNA, Uptime)
        if path == "/api/system":
            self._send_json(get_system_metrics())
            return

        # 3. API: Listado de medios con carátulas
        if path == "/api/media":
            items: List[Dict[str, Any]] = []

            for category, cat_dir in [("peliculas", PELICULAS_DIR), ("series", SERIES_DIR)]:
                if not cat_dir.exists():
                    continue

                for root, _, files in os.walk(cat_dir):
                    root_path = Path(root)
                    for f in files:
                        file_path = root_path / f
                        if file_path.suffix.lower() in VIDEO_EXTS:
                            stat = file_path.stat()
                            
                            # Comprobar si existe carátula específica o de carpeta
                            cover_file = file_path.with_suffix(".jpg")
                            folder_cover = root_path / "cover.jpg"
                            
                            has_cover = False
                            cover_rel = ""
                            if cover_file.exists():
                                has_cover = True
                                cover_rel = str(cover_file.relative_to(MEDIA_ROOT))
                            elif folder_cover.exists():
                                has_cover = True
                                cover_rel = str(folder_cover.relative_to(MEDIA_ROOT))

                            # Generar título limpio (usando helper o regex)
                            clean_title = file_path.stem.replace(".", " ").replace("_", " ")
                            
                            items.append({
                                "filename": file_path.name,
                                "clean_title": clean_title,
                                "category": category,
                                "rel_path": str(file_path.relative_to(MEDIA_ROOT)),
                                "size_bytes": stat.st_size,
                                "size_formatted": format_bytes(stat.st_size),
                                "mtime": stat.st_mtime,
                                "has_cover": has_cover,
                                "cover_path": cover_rel
                            })

            # Ordenar del más reciente al más antiguo
            items.sort(key=lambda x: x["mtime"], reverse=True)
            self._send_json(items)
            return

        # 0. Favicon
        if path in ["/favicon.ico", "/favicon.svg"]:
            svg_icon = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#818cf8"/><stop offset="50%" stop-color="#6366f1"/><stop offset="100%" stop-color="#4f46e5"/></linearGradient></defs><rect width="32" height="32" rx="8" fill="#090d16"/><rect x="1" y="1" width="30" height="30" rx="7" fill="none" stroke="rgba(255,255,255,0.1)"/><path d="M12 9l12 7-12 7V9z" fill="url(#g)"/></svg>'''
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg_icon)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            self.wfile.write(svg_icon)
            return

        # 4. API: Servir carátula local
        if path == "/api/cover":
            target_rel = query.get("path", [""])[0]
            if not target_rel:
                self.send_error(400, "Falta parámetro path.")
                return

            try:
                # Prevenir path traversal e inspección de archivos no autorizados
                target_file = (MEDIA_ROOT / target_rel).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self.send_error(403, "Acceso denegado.")
                    return
                if not target_file.is_file() or target_file.suffix.lower() not in IMAGE_EXTS:
                    self.send_error(404, "Carátula no encontrada o formato no permitido.")
                    return

                data = target_file.read_bytes()
                content_type = "image/png" if target_file.suffix.lower() == ".png" else "image/jpeg"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(404, f"No se pudo cargar la carátula: {e}")
            return

        # 5. API: Streaming de vídeo en navegador (HTTP 206 Partial Content)
        if path == "/api/stream":
            target_rel = query.get("path", [""])[0]
            if not target_rel:
                self.send_error(400, "Falta parámetro path.")
                return

            try:
                target_file = (MEDIA_ROOT / target_rel).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self.send_error(403, "Acceso denegado.")
                    return
                if not target_file.is_file() or target_file.suffix.lower() not in VIDEO_EXTS:
                    self.send_error(404, "Vídeo no encontrado o formato no permitido.")
                    return

                file_size = target_file.stat().st_size
                range_header = self.headers.get("Range", "")

                content_type = "video/mp4"
                if target_file.suffix.lower() == ".mkv":
                    content_type = "video/x-matroska"
                elif target_file.suffix.lower() == ".webm":
                    content_type = "video/webm"

                if range_header:
                    ranges = range_header.replace("bytes=", "").split("-")
                    start = int(ranges[0]) if ranges[0] else 0
                    end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else file_size - 1
                    end = min(end, file_size - 1)
                    length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(target_file, "rb") as f:
                        f.seek(start)
                        bytes_to_send = length
                        chunk_size = 64 * 1024
                        while bytes_to_send > 0:
                            chunk = f.read(min(bytes_to_send, chunk_size))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            bytes_to_send -= len(chunk)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(file_size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    with open(target_file, "rb") as f:
                        shutil.copyfileobj(f, self.wfile, length=64 * 1024)

            except Exception:
                pass
            return

        self.send_error(404, "Endpoint no encontrado.")

    def _read_json_body(self) -> Dict[str, Any]:
        """Lee y parsea de forma segura el cuerpo JSON de una petición POST."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                return json.loads(body.decode("utf-8"))
        except Exception:
            pass
        return {}

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. API: Subida de archivos con streaming directo a disco
        if path == "/api/upload":
            raw_name = query.get("name", [""])[0] or query.get("filename", [""])[0]
            category = query.get("category", ["peliculas"])[0]

            if not raw_name:
                self._send_error_json("Nombre de archivo no especificado.", 400)
                return

            # Limpiar nombre para evitar path traversal
            safe_name = os.path.basename(raw_name).strip()
            if not safe_name or safe_name in {".", ".."} or safe_name.startswith("."):
                self._send_error_json("Nombre de archivo inválido.", 400)
                return

            if Path(safe_name).suffix.lower() not in VIDEO_EXTS:
                self._send_error_json("Formato no permitido. Solo se admiten archivos de vídeo.", 400)
                return

            if Path(safe_name).suffix.lower() == ".avi":
                self._send_error_json("El formato .avi (DivX/Xvid) no es compatible con la Smart TV Samsung. Conviértelo a MP4 con el botón mágico.", 400)
                return

            target_dir = SERIES_DIR if category == "series" else PELICULAS_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = (target_dir / safe_name).resolve()

            # Verificación de confinamiento en target_dir
            if not target_file.is_relative_to(target_dir) or target_file == target_dir:
                self._send_error_json("Acceso denegado: ruta no permitida.", 403)
                return

            # El servidor habla HTTP/1.0, que no admite Transfer-Encoding chunked.
            # Sin esta comprobación los bytes de framing se escribirían crudos
            # dentro del vídeo (archivo corrupto) y el hilo se quedaría esperando.
            transfer_encoding = (self.headers.get("Transfer-Encoding") or "").strip().lower()
            if transfer_encoding and transfer_encoding != "identity":
                self._send_error_json(
                    "Transfer-Encoding no soportado. Envía el tamaño del archivo en Content-Length.", 411
                )
                return

            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._send_error_json("Falta la cabecera Content-Length.", 411)
                return

            try:
                content_length = int(raw_length)
            except (TypeError, ValueError):
                self._send_error_json("Content-Length inválido.", 400)
                return

            if content_length < 0:
                self._send_error_json("Content-Length inválido.", 400)
                return

            # Cuerpo vacío: el navegador no pudo leer el archivo. Antes se entraba
            # en un bucle de lectura que bloqueaba el hilo para siempre ("Iniciando...").
            if content_length == 0:
                self._send_error_json(
                    "El archivo llegó vacío (0 bytes). Vuelve a seleccionarlo o arrástralo de nuevo.", 400
                )
                return

            print(f"[*] Recibiendo subida: '{safe_name}' ({format_bytes(content_length)}) en {category}...")

            # Timeout acotado a la recepción del cuerpo de la subida
            try:
                self.connection.settimeout(self.UPLOAD_TIMEOUT_SECONDS)
            except OSError:
                pass

            interrupted = False
            try:
                # Streaming en bloques de 64 KB a disco para no ocupar memoria RAM
                remaining = content_length
                chunk_size = 64 * 1024  # 64 KB
                with open(target_file, "wb") as f:
                    while remaining > 0:
                        read_bytes = min(remaining, chunk_size)
                        try:
                            chunk = self.rfile.read(read_bytes)
                        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                            interrupted = True
                            break
                        if not chunk:
                            interrupted = True
                            break
                        f.write(chunk)
                        remaining -= len(chunk)
            except Exception as e:
                # Fallo real de escritura (disco lleno, permisos...): el parcial
                # no sirve para nada, así que se descarta en vez de dejar un
                # vídeo incompleto en la biblioteca.
                target_file.unlink(missing_ok=True)
                print(f"[!] Error durante la subida: {e}", file=sys.stderr)
                self._send_error_json(f"Error escribiendo archivo: {e}", 500)
                return

            if interrupted:
                # El cliente canceló o reinició la subida. Se descarta el
                # parcial para no dejar un vídeo incompleto visible en la
                # biblioteca (el cliente siempre reenvía el archivo entero).
                saved = target_file.stat().st_size if target_file.exists() else 0
                target_file.unlink(missing_ok=True)
                print(f"[~] Subida interrumpida ({format_bytes(saved)} descartados): {safe_name}")
                try:
                    self._send_json({"status": "interrupted", "discarded": saved, "filename": safe_name}, status=499)
                except Exception:
                    pass  # Conexión ya cerrada por el cliente
                return

            # A partir de aquí el archivo ya está completo en disco: nada de lo
            # que falle después (carátula o respuesta) debe borrarlo.
            print(f"[✓] Archivo guardado con éxito: {target_file}")

            # Lanzar en segundo plano la descarga de carátula pasando la categoría
            cover_script = FETCH_COVER_SCRIPT if FETCH_COVER_SCRIPT.exists() else (REPO_DIR / "fetch_cover.py")
            if cover_script.exists():
                try:
                    subprocess.Popen(
                        [sys.executable, str(cover_script), str(target_file), category],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                except Exception as e:
                    print(f"[!] No se pudo invocar fetch_cover: {e}", file=sys.stderr)

            try:
                self._send_json({"status": "ok", "filename": safe_name, "category": category})
            except Exception:
                pass  # El archivo ya está guardado; la conexión se cerró al responder
            return

        # 2. API: Renombrar archivo de vídeo y su carátula
        if path == "/api/media/rename":
            body = self._read_json_body()
            rel_path = body.get("path") or query.get("path", [""])[0]
            new_name = body.get("new_name") or query.get("new_name", [""])[0]

            if not rel_path or not new_name:
                self._send_error_json("Parámetros 'path' y 'new_name' requeridos.", 400)
                return

            safe_new_name = os.path.basename(new_name).strip()
            if not safe_new_name or safe_new_name in {".", ".."} or safe_new_name.startswith("."):
                self._send_error_json("Nuevo nombre inválido.", 400)
                return

            if Path(safe_new_name).suffix.lower() not in VIDEO_EXTS:
                self._send_error_json("El nuevo archivo debe conservar una extensión de vídeo válida.", 400)
                return

            try:
                target_file = (MEDIA_ROOT / rel_path).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado.", 403)
                    return

                if not target_file.is_file():
                    self._send_error_json("Archivo original no encontrado.", 404)
                    return

                dest_file = (target_file.parent / safe_new_name).resolve()
                if not (dest_file.is_relative_to(PELICULAS_DIR) or dest_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado a destino.", 403)
                    return

                if dest_file.exists() and dest_file != target_file:
                    self._send_error_json("Ya existe un archivo con ese nombre.", 409)
                    return

                target_file.rename(dest_file)

                # Renombrar carátula asociada si existe
                old_cover = target_file.with_suffix(".jpg")
                new_cover = dest_file.with_suffix(".jpg")
                if old_cover.exists() and old_cover.is_file():
                    old_cover.rename(new_cover)

                print(f"[✓] Vídeo renombrado: {target_file.name} -> {dest_file.name}")
                self._send_json({
                    "status": "ok",
                    "old_path": rel_path,
                    "new_path": str(dest_file.relative_to(MEDIA_ROOT)),
                    "new_name": dest_file.name
                })
            except Exception as e:
                self._send_error_json(f"Error renombrando archivo: {e}", 500)
            return

        # 3. API: Mover archivo entre categorías (peliculas <-> series)
        if path == "/api/media/move":
            body = self._read_json_body()
            rel_path = body.get("path") or query.get("path", [""])[0]
            destination = (body.get("destination") or query.get("destination", ["peliculas"])[0]).lower()

            if not rel_path or destination not in {"peliculas", "series"}:
                self._send_error_json("Parámetros 'path' y 'destination' (peliculas/series) requeridos.", 400)
                return

            try:
                target_file = (MEDIA_ROOT / rel_path).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado.", 403)
                    return

                if not target_file.is_file():
                    self._send_error_json("Archivo no encontrado.", 404)
                    return

                target_dir = SERIES_DIR if destination == "series" else PELICULAS_DIR
                dest_file = (target_dir / target_file.name).resolve()

                if dest_file == target_file:
                    self._send_json({"status": "ok", "message": "El archivo ya está en el destino.", "new_path": rel_path})
                    return

                target_file.rename(dest_file)

                # Mover carátula asociada si existe
                old_cover = target_file.with_suffix(".jpg")
                new_cover = dest_file.with_suffix(".jpg")
                if old_cover.exists() and old_cover.is_file():
                    old_cover.rename(new_cover)

                print(f"[✓] Vídeo movido a {destination}: {target_file.name}")
                self._send_json({
                    "status": "ok",
                    "new_path": str(dest_file.relative_to(MEDIA_ROOT)),
                    "destination": destination
                })
            except Exception as e:
                self._send_error_json(f"Error moviendo archivo: {e}", 500)
            return

        # 4. API: Copiar archivo entre categorías
        if path == "/api/media/copy":
            body = self._read_json_body()
            rel_path = body.get("path") or query.get("path", [""])[0]
            destination = (body.get("destination") or query.get("destination", ["peliculas"])[0]).lower()

            if not rel_path or destination not in {"peliculas", "series"}:
                self._send_error_json("Parámetros 'path' y 'destination' requeridos.", 400)
                return

            try:
                target_file = (MEDIA_ROOT / rel_path).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado.", 403)
                    return

                if not target_file.is_file():
                    self._send_error_json("Archivo no encontrado.", 404)
                    return

                target_dir = SERIES_DIR if destination == "series" else PELICULAS_DIR
                dest_name = target_file.name
                dest_file = (target_dir / dest_name).resolve()

                # Si ya existe en destino, agregar sufijo _copia
                if dest_file.exists():
                    dest_name = f"{target_file.stem}_copia{target_file.suffix}"
                    dest_file = (target_dir / dest_name).resolve()

                shutil.copy2(target_file, dest_file)

                # Copiar carátula si existe
                old_cover = target_file.with_suffix(".jpg")
                new_cover = dest_file.with_suffix(".jpg")
                if old_cover.exists() and old_cover.is_file():
                    shutil.copy2(old_cover, new_cover)

                print(f"[✓] Vídeo copiado a {destination}: {dest_name}")
                self._send_json({
                    "status": "ok",
                    "new_path": str(dest_file.relative_to(MEDIA_ROOT)),
                    "destination": destination
                })
            except Exception as e:
                self._send_error_json(f"Error copiando archivo: {e}", 500)
            return

        # 5. API: Refrescar carátula oficial en segundo plano
        if path == "/api/media/cover":
            body = self._read_json_body()
            rel_path = body.get("path") or query.get("path", [""])[0]

            if not rel_path:
                self._send_error_json("Falta parámetro path.", 400)
                return

            try:
                target_file = (MEDIA_ROOT / rel_path).resolve()
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado.", 403)
                    return

                if not target_file.is_file():
                    self._send_error_json("Archivo no encontrado.", 404)
                    return

                cat = "series" if target_file.is_relative_to(SERIES_DIR) else "peliculas"
                cover_script = FETCH_COVER_SCRIPT if FETCH_COVER_SCRIPT.exists() else (REPO_DIR / "fetch_cover.py")
                if cover_script.exists():
                    subprocess.Popen(
                        [sys.executable, str(cover_script), str(target_file), cat],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                self._send_json({"status": "fetching_cover", "path": rel_path})
            except Exception as e:
                self._send_error_json(f"Error invocando búsqueda de carátula: {e}", 500)
            return

        self.send_error(404, "Endpoint no encontrado.")

    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. API: Borrar archivo de vídeo y su carátula
        if path == "/api/media":
            rel_path = query.get("path", [""])[0]
            if not rel_path:
                self._send_error_json("Falta parámetro path.", 400)
                return

            try:
                target_file = (MEDIA_ROOT / rel_path).resolve()
                # Verificación estricta de seguridad: dentro de peliculas o series, archivo real y extensión de vídeo
                if not (target_file.is_relative_to(PELICULAS_DIR) or target_file.is_relative_to(SERIES_DIR)):
                    self._send_error_json("Acceso denegado: solo se pueden eliminar archivos de películas o series.", 403)
                    return

                if not target_file.is_file() or target_file.suffix.lower() not in VIDEO_EXTS:
                    self._send_error_json("Archivo no encontrado o tipo de archivo no permitido.", 404)
                    return

                # Borrar archivo de vídeo
                target_file.unlink()
                print(f"[✓] Vídeo eliminado: {target_file}")

                # Borrar carátula específica si existe
                cover_file = target_file.with_suffix(".jpg")
                if cover_file.exists() and cover_file.is_file() and (cover_file.is_relative_to(PELICULAS_DIR) or cover_file.is_relative_to(SERIES_DIR)):
                    cover_file.unlink()

                self._send_json({"status": "deleted", "path": rel_path})
            except Exception as e:
                self._send_error_json(f"Error eliminando archivo: {e}", 500)
            return

        self.send_error(404, "Endpoint no encontrado.")

    def log_message(self, format: str, *args: Any) -> None:
        # Logs limpios sin saturar stdout
        pass


def run_server(port: int = 8090) -> None:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    PELICULAS_DIR.mkdir(parents=True, exist_ok=True)
    SERIES_DIR.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("0.0.0.0", port), MediaDashboardHandler)
    print(f"=== 🎬 Android Media Dashboard activo en http://0.0.0.0:{port} ===")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Deteniendo servidor...")
        server.server_close()


if __name__ == "__main__":
    port_env = int(os.environ.get("PORT", "8090"))
    run_server(port_env)
