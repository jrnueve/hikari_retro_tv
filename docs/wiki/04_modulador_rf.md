# 04 — Modulador de RF (hardware específico en uso)

Este documento reemplaza la sección genérica "Conexión al modulador de RF"
de [01_hardware_esquemas.md](01_hardware_esquemas.md) con el modulador
concreto que usa este proyecto: convierte video compuesto + audio mono +
alimentación 5V en una señal de RF para la entrada de antena de un
televisor de tubo (CRT).

## 1. El modulador y su conector

El modulador trae un cable con conector **Mini-DIN de 4 pines** (misma
forma física que un conector S-Video), pero **no implementa el estándar
S-Video** — es un pinout propietario que reutiliza esas 4 vías para Video
Compuesto, Audio, VCC y GND. No conectar este cable a un puerto S-Video
real de otro equipo asumiendo compatibilidad: los niveles y la asignación
de pines no son S-Video.

Pinout identificado (colores del cable / letra serigrafiada en la placa del
modulador):

| Pin S-Video | Color de cable | Letra en placa | Función                          |
|-------------|-----------------|-----------------|-----------------------------------|
| 1           | Blanco          | B               | VCC — alimentación (asumida 5V DC, **verificar antes de conectar**, ver Precauciones) |
| 2           | Amarillo        | A               | Entrada de audio analógico mono   |
| 4           | Rojo            | V               | Entrada de video compuesto        |
| Chasis/malla| Marrón          | G               | GND / masa común                  |

## 2. Esquema de cableado — Pi Zero W → modulador

La Zero W no tiene conector de video ni audio nativo, así que cada cable
del modulador se conecta a un punto distinto de la placa:

| Cable modulador | Función | Punto en la Pi Zero W | Notas |
|---|---|---|---|
| **Marrón (G)** | GND | Test pad **GND** (el mismo par que "TV", cerca del mini-HDMI) o cualquier pin GND del header de 40 pines (ej. pin físico 6, 9, 14...) | Conectar **primero**, antes que VCC y señal — ver Precauciones. Todos los GND de la placa son el mismo nodo eléctrico, así que cualquiera sirve; usar el más cómodo de soldar. |
| **Rojo (V)** | Video compuesto | Test pad **TV** (ver [01_hardware_esquemas.md §1](01_hardware_esquemas.md#1-salida-de-video--pin-tv-compuesto)) | Señal directa, sin circuito adicional. |
| **Amarillo (A)** | Audio mono | Salida del **filtro RC** (después de C2), no directo a GPIO 18 | Ver §3 — nunca conectar el amarillo directo al GPIO. |
| **Blanco (B)** | VCC (5V asumidos) | Pin físico **2 o 4** del header de 40 pines (rail de 5V) | **No conectar sin verificar el voltaje real que espera el modulador primero** — ver Precauciones. |

```
                                Raspberry Pi Zero W
                       ┌───────────────────────────────────┐
                       │                                    │
   Pad "TV"  o─────────┼──── Video compuesto                │
                       │                                    │
   Pad "GND" o─────────┼──── GND                             │
                       │                                    │
   GPIO 18    o────┐    │                                    │
   (header)        │    │                                    │
                    R1 270R                                  │
                    │    │                                    │
              C1 33nF   │                                    │
              a GND      │                                    │
                    │    │                                    │
                   C2 10uF (serie, desacople DC)               │
                    │    │                                    │
                    └────┼──── Audio filtrado                 │
                       │                                    │
   Header pin 2/4 o─────┼──── 5V (verificar antes, ver abajo) │
   (5V rail)            │                                    │
                       └───────────────────────────────────┘
                                       │
                       Blanco(VCC) Amarillo(A) Rojo(V) Marrón(G)
                       ┌────┴───────────┴─────────┴────────┴────┐
                       │     Modulador de RF (conector          │
                       │     mini-DIN 4 pines, propietario)      │
                       └──────────────────┬───────────────────────┘
                                          │ RF (coaxial)
                                          ▼
                                  Entrada de antena del TV CRT
```

## 3. Solución de audio — no conectar el amarillo directo al GPIO

La Pi Zero W no tiene salida de audio analógica: el audio sale como PWM
(onda cuadrada de alta frecuencia) por GPIO 18. **El cable amarillo del
modulador debe conectarse a la salida del filtro RC descrito en
[01_hardware_esquemas.md §2](01_hardware_esquemas.md#2-salida-de-audio--pwm-por-gpio-18--filtro-rc-pasivo)
(R1 270Ω + C1 33nF a GND + C2 10µF serie), nunca directo al pin.**

¿Se puede saltear el filtro "solo para una prueba rápida"? **No, ni para
pruebas**, por dos motivos:

1. **C2 (desacople DC) es obligatorio, no opcional**: la salida PWM cruda
   tiene un offset de continua (~1.65V promedio). Conectada directo a la
   entrada de audio del modulador, esa continua puede saturar/desviar el
   punto de trabajo de la etapa de audio del modulador — en el mejor caso
   suena mal, en el peor puede estresar esa etapa de entrada.
2. **R1+C1 (filtro pasa-bajos) evita interferencia en el video**: la
   portadora PWM cruda tiene armónicos de alta frecuencia. Al estar el
   audio y el video entrando al mismo modulador (que después mezcla todo
   en una sola portadora de RF), esos armónicos sin filtrar pueden acoplarse
   a la etapa de video y aparecer como ruido/interferencia visible en la
   imagen del TV (patrón tipo "espina de pescado"). El filtro RC completo
   es la forma más simple de evitarlo con el hardware que ya está definido
   para este proyecto.

No hace falta ningún componente adicional más allá del filtro ya
documentado — no se requiere un DAC ni una etapa de amplificación extra
para esta prueba.

## 4. Configuración de software — config.txt validado

Estas son las líneas que ya se probaron en hardware real (Raspberry Pi OS
Lite, Raspbian 13 "trixie", Zero W) y se confirmaron con osciloscopio:
señal compuesta PAL correcta (`vcgencmd get_lcd_info` → `720 576 24`) y
`/dev/fb0` activo sin el driver KMS cargado.

```ini
# Audio PWM por GPIO 18/19
dtparam=audio=on
dtoverlay=audremap,pins_18_19
audio_pwm_mode=2

# Video compuesto (TV Out) - PAL (Argentina). Usar sdtv_mode=0 para NTSC.
enable_tvout=1
sdtv_mode=2
sdtv_aspect=1

# Memoria de GPU para decodificacion de video
gpu_mem=128

# IMPORTANTE: dtoverlay=vc4-kms-v3d debe estar comentado/ausente.
# El driver KMS reemplaza el stack legacy (dispmanx/MMAL) que necesitamos
# para el TV Out compuesto y para la decodificacion por hardware de cvlc.
# Si algun paquete o actualizacion lo vuelve a agregar a config.txt,
# comentarlo de nuevo o el video compuesto deja de funcionar.
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

Ubicación: `/boot/firmware/config.txt` en la Pi ya booteada (equivalente al
`config.txt` en la raíz de la partición boot de la SD, editable desde una
PC antes del primer arranque).

`sdtv_mode`: `0` = NTSC, `2` = PAL. Este proyecto usa PAL (Argentina). Si
en algún momento se prueba con otro modulador/TV que espera NTSC, es la
única línea que hace falta cambiar.

## 5. Precauciones eléctricas antes de energizar el conjunto

- **Verificar el voltaje real de VCC antes de conectar el blanco (B) al
  riel de 5V de la Pi.** El pinout identificado *asume* 5V DC, pero no está
  confirmado contra un datasheet del modulador. Si el modulador en
  realidad espera otro voltaje (por ejemplo 9V o 12V, común en algunos
  moduladores de RF), conectarlo a 5V puede simplemente no encenderlo, o
  en el peor caso dañarlo si internamente asume una tensión mínima para
  algún regulador. Medir con multímetro (continuidad y, si es posible,
  probar el modulador con su fuente original y medir el consumo) antes de
  unir el blanco al header de la Pi.
- **Conectar GND primero**, antes que VCC y las señales de video/audio.
  Esto evita que una diferencia de potencial transitoria entre las dos
  placas (Pi y modulador) circule corriente por las líneas de señal en vez
  de por la masa. Al desconectar, orden inverso: señales/VCC primero, GND
  al final.
- **Verificar el consumo de corriente del modulador** antes de alimentarlo
  desde el pin 5V de la Pi. La Zero W comparte ese riel con su propio
  consumo y con el fusible/límite de corriente de la fuente USB que
  alimenta a la Pi. Si el modulador consume más de unas pocas decenas de
  mA, o si la fuente de alimentación de la Pi no tiene margen de sobra
  (usar idealmente una fuente de 2A+), preferir alimentar el modulador con
  una fuente de 5V separada y unir únicamente los GND de ambas fuentes.
  Un consumo excesivo puede producir caídas de tensión (brownout) que
  reinicien la Pi o corrompan la SD a mitad de escritura.
- **No hacer conexiones/soldaduras con todo energizado.** Apagar la Pi
  (`sudo poweroff` y esperar el apagado completo, o directamente desconectar
  la alimentación) antes de modificar cualquier cable del conjunto.
- **Doble-chequear colores contra continuidad real** antes de conectar:
  los colores de cable ya fueron identificados y mapeados a las letras de
  la placa del modulador, pero conviene volver a verificar con multímetro
  en modo continuidad (equipo apagado) pin a pin antes de la conexión
  final, para descartar un error de identificación.
- **Cuidado con descargas electrostáticas (ESD)** al manipular la placa
  desnuda de la Pi Zero W (sin gabinete) — tocar una superficie metálica
  puesta a tierra antes de manipular la placa, especialmente en ambientes
  secos.

## Referencias pendientes

- [ ] Confirmar el voltaje y consumo real de VCC del modulador con
      multímetro antes de la primera conexión al riel de 5V de la Pi.
- [ ] Documentar el modelo/marca específico del modulador si se llega a
      identificar (actualmente sin datasheet, pinout inferido/medido a mano).
- [ ] Foto del conjunto cableado en `hardware/` una vez armado.
- [ ] Confirmar sintonía de canal RF de salida (canal VHF 3 o 4) una vez
      conectado al TV.
