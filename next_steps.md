# Backlog — Hikari TV

Convención: `[ ]` pendiente, `[~]` en curso, `[x]` cerrado.

## Fase 1 — Estructura del repositorio y documentación

- [x] Inicializar repo Git (`git init`, remote `origin`)
- [x] Crear estructura `scripts/`, `config/`, `docs/wiki/`, `hardware/`
- [x] `README.md` con arquitectura y filosofía del proyecto
- [x] `docs/wiki/01_hardware_esquemas.md` — filtro RC de audio PWM + pin TV Out
- [ ] Primer commit + push a `main`

## Fase 2 — Configuración del sistema operativo y hardware

- [ ] Flashear Raspberry Pi OS Lite (32 o 64 bit) en la SD
- [ ] Habilitar SSH (archivo `ssh` vacío en partición boot, o `raspi-config`)
- [ ] Editar `/boot/firmware/config.txt` (Bookworm) o `/boot/config.txt` (Bullseye o anterior):
  - [ ] Forzar salida de video compuesto (`enable_tvout=1`, `sdtv_mode`)
  - [ ] Asignar `gpu_mem` para decodificación de video
  - [ ] `dtoverlay=audremap,pins_18_19` para audio PWM por GPIO 18
- [ ] Reboot y verificar `/dev/fb0` presente
- [ ] Verificar salida de audio con `speaker-test` o `aplay`
- [ ] Documentar en `docs/wiki/` cualquier desvío respecto a lo planeado

## Fase 3 — Prueba rápida de streaming (software)

- [ ] Instalar reproductor CLI (mpv o cvlc) vía apt
- [ ] Crear `scripts/test_stream.sh` con URL HLS pública de prueba
- [ ] Confirmar renderizado en framebuffer (sin X11)
- [ ] Confirmar audio forzado al dispositivo ALSA PWM
- [ ] Medir uso de CPU/RAM durante reproducción (`top`/`vcgencmd`)
- [ ] Si el uso de CPU es excesivo: evaluar bajar resolución/bitrate del stream
      o decodificación por hardware si el player lo soporta

## Backlog futuro (post-MVP)

- [ ] Selección de canal (lista de canales IPTV, changer simple por teclado/botón físico)
- [ ] Arranque automático en boot (systemd service)
- [ ] Recuperación automática ante caída de stream o de red WiFi
- [ ] Ajuste fino de sintonía del modulador RF (canal 3/4 VHF típico)
- [ ] Carcasa retro / integración física con el modulador
