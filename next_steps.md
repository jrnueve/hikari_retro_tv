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
- [x] Verificar salida de audio con `speaker-test` — confirmado con
      osciloscopio en la salida del filtro (tono 440Hz limpio); nota:
      el audio mono sale por GPIO19/pin35, no GPIO18/pin12 (corregido
      en la doc)
- [x] Documentar en `docs/wiki/` desvíos respecto a lo planeado (pin de TV
      out real vs. lo asumido inicialmente, versión de OS más nueva de lo
      esperado — Raspbian 13 "trixie")
- [x] Documentar modulador de RF específico y su cableado —
      [docs/wiki/04_modulador_rf.md](docs/wiki/04_modulador_rf.md)
- [x] Verificar con multímetro el voltaje/consumo real de VCC del
      modulador — confirmado 5V, ~14mA (ver 04_modulador_rf.md §5)
- [x] Conectar video + GND + VCC del modulador y confirmar imagen por RF
      — confirmado con un conversor RF-a-VGA como receptor de prueba,
      imagen estable de la consola de Linux en canal ~52 (2026-08-17)
- [x] Conectar audio (amarillo, vía filtro RC en GPIO19) al modulador —
      confirmado a nivel de circuito y por RF (canales 59/83, con bandas
      correlacionadas al tono — evidencia de subportadora de audio FM
      real, el conversor de prueba no la demodula pero el modulador sí
      la genera)
- [ ] **BLOQUEADO — a la espera del TV CRT real**: confirmar imagen +
      audio simultáneos con sintonía estable. El conversor RF-a-VGA usado
      hasta ahora fue solo herramienta de validación (sin demodulación
      intercarrier de audio, sintonía poco confiable) — no sirve para la
      prueba definitiva. Circuito completo (video + audio + alimentación)
      ya validado y listo para probar en el TV real apenas esté disponible.

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
