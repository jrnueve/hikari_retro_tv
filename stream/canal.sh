#!/bin/bash
# canal.sh - reproduce un canal IPTV en el TV blanco y negro por video compuesto.
#
# Decodifica H.264 por hardware (h264_v4l2m2m), toma solo la luma (el TV es
# monocromo) y la escribe en el framebuffer con fbgray, que ademas la estira
# de rango de video (16-235) a pleno (0-255). Audio mono por la salida ALSA PWM.
#
# Dos etapas con un buffer en el medio: el servidor de prueba entrega cada
# segmento HLS de 5 s en ~2.5 s, y el lector HLS de ffmpeg los baja recien
# cuando los necesita, en el mismo hilo que alimenta la reproduccion; sin
# buffer, cualquier demora congela la imagen. La etapa 1 solo descarga (sin
# decodificar) hacia mbuffer y la etapa 2 reproduce desde ahi a ritmo real.
# Costo: la imagen aparece cuando el buffer junta ~8 s de stream.
#
# Uso:   ./canal.sh [URL]          (Ctrl+C para salir)
# Detiene tvtestd mientras corre (ambos escriben en el framebuffer) y lo
# vuelve a arrancar al salir.

set -u
URL="${1:-http://stream.mcquack.net/242/index.m3u8}"
DIR="$(cd "$(dirname "$0")" && pwd)"
ALSA="${HIKARI_ALSA_DEVICE:-plughw:0,0}"
# Solo luma, llevada a 720x576 (si el canal ya viene en 720x576 el scale no
# hace nada; para 720x480 o 1280x720 cuesta CPU extra)
LUMA="extractplanes=y,scale=720:576:flags=fast_bilinear"
BUFFER="${HIKARI_BUFFER:-3M}"     # ~13 s a 1.8 Mbps; la reproduccion arranca al 60 %

[ "$DIR/fbgray" -nt "$DIR/fbgray.c" ] || gcc -O2 -o "$DIR/fbgray" "$DIR/fbgray.c" || exit 1

restaurar() {
    sudo systemctl start tvtestd 2>/dev/null
}
trap restaurar EXIT

sudo systemctl stop tvtestd 2>/dev/null
sudo chvt 8

ffmpeg -hide_banner -loglevel error -http_multiple 1 -i "$URL" \
    -map 0 -c copy -f mpegts - \
    | mbuffer -q -m "$BUFFER" -P 60 \
    | ffmpeg -hide_banner -loglevel warning -stats -re \
    -c:v h264_v4l2m2m -f mpegts -i - \
    -map 0:v:0 -vf "$LUMA" -f rawvideo - \
    -map 0:a:0 -ac 1 -ar 48000 -f alsa "$ALSA" \
    | "$DIR/fbgray"
