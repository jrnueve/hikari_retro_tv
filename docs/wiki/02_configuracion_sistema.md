# 02 — Configuración del sistema operativo y hardware

## Imagen base

- **Raspberry Pi OS Lite, 32-bit** (obligatorio para Pi Zero W — el SoC es
  BCM2835/ARMv6 y **no puede bootear ningún kernel de 64 bits**, sin
  excepción). Sin entorno de escritorio: esto es intencional, todo el
  renderizado va directo a framebuffer, no hay X11/Wayland corriendo.
- Flashear con Raspberry Pi Imager o `rpi-imager`.
  - **Importante en "Choose Device"**: elegir específicamente
    **"Raspberry Pi Zero"**, NO "Raspberry Pi Zero 2 W". El Zero 2 W usa
    otro SoC (BCM2710, ARMv8) y su imagen de 64-bit no trae los archivos
    `bcm2708-rpi-zero-w.dtb` ni `kernel.img` (armhf) que la Zero W original
    necesita para arrancar. Verificar después de flashear que la partición
    boot de la SD tenga esos dos archivos antes de mover la SD a la Pi.
  - En "Choose OS": Raspberry Pi OS Lite (32-bit).
  - En las opciones avanzadas (⚙️ / Ctrl+Shift+X): hostname, SSH habilitado
    (password o clave pública), WiFi si no se usa Ethernet, timezone.
- El Imager moderno (Bookworm/trixie) provisiona el primer boot con
  archivos `user-data`/`network-config`/`meta-data` (estilo cloud-init) en
  la raíz de la partición boot, en vez del viejo esquema `userconf.txt` +
  `ssh` + `wpa_supplicant.conf`. Si algo del primer boot no toma (SSH,
  WiFi), revisar esos archivos antes que nada.

Si se flashea manualmente sin el Imager, habilitar SSH creando un archivo
vacío llamado `ssh` (sin extensión) en la partición `boot` de la SD.

## Primer arranque

```bash
ssh pi@hikaritv.local
sudo raspi-config   # opcional: expandir filesystem, timezone, etc.
sudo apt update && sudo apt full-upgrade -y
```

## Edición de `config.txt`

Ubicación según versión de Raspberry Pi OS:

- **Bookworm/trixie (2023+)**: `/boot/firmware/config.txt`
- **Bullseye o anterior**: `/boot/config.txt`

Agregar (o descomentar/modificar) las siguientes líneas — este es el
**set validado en hardware real** (Zero W, Raspbian 13 "trixie",
2026-08-16, confirmado con osciloscopio):

```ini
# --- Hikari TV: salida de video compuesto (TV Out) ---
enable_tvout=1
sdtv_mode=2
# sdtv_mode: 0 = NTSC, 2 = PAL. Este proyecto usa PAL (Argentina).
sdtv_aspect=1
# sdtv_aspect: 1 = 4:3 (estandar para un TV antiguo)

# --- Hikari TV: memoria de GPU para decodificacion ---
gpu_mem=128
# 128MB es un piso razonable para decodificar H.264 via hardware en la Zero W.
# Si el player usa MMAL/OMX para decodificacion por hardware, no bajar de 128.

# --- Hikari TV: audio PWM remapeado a GPIO 18/19 ---
dtoverlay=audremap,pins_18_19
audio_pwm_mode=2
# Sin el overlay, el PWM de audio sale por los pines de audio "de fabrica"
# (GPIO 40/41 en el SoC, no expuestos en el header de la Zero W). Con el
# overlay, se habilitan GPIO 18 y GPIO 19 (si estan expuestos en el header
# de 40 pines de la Zero W). IMPORTANTE (validado en hardware real): en
# modo audio MONO (speaker-test -c1), la señal sale por GPIO19/pin fisico
# 35, no por GPIO18/pin 12 pese a la convencion habitual de "izquierdo=18".
# audio_pwm_mode=2 usa el modo de mayor calidad del PWM de audio.

# --- Hikari TV: DRM VC4 V3D (KMS) deshabilitado a proposito ---
# Las imagenes recientes de Raspberry Pi OS traen dtoverlay=vc4-kms-v3d
# activado por default. Ese driver reemplaza el stack legacy (dispmanx/
# MMAL) que este proyecto necesita para el TV out compuesto y para la
# decodificacion por hardware de cvlc. Si esta linea esta presente y
# descomentada en el config.txt final, COMENTARLA (o el video compuesto
# no va a funcionar):
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

Notas:

- `enable_tvout=1` puede no ser necesaria en todas las versiones del
  firmware (en algunas basta con `sdtv_mode`), pero se deja explícita para
  forzar la detección.
- **Confirmado en hardware real**: con estas líneas, `/dev/fb0` queda
  presente y `vcgencmd get_lcd_info` devuelve `720 576 24` (resolución PAL
  correcta), sin el módulo `vc4` cargado (`lsmod | grep vc4` vacío).
- `sdtv_mode` y `sdtv_aspect` deben coincidir con el estándar de video que
  espera el modulador de RF — ver
  [04_modulador_rf.md](04_modulador_rf.md) para el modulador específico
  de este proyecto.

## Verificación post-reboot

```bash
sudo reboot
# tras reconectar por SSH:
ls -l /dev/fb0                     # debe existir el framebuffer
fbset -i                           # info de la resolucion/modo activo
aplay -l                           # deberia listar el dispositivo PWM (bcm2835 headphones)
speaker-test -D plughw:0,0 -c1 -t sine -f 440   # tono de prueba mono, sale por GPIO19/pin35 (Ctrl+C para cortar)
```

Si `aplay -l` no muestra el dispositivo PWM, confirmar que el overlay
`audremap` haya quedado aplicado (`dmesg | grep -i pwm` o revisar
`/boot/firmware/config.txt` por typos) y que no haya otro overlay de audio
(p. ej. `dtoverlay=hifiberry-*` o similar) compitiendo.

## Siguiente paso

Con video y audio confirmados a nivel de sistema, continuar con la
[Fase 3 — prueba de streaming](03_streaming_prueba.md).
