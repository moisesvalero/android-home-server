#!/usr/bin/env bash
# ==============================================================================
# ENVIAR PELÍCULAS O SERIES DEL MAC MINI AL Android Server
# ==============================================================================
# Transfiere el archivo por Wi-Fi usando SSH/SCP (puerto 8022 ya activo)
# y ejecuta automáticamente la descarga de la carátula oficial en el servidor.
#
# Uso:
#   ./media_server/enviar_al_servidor.sh "/ruta/a/Avatar.2009.1080p.mkv"
#   ./media_server/enviar_al_servidor.sh "/ruta/a/Breaking.Bad.S01E01.mkv"
#   ./media_server/enviar_al_servidor.sh "/ruta/a/The.Bear.S02" serie
# ==============================================================================
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-192.168.1.100}"
SERVER_PORT="${SERVER_PORT:-8022}"
SERVER_USER="${SERVER_USER:-u0_a256}"
REMOTE="${SERVER_USER}@${SERVER_HOST}"
SSH_OPTS=(-p "${SERVER_PORT}" -o ConnectTimeout=8)

# Colores para la terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

if [ $# -lt 1 ]; then
    echo -e "${YELLOW}Uso:${NC} $0 <archivo_o_carpeta_de_video> [peli|serie]"
    echo ""
    echo "Ejemplos:"
    echo "  $0 ~/Downloads/Avatar.2009.mkv"
    echo "  $0 ~/Downloads/Breaking.Bad.S01E01.mkv"
    exit 1
fi

ORIGEN="$1"
TIPO="${2:-auto}"

if [ ! -e "$ORIGEN" ]; then
    echo -e "${RED}[!] El archivo o carpeta no existe:${NC} $ORIGEN"
    exit 1
fi

NOMBRE_BASE="$(basename "$ORIGEN")"

# 0. Detección y conversión en el Mac si el formato es incompatible con Smart TV Samsung (.avi)
EXTENSION="${ORIGEN##*.}"
EXTENSION_LOWER="$(echo "$EXTENSION" | tr '[:upper:]' '[:lower:]')"
if [ "$EXTENSION_LOWER" = "avi" ]; then
    echo -e "${YELLOW}[!] El formato .avi (DivX/Xvid) no es compatible directamente con Smart TV Samsung (Tizen).${NC}"
    if command -v ffmpeg >/dev/null 2>&1; then
        STEM="${NOMBRE_BASE%.*}"
        DIR_ORIGEN="$(dirname "$ORIGEN")"
        DEST_MP4="${DIR_ORIGEN}/${STEM}.mp4"
        TEMP_MP4="${DIR_ORIGEN}/${STEM}.mp4.convirtiendo"
        
        echo -e "${BLUE}[*] Convirtiendo en tu Mac a MP4 compatible (H.264 / AAC) con -map_metadata -1...${NC}"
        ffmpeg -y -i "$ORIGEN" \
            -c:v libx264 -profile:v main -level 4.0 -crf 20 -preset medium \
            -pix_fmt yuv420p -c:a aac -b:a 192k -ac 2 -ar 48000 \
            -map_metadata -1 -movflags +faststart \
            "$TEMP_MP4"
        
        mv "$TEMP_MP4" "$DEST_MP4"
        echo -e "${GREEN}[✓] Vídeo convertido con éxito en el Mac: $(basename "$DEST_MP4")${NC}"
        ORIGEN="$DEST_MP4"
        NOMBRE_BASE="$(basename "$ORIGEN")"
    else
        echo -e "${RED}[!] Advertencia: ffmpeg no está instalado en este Mac. Se enviará el archivo original pero la tele podría rechazarlo.${NC}"
    fi
fi

# Detección automática del tipo si no se especificó
if [ "$TIPO" = "auto" ]; then
    if echo "$NOMBRE_BASE" | grep -Ei "(s[0-9]+e[0-9]+|[0-9]+x[0-9]+|temporada|season)" >/dev/null 2>&1; then
        TIPO="serie"
    else
        TIPO="peli"
    fi
fi

if [ "$TIPO" = "serie" ] || [ "$TIPO" = "series" ]; then
    DESTINO_REMOTO="media/series"
    echo -e "${BLUE}[*] Clasificado como:${NC} SERIE (${NOMBRE_BASE})"
else
    DESTINO_REMOTO="media/peliculas"
    echo -e "${BLUE}[*] Clasificado como:${NC} PELÍCULA (${NOMBRE_BASE})"
fi

echo -e "${BLUE}[*] Conectando con Android Server en ${SERVER_HOST}:${SERVER_PORT}...${NC}"

# 1. Comprobar conectividad rápida por SSH
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "${REMOTE}" "echo ok" >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] Comprobando conexión SSH interactiva con el servidor...${NC}"
fi

# 2. Transferencia usando rsync (con barra de progreso) si está disponible, o scp
echo -e "${BLUE}[*] Subiendo archivo al Android Server...${NC}"
if command -v rsync >/dev/null 2>&1; then
    rsync -avzP -e "ssh -p ${SERVER_PORT}" "$ORIGEN" "${REMOTE}:${DESTINO_REMOTO}/"
else
    scp -P "${SERVER_PORT}" -r "$ORIGEN" "${REMOTE}:${DESTINO_REMOTO}/"
fi

echo -e "${GREEN}[✓] Transferencia completada al servidor.${NC}"

# 3. Descarga de la carátula oficial en el servidor
echo -e "${BLUE}[*] Buscando y configurando carátula oficial en alta definición...${NC}"
ssh "${SSH_OPTS[@]}" "${REMOTE}" "python3 ~/media/fetch_cover.py \"\$HOME/${DESTINO_REMOTO}/${NOMBRE_BASE}\"" || {
    echo -e "${YELLOW}[!] No se pudo obtener la carátula automáticamente, pero el vídeo ya está disponible.${NC}"
}

echo ""
echo -e "${GREEN}=================================================================${NC}"
echo -e "${GREEN} 🎉 ¡LISTO PARA VER EN TU TELEVISIÓN SAMSUNG!${NC}"
echo -e "${GREEN}=================================================================${NC}"
echo -e " 1. Enciende tu tele Samsung."
echo -e " 2. Pulsa en ${YELLOW}'Fuentes'${NC} o ${YELLOW}'Dispositivos Conectados'${NC} en el mando."
echo -e " 3. Selecciona ${YELLOW}'Android Server Media Server'${NC}."
echo -e " 4. Entra en ${YELLOW}${DESTINO_REMOTO}${NC} y dale al Play con su carátula."
echo ""
