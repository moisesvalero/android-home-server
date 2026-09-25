#!/usr/bin/env python3
"""
Módulo de seguridad de red y prevención de SSRF para Android Hermes Server.
Valida URLs públicas HTTPS, restringe rangos de IP no seguros y descarga imágenes de forma controlada.
"""
import ipaddress
import socket
import urllib.parse
import urllib.request
import urllib.error

ALLOWED_SCHEMES = {"https"}
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif"
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


class SSRFValidationError(ValueError):
    """Excepción lanzada cuando una URL viola las políticas de seguridad anti-SSRF."""
    pass


def is_ip_safe(ip_str: str) -> bool:
    """
    Verifica si una IP dada es pública y segura.
    Retorna False si es privada, loopback, link-local, multicast, reservada o no especificada.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        return True
    except ValueError:
        return False


def validate_safe_public_url(url: str) -> str:
    """
    Valida rigurosamente que una URL use HTTPS y que su hostname resuelva únicamente a IPs públicas y seguras.
    Lanza SSRFValidationError si la URL no cumple los requisitos.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL vacía o no válida.")

    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"Esquema no permitido '{parsed.scheme}'. Solo se admite HTTPS.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("La URL no contiene un nombre de host válido.")

    hostname_lower = hostname.lower()
    if (
        hostname_lower == "localhost"
        or hostname_lower.endswith(".local")
        or hostname_lower.endswith(".internal")
        or hostname_lower.endswith(".localhost")
    ):
        raise SSRFValidationError(f"Nombre de host bloqueado: '{hostname}'")

    # Si el hostname es directamente una dirección IP, validarla
    try:
        ipaddress.ip_address(hostname)
        if not is_ip_safe(hostname):
            raise SSRFValidationError(f"La dirección IP '{hostname}' está en un rango privado o reservado.")
        return url
    except ValueError:
        pass

    # Resolver hostname mediante DNS y verificar todas las IPs devueltas
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = set()
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            resolved_ips.add(ip_str)

        if not resolved_ips:
            raise SSRFValidationError(f"No se pudo resolver la dirección para '{hostname}'.")

        for ip_str in resolved_ips:
            if not is_ip_safe(ip_str):
                raise SSRFValidationError(
                    f"El host '{hostname}' resuelve a una IP no segura o privada: '{ip_str}'."
                )
    except socket.gaierror as e:
        raise SSRFValidationError(f"Error de resolución DNS para '{hostname}': {e}")

    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Manejador de redirecciones que valida que la URL de destino sea segura antes de seguirla."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Resolver URL relativa si aplica
        safe_newurl = urllib.parse.urljoin(req.full_url, newurl)
        validate_safe_public_url(safe_newurl)
        return super().redirect_request(req, fp, code, msg, headers, safe_newurl)


def build_safe_opener():
    """Construye un opener de urllib con manejador estricto de redirecciones."""
    return urllib.request.build_opener(SafeRedirectHandler())


def safe_download_image(
    url: str,
    max_bytes: int = MAX_IMAGE_BYTES,
    timeout: int = 15
) -> tuple[bytes, str]:
    """
    Descarga una imagen de forma segura validando URL, IPs, redirecciones, Content-Type y tamaño máximo.
    Retorna (image_data, content_type).
    Lanza SSRFValidationError o IOError ante cualquier irregularidad.
    """
    validate_safe_public_url(url)
    opener = build_safe_opener()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AndroidHomeServer/2.0; +https://github.com/moisesvalero)",
        "Accept": "image/jpeg,image/png,image/webp,image/gif,*/*;q=0.8"
    }
    req = urllib.request.Request(url, headers=headers)

    with opener.open(req, timeout=timeout) as resp:
        content_type_header = resp.headers.get("Content-Type", "").lower()
        content_type = content_type_header.split(";")[0].strip()

        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise SSRFValidationError(
                f"Content-Type no permitido: '{content_type_header}'. "
                f"Se requiere uno de: {sorted(list(ALLOWED_IMAGE_CONTENT_TYPES))}"
            )

        content_length = resp.headers.get("Content-Length")
        if content_length:
            try:
                content_length_int = int(content_length)
            except ValueError:
                # Header Content-Length malformado: se ignora; el límite se aplica
                # igualmente durante la lectura por bloques más abajo.
                content_length_int = None
            if content_length_int is not None and content_length_int > max_bytes:
                raise SSRFValidationError(
                    f"El tamaño de la imagen ({content_length} bytes) excede el máximo permitido ({max_bytes} bytes)."
                )

        # Leer en bloques garantizando el límite de bytes
        data = bytearray()
        block_size = 64 * 1024
        while True:
            chunk = resp.read(block_size)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise SSRFValidationError(
                    f"Descarga abortada: superó el límite de {max_bytes} bytes."
                )

        return bytes(data), content_type
