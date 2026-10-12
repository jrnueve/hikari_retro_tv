# Hikari Retro TV

Televisor IPTV para televisores retro de tubo: una Raspberry Pi Zero W que
entrega señal analógica (video compuesto + audio) al TV, directo o por un
modulador de RF a su entrada de antena. Los canales y categorías se eligen
desde una web app en el celular; el volumen es la perilla del propio TV.

La primera versión apunta a televisores **blanco y negro** (solo luma, sin
subportadora de color); podría haber versiones futuras en color. Es la
hermana de Hikari TV sobre la netbook MSI Wind U100, de la que hereda el
catálogo de canales y la web app.

## Filosofía del proyecto

- **Headless puro**: Raspberry Pi OS Lite, sin entorno de escritorio (X11/Wayland).
  Todo el renderizado de video ocurre directo sobre el framebuffer (`/dev/fb0`).
- **Sin hardware adicional de audio**: no se usa DAC I2S. El audio sale como
  PWM mono por GPIO 18, filtrado con un pasa-bajos RC pasivo (ver
  [docs/wiki/01_hardware_esquemas.md](docs/wiki/01_hardware_esquemas.md)).
- **Salida analógica retro**: video por el pin compuesto (TV Out) hacia un
  modulador de RF, para entrar por el conector de antena del televisor.
- **Recursos limitados**: Pi Zero W = CPU single-core ARMv6 + 512MB RAM.
  Cualquier decisión de software prioriza bajo consumo de CPU sobre
  features (nada de escritorio, nada de decodificación por software pesada
  si se puede evitar).

## Arquitectura (resumen)

```
IPTV (HLS) --> ffmpeg (h264_v4l2m2m, solo luma) --> fbgray --> framebuffer (/dev/fb0) --> TV Out (compuesto) --> TV blanco y negro
                            \--> ALSA PWM (GPIO 19) --> filtro RC --> entrada de audio

celular --> web app :8080 --> hikaritvd (supervisa el pipeline, catalogo, favoritos)
```

## Estructura del repositorio

- `scripts/` — scripts bash de instalación, configuración y pruebas.
- `config/` — snippets de configuración de sistema (config.txt, asound.conf, etc.).
- `docs/wiki/` — documentación técnica ampliada (hardware, software, decisiones).
- `hardware/` — esquemas, diagramas y notas de electrónica (filtro RC, modulador RF).
- `plataforma/` — televisor IPTV: demonio `hikaritvd` + web app, pipeline, catalogo y despliegue
  (ver [docs/wiki/05_plataforma_iptv.md](docs/wiki/05_plataforma_iptv.md)).
- `tvtest/` — generador de señales de prueba para el TV blanco y negro.

## Estado del proyecto

Ver [next_steps.md](next_steps.md) para el backlog y la fase actual.

## Referencias de hardware

- Raspberry Pi Zero W (single-core ARMv6, 512MB RAM)
- Salida de video compuesto nativa (pin TV, ver [hardware/](hardware/))
- Modulador de RF (entrada de video compuesto + audio línea)
- Filtro RC pasivo para audio PWM (GPIO 18) — ver
  [docs/wiki/01_hardware_esquemas.md](docs/wiki/01_hardware_esquemas.md)

## Repositorio

https://github.com/jrnueve/hikari_retro_tv
