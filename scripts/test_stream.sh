#!/usr/bin/env bash
#
# Hikari Retro TV - prueba rapida de streaming HLS
#
# Renderiza el stream directo sobre el framebuffer (dispmanx/MMAL, sin X11)
# y fuerza la salida de audio al dispositivo ALSA PWM (GPIO 18) configurado
# en config.txt (ver docs/wiki/02_configuracion_sistema.md).
#
# Requiere cvlc (paquete vlc-bin + vlc-plugin-base + vlc-plugin-video-output).
# Ver docs/wiki/03_streaming_prueba.md para detalle e instalacion.

set -euo pipefail

INPUT_URL="${1:-https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8}"
ALSA_DEVICE="${HIKARI_ALSA_DEVICE:-plughw:0,0}"

if ! command -v cvlc >/dev/null 2>&1; then
    echo "Error: cvlc no esta instalado. Ver docs/wiki/03_streaming_prueba.md." >&2
    exit 1
fi

STREAM_URL="${INPUT_URL}"

# VLC no resuelve YouTube de forma confiable: si la URL es de YouTube,
# resolver primero el stream directo (HLS o mp4) con yt-dlp.
if [[ "${INPUT_URL}" == *youtube.com/* || "${INPUT_URL}" == *youtu.be/* ]]; then
    if ! command -v yt-dlp >/dev/null 2>&1; then
        echo "Error: URL de YouTube pero yt-dlp no esta instalado. Ver docs/wiki/03_streaming_prueba.md." >&2
        exit 1
    fi
    echo "URL de YouTube detectada, resolviendo stream directo con yt-dlp..."
    STREAM_URL="$(yt-dlp -f 'best[ext=mp4]/best' -g "${INPUT_URL}")"
fi

echo "Hikari Retro TV - test_stream.sh"
echo "Stream: ${STREAM_URL}"
echo "Salida de audio ALSA: ${ALSA_DEVICE} (verificar con 'aplay -l' si falla)"

exec cvlc \
    --play-and-exit \
    --fullscreen \
    --vout=mmal_vout \
    --codec=mmal_codec,avcodec \
    --aout=alsa \
    --alsa-audio-device="${ALSA_DEVICE}" \
    --no-audio-time-stretch \
    "${STREAM_URL}"
