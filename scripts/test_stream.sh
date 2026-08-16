#!/usr/bin/env bash
#
# Hikari TV - prueba rapida de streaming HLS
#
# Renderiza el stream directo sobre el framebuffer (dispmanx/MMAL, sin X11)
# y fuerza la salida de audio al dispositivo ALSA PWM (GPIO 18) configurado
# en config.txt (ver docs/wiki/02_configuracion_sistema.md).
#
# Requiere cvlc (paquete vlc-bin + vlc-plugin-base + vlc-plugin-video-output).
# Ver docs/wiki/03_streaming_prueba.md para detalle e instalacion.

set -euo pipefail

STREAM_URL="${1:-https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8}"
ALSA_DEVICE="${HIKARI_ALSA_DEVICE:-plughw:0,0}"

if ! command -v cvlc >/dev/null 2>&1; then
    echo "Error: cvlc no esta instalado. Ver docs/wiki/03_streaming_prueba.md." >&2
    exit 1
fi

echo "Hikari TV - test_stream.sh"
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
