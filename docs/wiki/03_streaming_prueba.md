# 03 — Prueba rápida de streaming (software)

## Elección de reproductor

Para una Pi Zero W (ARMv6 single-core, 512MB RAM, sin GPU moderna V3D/KMS
activa — ver nota en [02](02_configuracion_sistema.md) sobre evitar
`vc4-kms-v3d`), la decodificación de video **debe** apoyarse en el bloque
de hardware VideoCore IV vía **MMAL**. Decodificar H.264 por software en
este SoC no es viable para un stream fluido.

Recomendación: **`cvlc`** (VLC en modo línea de comandos, sin GUI/Qt) con
los módulos `mmal_vout` (salida de video por dispmanx/framebuffer) y
`mmal_codec` (decodificación H.264 por hardware). Es la opción con mejor
soporte vigente para el stack legacy de la Pi Zero W:

- `omxplayer` fue la opción histórica para esto, pero está **deprecado** y
  ya no se distribuye en los repos de Raspberry Pi OS a partir de Bookworm
  — no usarlo como base para un proyecto nuevo.
- `mpv` es una alternativa válida, pero requiere compilar o configurar
  explícitamente el decoder `h264_mmal` de ffmpeg y una salida de video
  compatible con el framebuffer legacy (`--vo=drm` no aplica sin KMS,
  `--vo=fbdev` no tiene aceleración). Requiere más ajuste fino que VLC/MMAL.

### Instalación mínima

```bash
sudo apt update
sudo apt install --no-install-recommends -y vlc-bin vlc-plugin-base vlc-plugin-video-output
```

`--no-install-recommends` evita arrastrar dependencias de escritorio
(Qt, íconos, etc.) que no aportan nada en un sistema headless.

Verificar que el módulo MMAL esté disponible tras instalar:

```bash
cvlc --list | grep -i mmal
```

Si no aparece, revisar la versión exacta del paquete `vlc-plugin-video-output`
disponible en el repo de la release de Raspberry Pi OS en uso — el nombre
del paquete que contiene el plugin MMAL puede variar entre versiones de
Debian/Raspberry Pi OS.

## Script de prueba

[`scripts/test_stream.sh`](../../scripts/test_stream.sh) reproduce un
stream HLS público de prueba, forzando:

- Video por el módulo `mmal_vout` (framebuffer, sin X11).
- Decodificación por hardware vía `mmal_codec` (fallback a `avcodec` si
  MMAL no puede manejar el stream).
- Audio por el dispositivo ALSA PWM configurado en la Fase 2
  (`aplay -l` para confirmar el índice de tarjeta/dispositivo correcto).

### Uso

```bash
chmod +x scripts/test_stream.sh
./scripts/test_stream.sh
# o con una URL propia:
./scripts/test_stream.sh "https://mi-servidor/mi_lista.m3u8"
# o forzando otro dispositivo ALSA si el indice de tarjeta no es el default:
HIKARI_ALSA_DEVICE=plughw:1,0 ./scripts/test_stream.sh
```

### Qué observar durante la prueba

- Que la imagen aparezca en el TV conectado al modulador de RF (sin
  necesidad de HDMI/monitor conectado).
- Que el audio se escuche por la salida del filtro RC.
- Uso de CPU (`top` en otra sesión SSH, o `vcgencmd measure_clock arm`):
  si un solo core está saturado al 100% de forma sostenida, el stream
  probablemente está cayendo a decodificación por software — bajar la
  resolución/bitrate del stream de origen o revisar que MMAL esté
  realmente activo (`cvlc` con `-vvv` para log verboso y confirmar el
  decoder usado).
