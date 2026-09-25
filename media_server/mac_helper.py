#!/usr/bin/env python3
"""
mac_helper.py — Micro-asistente local para conversión rápida en el Mac
======================================================================
Servicio local ultraligero (puerto 8095) que permite al Dashboard del Android Server
convertir vídeos incompatibles (como .avi) usando la potencia del Mac (ffmpeg)
con un solo clic y subirlos automáticamente al servidor sin saturar el móvil.
"""

from __future__ import annotations

import sys
import os
import shutil
import hashlib
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

PORT = 8095
TEMP_DIR = Path("/tmp/android_mac_transcode")


def get_ffmpeg_path() -> str | None:
    """Obtiene la ruta a ffmpeg en macOS, con soporte para Homebrew."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    for fallback in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
        if os.path.isfile(fallback) and os.access(fallback, os.X_OK):
            return fallback
    return None


def check_ffmpeg() -> bool:
    """Verifica si ffmpeg está disponible en el sistema."""
    return get_ffmpeg_path() is not None


def format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit in ['MB', 'GB'] else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


class MacHelperHandler(BaseHTTPRequestHandler):
    server_version = "MediaMacHelper/1.0"

    def _send_json(self, data: dict, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/api/status", "/status", "/ping"]:
            self._send_json({
                "status": "ok",
                "ffmpeg": check_ffmpeg(),
                "helper": "media-mac-helper",
                "version": "1.0"
            })
            return

        self.send_error(404, "Endpoint no encontrado")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/convert":
            raw_name = query.get("name", ["video.avi"])[0]
            category = query.get("category", ["peliculas"])[0]
            server_url = query.get("server_url", [""])[0]

            safe_name = os.path.basename(raw_name).strip() or "video.avi"
            stem = Path(safe_name).stem
            out_name = f"{stem}.mp4"

            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            input_file = TEMP_DIR / safe_name
            temp_output = TEMP_DIR / f"{out_name}.convirtiendo"
            final_output = TEMP_DIR / out_name

            # 1. Leer el archivo recibido desde el navegador
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json({"error": "Archivo vacío o Content-Length ausente"}, 400)
                return

            print(f"[*] [Mac Helper] Recibiendo '{safe_name}' ({format_bytes(content_length)})...")
            remaining = content_length
            chunk_size = 64 * 1024
            with open(input_file, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, chunk_size))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            if not input_file.exists() or input_file.stat().st_size == 0:
                self._send_json({"error": "No se pudo recibir el archivo"}, 400)
                return

            ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
            print(f"[*] [Mac Helper] Convirtiendo en el Mac a MP4 con {ffmpeg_bin}...")
            # 2. Ejecutar ffmpeg con los parámetros certificados
            cmd = [
                ffmpeg_bin, "-y", "-i", str(input_file),
                "-c:v", "libx264", "-profile:v", "main", "-level", "4.0", "-crf", "20",
                "-preset", "medium", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000",
                "-map_metadata", "-1", "-movflags", "+faststart",
                str(temp_output)
            ]

            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc.returncode != 0 or not temp_output.exists():
                input_file.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                self._send_json({"error": "Falló la transcodificación con ffmpeg en el Mac"}, 500)
                return

            # 3. Verificación de integridad por SHA-256
            hasher = hashlib.sha256()
            with open(temp_output, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            sha256_hash = hasher.hexdigest()

            # Renombrar de .convirtiendo a .mp4
            temp_output.rename(final_output)
            print(f"[✓] [Mac Helper] Conversión lista: {out_name} (SHA256: {sha256_hash[:8]}...)")

            # 4. Si se proporcionó URL del servidor, subir directamente
            uploaded = False
            if server_url:
                try:
                    upload_target = f"{server_url}?name={urllib.parse.quote(out_name)}&category={urllib.parse.quote(category)}"
                    print(f"[*] [Mac Helper] Subiendo automáticamente al Android Server: {upload_target}...")
                    file_size = final_output.stat().st_size
                    with open(final_output, "rb") as f_out:
                        req = urllib.request.Request(
                            upload_target,
                            data=f_out,
                            headers={
                                "Content-Type": "application/octet-stream",
                                "Content-Length": str(file_size)
                            },
                            method="POST"
                        )
                        with urllib.request.urlopen(req, timeout=300) as resp:
                            if resp.status == 200:
                                uploaded = True
                                print(f"[✓] [Mac Helper] Subida completada con éxito al Android Server!")
                except Exception as e:
                    print(f"[!] [Mac Helper] Error subiendo al servidor: {e}", file=sys.stderr)

            # Limpiar archivo original temporal
            input_file.unlink(missing_ok=True)
            if uploaded:
                final_output.unlink(missing_ok=True)

            self._send_json({
                "status": "ok",
                "filename": out_name,
                "sha256": sha256_hash,
                "uploaded": uploaded,
                "message": "Vídeo convertido y subido al Android Server con éxito"
            })
            return

        self.send_error(404, "Endpoint no encontrado")

    def log_message(self, format: str, *args) -> None:
        # Silenciar logs ruidosos
        pass


def run_helper(port: int = PORT) -> None:
    server = HTTPServer(("127.0.0.1", port), MacHelperHandler)
    print(f"=== 🪄 servidor Mac Helper activo en http://127.0.0.1:{port} ===")
    print("Listo para convertir vídeos incompatibles con 1 clic desde el Dashboard.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Cerrando Mac Helper...")
        server.server_close()


if __name__ == "__main__":
    run_helper()
