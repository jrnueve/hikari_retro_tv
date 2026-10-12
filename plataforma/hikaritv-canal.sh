#!/bin/bash
# hikaritv-canal - reproduce UN canal en el TV blanco y negro. Lo lanza
# hikaritvd en su propio grupo de procesos y lo mata entero para cambiar de
# canal; no tiene trampas ni reintentos propios (eso es del demonio).
#
# Mismo pipeline que stream/canal.sh, validado en el TV real:
#   etapa 1: ffmpeg solo descarga (copia sin decodificar) hacia mbuffer, que
#            absorbe las demoras del servidor HLS;
#   etapa 2: ffmpeg a ritmo real, decodifica H.264 por hardware
#            (h264_v4l2m2m), toma solo la luma y la entrega a fbgray, que la
#            escribe en /dev/fb0. Audio mono por la salida ALSA PWM.
#
# ffmpeg no escala nada: entrega la luma en el tamano nativo del canal y
# fbgray la lleva a pantalla (bandas incluidas) por vecino mas cercano.
# Escalar con swscale satura la Pi. La etapa 2 corre con -loglevel info para
# que hikaritvd lea el tamano real y la proporcion (DAR) del video y se los
# pase a fbgray en ARCHIVO_VIDEO, antes del primer cuadro.
# User-Agent de navegador: hay CDN que dan 403 al de ffmpeg (Lavf).
# fps=25: un canal de 30 fps descarta cuadros antes de pasar por la tuberia.
#
# Uso: hikaritv-canal URL      (variables: ver hikari-tv.conf y hikaritvd)

set -u
URL="$1"
LIB="$(cd "$(dirname "$0")" && pwd)"
ALSA="${ALSA:-plughw:0,0}"
BUFFER="${BUFFER:-3M}"
BUFFER_PORC="${BUFFER_PORC:-60}"
ARCHIVO_VIDEO="${ARCHIVO_VIDEO:-/tmp/hikari-tv-video}"

LUMA="fps=25,extractplanes=y"

ffmpeg -nostdin -hide_banner -loglevel error -http_multiple 1 \
    -user_agent "Mozilla/5.0" -i "$URL" -map 0:v:0 -map '0:a:0?' -c copy -f mpegts - \
    | mbuffer -q -m "$BUFFER" -P "$BUFFER_PORC" \
    | ffmpeg -nostdin -hide_banner -nostats -loglevel info -re \
    -c:v h264_v4l2m2m -f mpegts -i - \
    -map 0:v:0 -vf "$LUMA" -f rawvideo - \
    -map '0:a:0?' -ac 1 -ar 48000 -f alsa "$ALSA" \
    | "$LIB/fbgray" -v "$ARCHIVO_VIDEO"
