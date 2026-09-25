#!/usr/bin/env python3
"""
Publicador en Bluesky desde Android Home Server.
Soporta texto e imágenes con facets de enlaces automáticos.
Descargas protegidas contra SSRF, límites de tamaño y limpieza garantizada de temporales.

Uso:
    python bsky_post.py "Texto del post aquí"
    python bsky_post.py --file /tmp/post.txt
    python bsky_post.py "Texto" --image /ruta/imagen.jpg
    python bsky_post.py "Texto" --image-url https://ejemplo.com/imagen.jpg
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import re
import tempfile

from hermes_config import get_env_var
from network_security import safe_download_image, SSRFValidationError

try:
    from atproto import Client, models
except ImportError:
    Client = None
    models = None

BSKY_HANDLE = "tu_handle.bsky.social"
MAX_POST_CHARS = 300


def get_pass() -> str:
    """Obtiene la contraseña de aplicación de Bluesky mediante hermes_config o entorno."""
    return get_env_var("BSKY_PASS", "")


def validate_post_text(text: str) -> str:
    """
    Valida que el texto no esté vacío y no supere el límite de 300 caracteres de Bluesky.
    Lanza ValueError si no es válido.
    """
    if not text or not text.strip():
        raise ValueError("El texto del post no puede estar vacío.")
    
    clean_text = text.strip()
    if len(clean_text) > MAX_POST_CHARS:
        raise ValueError(
            f"El texto excede el límite de Bluesky ({len(clean_text)} > {MAX_POST_CHARS} caracteres)."
        )
    return clean_text


def post_to_bluesky(text: str, image_path: str | None = None) -> dict:
    """Publica un post en Bluesky con facets de enlace e imagen opcional."""
    if Client is None or models is None:
        return {
            "ok": False,
            "error": "El paquete 'atproto' no está instalado en este intérprete de Python."
        }

    pw = get_pass()
    if not pw:
        return {"ok": False, "error": "Variable BSKY_PASS no configurada en entorno ni en .env."}

    try:
        text = validate_post_text(text)
    except ValueError as val_err:
        return {"ok": False, "error": str(val_err)}

    try:
        cl = Client()
        cl.login(BSKY_HANDLE, pw)

        # Crear facets para todas las URLs para que sean clicables
        # CRITICAL: usar byte offsets (UTF-8), no character offsets
        facets = []
        for m in re.finditer(r'https?://[^\s]+', text):
            byte_start = len(text[:m.start()].encode('utf-8'))
            byte_end = len(text[:m.end()].encode('utf-8'))
            facets.append(models.AppBskyRichtextFacet.Main(
                features=[models.AppBskyRichtextFacet.Link(uri=m.group())],
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byte_start=byte_start, byte_end=byte_end
                )
            ))

        embed = None
        if image_path and os.path.isfile(image_path):
            with open(image_path, "rb") as f:
                img_data = f.read()
            upload = cl.upload_blob(img_data)
            embed = models.AppBskyEmbedImages.Main(images=[
                models.AppBskyEmbedImages.Image(alt="Attachment", image=upload.blob)
            ])

        response = cl.send_post(text, facets=facets if facets else None, embed=embed)
        post_uri = getattr(response, "uri", "")
        post_cid = getattr(response, "cid", "")
        
        return {
            "ok": True,
            "uri": post_uri,
            "cid": post_cid,
            "with_image": image_path is not None,
            "links": len(facets)
        }
    except Exception as e:
        return {"ok": False, "error": f"Error publicando en Bluesky: {e}"}


def main():
    parser = argparse.ArgumentParser(description="Publicar en Bluesky con validaciones y seguridad.")
    parser.add_argument("text", nargs="?", help="Texto del post")
    parser.add_argument("--file", help="Ruta al archivo con el texto del post")
    parser.add_argument("--image", help="Ruta local de la imagen a adjuntar")
    parser.add_argument("--image-url", help="URL segura HTTPS de la imagen a descargar y adjuntar")
    args = parser.parse_args()

    text = None
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read().strip()
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"No se pudo leer el archivo de texto: {e}"}))
            sys.exit(1)
    elif args.text:
        text = args.text

    if not text:
        print(json.dumps({"ok": False, "error": "No se proporcionó texto para el post"}))
        sys.exit(1)

    image_path = args.image
    temp_file_created = False
    temp_image_path = None

    try:
        # Descarga segura si se proporciona --image-url
        if args.image_url and not image_path:
            try:
                img_bytes, content_type = safe_download_image(args.image_url)
                ext_map = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                    "image/gif": ".gif"
                }
                suffix = ext_map.get(content_type, ".jpg")
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(img_bytes)
                tmp.flush()
                tmp.close()
                temp_image_path = tmp.name
                image_path = temp_image_path
                temp_file_created = True
            except (SSRFValidationError, IOError, Exception) as dl_err:
                print(json.dumps({"ok": False, "error": f"Fallo al descargar la imagen de forma segura: {dl_err}"}))
                sys.exit(1)

        result = post_to_bluesky(text, image_path)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    finally:
        # Limpieza incondicional garantizada de archivos temporales
        if temp_file_created and temp_image_path and os.path.exists(temp_image_path):
            try:
                os.unlink(temp_image_path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
