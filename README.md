# Hikari TV

Reproductor de IPTV minimalista para Raspberry Pi Zero W que inyecta señal
analógica (video compuesto + audio) a un modulador de RF, para sintonizar
canales IPTV en un televisor antiguo por su entrada de antena (RF).

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
IPTV stream (HLS/m3u8) --> mpv/vlc (CLI, sin GUI) --> framebuffer (/dev/fb0) --> TV Out (compuesto) --> Modulador RF --> TV antiguo (entrada antena)
                                              \--> ALSA PWM (GPIO 18) --> filtro RC --> entrada de audio del modulador RF
```

## Estructura del repositorio

- `scripts/` — scripts bash de instalación, configuración y pruebas.
- `config/` — snippets de configuración de sistema (config.txt, asound.conf, etc.).
- `docs/wiki/` — documentación técnica ampliada (hardware, software, decisiones).
- `hardware/` — esquemas, diagramas y notas de electrónica (filtro RC, modulador RF).

## Estado del proyecto

Ver [next_steps.md](next_steps.md) para el backlog y la fase actual.

## Referencias de hardware

- Raspberry Pi Zero W (single-core ARMv6, 512MB RAM)
- Salida de video compuesto nativa (pin TV, ver [hardware/](hardware/))
- Modulador de RF (entrada de video compuesto + audio línea)
- Filtro RC pasivo para audio PWM (GPIO 18) — ver
  [docs/wiki/01_hardware_esquemas.md](docs/wiki/01_hardware_esquemas.md)

## Repositorio

https://github.com/jrnueve/hikari_tv
