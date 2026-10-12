# Backlog — Hikari Retro TV

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

## Generador de pruebas para TV B/N (Sony TV-900UET) — `tvtest/`

Ver [tvtest/README.txt](tvtest/README.txt).

- [x] Servicio `tvtestd` (systemd): 8 patrones en escala de grises a 720x576,
      tono senoidal 100-10000 Hz con volumen, por la salida ALSA PWM existente
- [x] Comando `tvtest` por socket UNIX (bash + nc, ~30 ms por comando en la Pi)
- [x] `config.txt`: `sdtv_disable_colourburst=1`; `cmdline.txt`: sin cursor,
      sin blanqueo ni mensajes del kernel (respaldos `.bak-tvtest`)
- [x] Instalado y verificado en la Pi: PAL 576i 50 Hz, 4:3, sin burst,
      driver legacy; arranca con crosshatch y audio apagado
- [ ] Prueba en el televisor real (inyeccion directa en video y audio)

## Fase 4 — Plataforma IPTV (`plataforma/`, clon del Hikari TV del U100)

Ver [docs/wiki/05_plataforma_iptv.md](docs/wiki/05_plataforma_iptv.md).

- [x] Demonio `hikaritvd`: supervisa el pipeline (cambio de canal = matar el
      grupo y lanzar otro), reintentos ante caida, sin imagen en 45 s = caido
- [x] Web app clonada del U100 (pagina /tv): anterior/siguiente, categorias,
      lista con filtro, favoritos, azar RND/PAIS/CATEG. Sin volumen ni color
- [x] Cartas en el framebuffer (logo, canal, estado) mientras junta buffer
- [x] fbgray adapta cualquier tamano a pantalla (vecino mas cercano, bandas
      16:9); ffmpeg no escala nada (swscale satura la Pi)
- [x] Relevamiento: 3.551 canales aptos (<= 720x576 pixeles, >= 360 lineas)
      de 7.379 del catalogo del U100; categorias por tema + espanol + argentina
- [x] Servicio systemd, arranca solo y vuelve al ultimo canal (reinicio
      verificado 2026-10-12)
- [ ] Probar la web app desde el celular y la imagen de las cartas en el TV
- [ ] Framebuffer a 16 bpp (`framebuffer_depth=16`): la mitad de escritura
      para fbgray; 854x480 hoy llega a 95 % de CPU
- [ ] Arranque: hoy 2 min (NetworkManager 50 s, cloud-init 18 s); evaluar
      quitar cloud-init y arrancar hikaritvd antes de la red (carta temprana)
- [ ] Canales sin pista de audio (hoy fallan como caidos)
- [ ] Maestras con audio en lista aparte (476 canales hoy sacrificados)
- [ ] `general` tiene 1.424 canales: evaluar partirla (por pais o idioma)
- [x] Repo propio: https://github.com/jrnueve/hikari_retro_tv (2026-10-12)

## Backlog futuro

- [ ] Controles fisicos (botones o joystick) como cliente de la API HTTP
- [ ] Ajuste fino de sintonía del modulador RF (canal 3/4 VHF típico)
- [ ] Carcasa retro / integración física con el modulador
