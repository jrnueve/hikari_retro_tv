# 02 — Configuración del sistema operativo y hardware

## Imagen base

- **Raspberry Pi OS Lite** (32 bits recomendado para Pi Zero W — el SoC es
  ARMv6, no soporta el kernel/userland de 64 bits). Sin entorno de
  escritorio: esto es intencional, todo el renderizado va directo a
  framebuffer, no hay X11/Wayland corriendo.
- Flashear con Raspberry Pi Imager o `rpi-imager`, habilitando en las
  opciones avanzadas (Ctrl+Shift+X en el Imager):
  - Hostname (ej. `hikari-tv.local`)
  - SSH habilitado (usuario/contraseña o clave pública)
  - WiFi (SSID/password) si no se va a usar Ethernet

Si se flashea manualmente sin el Imager, habilitar SSH creando un archivo
vacío llamado `ssh` (sin extensión) en la partición `boot` de la SD.

## Primer arranque

```bash
ssh pi@hikari-tv.local
sudo raspi-config   # opcional: expandir filesystem, timezone, etc.
sudo apt update && sudo apt full-upgrade -y
```

## Edición de `config.txt`

Ubicación según versión de Raspberry Pi OS:

- **Bookworm (2023+)**: `/boot/firmware/config.txt`
- **Bullseye o anterior**: `/boot/config.txt`

Agregar (o descomentar/modificar) las siguientes líneas:

```ini
# --- Hikari TV: salida de video compuesto (TV Out) ---
enable_tvout=1
sdtv_mode=0
# sdtv_mode: 0 = NTSC, 2 = PAL. Ajustar segun el estandar de la TV/modulador.
sdtv_aspect=1
# sdtv_aspect: 1 = 4:3 (estandar para un TV antiguo)

# --- Hikari TV: memoria de GPU para decodificacion ---
gpu_mem=128
# 128MB es un piso razonable para decodificar H.264 via hardware en la Zero W.
# Si el player usa MMAL/OMX para decodificacion por hardware, no bajar de 128.

# --- Hikari TV: audio PWM remapeado a GPIO 18/19 ---
dtoverlay=audremap,pins_18_19
# Sin este overlay, el PWM de audio sale por los pines de audio "de fabrica"
# (GPIO 40/41 en el SoC, no expuestos en el header de la Zero W). Con el
# overlay, sale por GPIO 18 (canal izquierdo) y GPIO 19 (canal derecho),
# que si estan expuestos en el header de 40 pines de la Zero W.
```

Notas:

- `enable_tvout=1` puede no ser necesaria en todas las versiones del
  firmware (en algunas basta con `sdtv_mode`), pero se deja explícita para
  forzar la detección. Verificar en el primer boot con un TV/monitor
  compuesto conectado.
- Si al bootear no aparece imagen en compuesto, revisar también que no haya
  un `hdmi_force_hotplug=1` conflictivo o un `dtoverlay=vc4-kms-v3d` activo
  (el driver KMS de escritorio interfiere con el TV out clásico en Lite).
- `sdtv_mode` y `sdtv_aspect` deben coincidir con el estándar de video que
  espera el modulador de RF (revisar su datasheet/manual).

## Verificación post-reboot

```bash
sudo reboot
# tras reconectar por SSH:
ls -l /dev/fb0                     # debe existir el framebuffer
fbset -i                           # info de la resolucion/modo activo
aplay -l                           # deberia listar el dispositivo PWM (bcm2835 headphones)
speaker-test -D plughw:0,0 -c1 -t sine -f 440   # tono de prueba por GPIO 18 (Ctrl+C para cortar)
```

Si `aplay -l` no muestra el dispositivo PWM, confirmar que el overlay
`audremap` haya quedado aplicado (`dmesg | grep -i pwm` o revisar
`/boot/firmware/config.txt` por typos) y que no haya otro overlay de audio
(p. ej. `dtoverlay=hifiberry-*` o similar) compitiendo.

## Siguiente paso

Con video y audio confirmados a nivel de sistema, continuar con la
[Fase 3 — prueba de streaming](03_streaming_prueba.md).
