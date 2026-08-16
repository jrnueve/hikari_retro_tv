# 01 — Esquemas de hardware

Este documento describe las dos salidas analógicas que usa Hikari TV: video
compuesto (TV Out) y audio PWM filtrado, ambas hacia las entradas de un
modulador de RF que a su vez se conecta al conector de antena del televisor
antiguo.

## 1. Salida de video — pin TV (compuesto)

La Raspberry Pi Zero W expone video compuesto directamente sobre el pin de
video del header GPIO (no hay conector RCA soldado de fábrica en el Zero).

- **Pin físico**: pin 4 del header de 40 pines sin soldar de la Zero W
  corresponde a la señal de TV compuesta (etiquetado a veces como "TV" en
  los pinouts, ubicado junto al conector de audio/video de las Pi de placa
  completa). En modelos con jack de 3.5mm de 4 polos (A/V), el video
  compuesto va en el anillo correspondiente del jack; en la Zero W, al no
  tener ese jack, se debe soldar un cable directamente al pin GPIO de TV out.
- **Verificar el pinout exacto** contra el modelo/revisión física de la
  placa antes de soldar (los pines de TV out no son GPIO de propósito
  general, son una señal analógica dedicada del SoC).
- El nivel de señal es analógico compuesto estándar (~1 Vpp), compatible
  directamente con la entrada de video del modulador de RF.
- Software: la señal se activa por configuración en `config.txt`
  (ver [02 fase 2](#) / `next_steps.md` Fase 2) y no requiere circuito
  adicional — se conecta el cable de video directo del pin al conector de
  entrada de video del modulador (blindado/coaxial recomendado para
  minimizar ruido).

## 2. Salida de audio — PWM por GPIO 18 + filtro RC pasivo

La Pi Zero W no tiene salida de audio analógica dedicada (a diferencia de
los modelos con jack 3.5mm). El audio se genera como una señal PWM (Pulse
Width Modulation) de alta frecuencia sobre GPIO 18, que debe filtrarse para
recuperar la señal de audio analógica antes de entregarla al modulador de RF.

### Circuito

```
                    R1 (~270 Ω)              C2 (~10 µF, electrolitico)
GPIO 18 (PWM) o-----/\/\/\-----+------------||------------o  AUDIO OUT
                                |                              (a entrada de
                                |                               audio del
                               ===  C1 (~33 nF)                 modulador RF)
                                |
                               GND -------------------------o  GND
                                                                (comun con
                                                                 modulador RF)
```

### Explicación de cada componente

- **R1 — Resistencia serie (~270 Ω)**: limita la corriente desde el pin GPIO
  y, junto con C1, forma un **filtro pasa-bajos RC** que promedia la señal
  PWM de alta frecuencia (tipicamente decenas de kHz) y la convierte en una
  tensión analógica variable equivalente al audio original. Frecuencia de
  corte aproximada: `fc = 1 / (2 * pi * R1 * C1)`.
- **C1 — Capacitor a GND (~33 nF, cerámico)**: cierra el filtro pasa-bajos
  contra masa. Junto con R1 (270 Ω / 33 nF) da una `fc` en el orden de los
  ~18 kHz, suficiente para dejar pasar el rango de audio audible y atenuar
  la portadora PWM.
- **C2 — Capacitor serie de desacople DC (~10 µF, electrolítico)**: la señal
  filtrada en el nodo entre R1 y C1 tiene un offset de continua (~1.65V,
  la mitad del riel de 3.3V del GPIO). C2 bloquea esa componente DC y deja
  pasar solo la señal de audio (AC), evitando inyectar continua a la
  entrada de audio del modulador de RF. Respetar la polaridad del
  electrolítico (el lado positivo va hacia el GPIO/nodo del filtro si la
  tensión de referencia del otro extremo es más baja; en caso de duda,
  usar un capacitor no polarizado o verificar con multímetro el sentido de
  la diferencia de potencial antes de soldar).
- **GND**: debe compartirse entre la Raspberry Pi y el modulador de RF para
  que el filtro tenga una referencia común. Sin GND común, el filtro no
  funciona y puede haber ruido o zumbido en el audio.

### Notas de implementación

- Esto es audio **mono**: PWM por GPIO 18 entrega un solo canal. Si el
  modulador de RF espera estéreo, alimentar ambos canales (izquierdo y
  derecho) con la misma señal filtrada, o usar un divisor pasivo simple.
- El filtro es pasivo y de bajo costo (una resistencia + dos capacitores),
  consistente con la restricción de no usar un DAC I2S externo.
- Calidad esperada: suficiente para voz/TV, no hi-fi. Es una limitación
  conocida y aceptada del enfoque PWM+RC frente a un DAC dedicado.
- Alternativa de mejora futura (no usada en este proyecto): un filtro RC de
  2 etapas o un filtro activo mejoraría la relación señal/ruido, a costa de
  más componentes.

## 3. Conexión al modulador de RF

- **Video**: cable desde el pin de TV out de la Pi hasta la entrada de video
  compuesto (RCA amarillo o equivalente) del modulador.
- **Audio**: salida del filtro RC (después de C2) hasta la entrada de audio
  (RCA blanco/rojo o línea) del modulador.
- **GND**: común entre Pi y modulador (ya sea por el propio cableado de
  video/audio si son cables blindados con malla a GND, o con un cable
  adicional de masa).
- **Salida del modulador**: cable coaxial RF hacia la entrada de antena del
  televisor antiguo, sintonizado en un canal VHF libre (típicamente canal 3
  o 4, según región/modulador).

## Referencias pendientes

- [ ] Confirmar pinout exacto de TV out para la revisión física de la Zero W
      en uso (foto + multímetro antes de soldar).
- [ ] Agregar foto/diagrama del circuito armado en protoboard o placa
      perforada a `hardware/`.
- [ ] Documentar modelo específico del modulador de RF usado y sus niveles
      de entrada esperados (impedancia, Vpp de video, nivel de línea de audio).
