# Backlog — Hikari TV

Convención: `[ ]` pendiente, `[~]` en curso, `[x]` cerrado.

## Fase 1 — Estructura del repositorio y documentación

- [x] Inicializar repo Git (`git init`, remote `origin`)
- [x] Crear estructura `scripts/`, `config/`, `docs/wiki/`, `hardware/`
- [x] `README.md` con arquitectura y filosofía del proyecto
- [x] `docs/wiki/01_hardware_esquemas.md` — filtro RC de audio PWM + pin TV Out
- [x] Primer commit local
- [ ] Push a `main` (remote `origin` configurado, todavía sin push)

## Fase 2 — Configuración del sistema operativo y hardware

- [x] Flashear Raspberry Pi OS Lite **32-bit** en la SD (con Raspberry Pi
      Imager — cuidado: elegir device "Raspberry Pi Zero", NO "Zero 2 W",
      que es de 64-bit y no bootea en la Zero W original)
- [x] Habilitar SSH (hecho vía opciones avanzadas del Imager + acceso por
      clave SSH configurado luego)
- [x] Editar `/boot/firmware/config.txt`:
  - [x] Forzar salida de video compuesto (`enable_tvout=1`, `sdtv_mode=2` PAL, `sdtv_aspect=1`)
  - [x] Asignar `gpu_mem=128` para decodificación de video
  - [x] `dtoverlay=audremap,pins_18_19` + `audio_pwm_mode=2` para audio PWM por GPIO 18
  - [x] Comentar `dtoverlay=vc4-kms-v3d` / `max_framebuffers=2` (el driver KMS por default de Raspberry Pi OS rompe el TV out legacy)
- [x] Reboot y verificar `/dev/fb0` presente (confirmado)
- [x] Verificar señal de video compuesto con osciloscopio (Hantek DSO2D15) —
      confirmado PAL 720x576 vía `vcgencmd get_lcd_info`, burst de color
      visible en la forma de onda (2026-08-16)
- [ ] Verificar salida de audio con `speaker-test` o `aplay` (pendiente,
      requiere el filtro RC armado y conectado)
- [x] Documentar en `docs/wiki/` desvíos respecto a lo planeado (pin de TV
      out real vs. lo asumido inicialmente, versión de OS más nueva de lo
      esperado — Raspbian 13 "trixie")
- [x] Documentar modulador de RF específico y su cableado —
      [docs/wiki/04_modulador_rf.md](docs/wiki/04_modulador_rf.md)
- [ ] Verificar con multímetro el voltaje/consumo real de VCC del
      modulador antes de conectarlo al riel de 5V de la Pi (ver
      Precauciones en 04_modulador_rf.md)
- [ ] Conectar físicamente el modulador (video, audio filtrado, GND, VCC)
      y confirmar imagen en el TV CRT

## Fase 3 — Prueba rápida de streaming (software)

- [x] Documentar reproductor CLI recomendado (`cvlc` + MMAL) y comandos apt
- [x] Crear `scripts/test_stream.sh` con URL HLS pública de prueba +
      soporte YouTube vía `yt-dlp`
- [ ] Instalar `cvlc`/`yt-dlp` en la Pi real (documentado, no ejecutado todavía)
- [ ] Confirmar renderizado en framebuffer (sin X11) en la Pi real
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
