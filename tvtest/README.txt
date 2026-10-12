TVTEST - GENERADOR DE SENALES DE PRUEBA PARA TV BLANCO Y NEGRO
================================================================

Generador de patrones de video y tono de audio sobre la Raspberry Pi Zero W
del proyecto, para ajustar y diagnosticar un televisor Sony TV-900UET de tubo,
blanco y negro (version europea, norma B/G).

La senal de video compuesto y el audio se inyectan directo en las etapas de
video y de audio del televisor, sin RF.


1. ADVERTENCIA DE SEGURIDAD
---------------------------

Muchos televisores de esa epoca tienen el chasis conectado directamente a la
red electrica ("chasis caliente"). Si es el caso, unir la masa de la Pi con la
masa del televisor pone la Pi (y la PC, si esta conectada por USB) a tension
de red. Los capacitores de acople NO protegen la masa.

Antes de unir las masas: medir la tension entre el chasis y tierra con el TV
encendido, o alimentar el televisor a traves de un transformador de
aislamiento.


2. CONEXION
-----------

Video:  pad TV de la Pi -> capacitor de 10 uF en serie (negativo hacia la
        Pi) -> punto de inyeccion de video del televisor.
Audio:  salida del conversor RC existente (GPIO19, pin fisico 35, filtro
        270 ohm / 47 nF) -> capacitor de acople -> entrada de audio del
        televisor.
Masa:   GND de la Pi (pad GND o cualquier GND del header) unido a la masa del
        televisor (ver seccion 1).

Nunca conectar sin los capacitores de acople.

La Pi entrega el nivel y la polaridad estandar de video compuesto
(sincronismo abajo, blanco arriba, ~1 Vpp sobre 75 ohm). Segun el punto de
inyeccion elegido, la etapa del televisor puede esperar otro nivel u otra
polaridad: si la imagen sale invertida o muy debil, revisar el punto de
inyeccion, no la Pi.


3. CONFIGURACION APLICADA
-------------------------

La Pi usa el driver de video legacy del firmware (sin vc4-kms-v3d, sin
/dev/dri). Video compuesto PAL, 625 lineas, 50 Hz entrelazado (576i, linea
de 15 625 Hz), 4:3, framebuffer 720x576.

/boot/firmware/config.txt (lineas relevantes):

    enable_tvout=1
    sdtv_mode=2                   PAL entrelazado
    sdtv_aspect=1                 4:3
    sdtv_disable_colourburst=1    sin subportadora de color (agregada por tvtest)
    dtoverlay=audremap,pins_18_19 audio PWM por GPIO18/19 (mono por GPIO19)
    audio_pwm_mode=2

/boot/firmware/cmdline.txt (agregado al final de la unica linea):

    consoleblank=0 vt.global_cursor_default=0 loglevel=3 quiet logo.nologo

Sin apagado de pantalla, sin cursor y sin mensajes del kernel sobre la imagen.
Ademas el servicio pasa a la consola virtual 8 en modo grafico, donde la
consola de texto no dibuja nada.

Respaldos (los crea install.sh la primera vez):

    /boot/firmware/config.txt.bak-tvtest
    /boot/firmware/cmdline.txt.bak-tvtest

Como revertir:

    sudo /home/pi/tvtest/uninstall.sh
    sudo reboot

o a mano:

    sudo cp /boot/firmware/config.txt.bak-tvtest  /boot/firmware/config.txt
    sudo cp /boot/firmware/cmdline.txt.bak-tvtest /boot/firmware/cmdline.txt
    sudo reboot

Si la Pi no arranca: poner la SD en la PC (la particion de arranque es FAT) y
copiar los .bak-tvtest sobre los originales.


4. INSTALACION
--------------

Desde la PC, en la carpeta del repo:

    scp -r tvtest pi@192.168.1.40:/home/pi/
    ssh pi@192.168.1.40 "sudo /home/pi/tvtest/install.sh && sudo reboot"

Archivos instalados:

    /opt/tvtest/tvtestd.py                  servicio
    /usr/local/bin/tvtest                   comando de control
    /etc/systemd/system/tvtestd.service     unidad systemd

Al encender, el servicio arranca mostrando la cuadricula (crosshatch) con el
audio apagado.

Arranque automatico:

    ssh pi@192.168.1.40 tvtest autostart on      (equivale a systemctl enable)
    ssh pi@192.168.1.40 tvtest autostart off     (equivale a systemctl disable)

Arrancar y detener a mano:

    ssh pi@192.168.1.40 tvtest start
    ssh pi@192.168.1.40 tvtest stop

Registro del servicio:

    ssh pi@192.168.1.40 journalctl -u tvtestd -n 50


5. COMANDOS DE TVTEST
---------------------

    tvtest pattern list          lista de patrones (* = actual)
    tvtest pattern <nombre>      cambia de patron (inmediato, sin cortar el sincronismo)
    tvtest tone <Hz>             enciende el tono, 100 a 10000 Hz
    tvtest tone on               enciende con la ultima frecuencia
    tvtest tone off              apaga el tono
    tvtest volume <0-100>        volumen del tono en %
    tvtest status                patron, tono, volumen y modo de video activo
    tvtest start|stop|restart    control del servicio
    tvtest autostart on|off      arranque automatico al encender

Ejemplos:

    ssh pi@192.168.1.40 tvtest pattern crosshatch
    ssh pi@192.168.1.40 tvtest tone 1000
    ssh pi@192.168.1.40 tvtest volume 50
    ssh pi@192.168.1.40 tvtest status

El tono es una senoidal generada por el servicio y enviada a la misma salida
ALSA PWM de siempre (bcm2835, mono por GPIO19, mismo filtro RC). El filtro
corta cerca de 12.5 kHz, asi que hacia 10 kHz el nivel de salida baja.
Por defecto: 1000 Hz, volumen 50 %, apagado al arrancar.


6. PATRONES Y QUE AJUSTA CADA UNO
---------------------------------

Todos a pantalla completa, 720x576, escala de grises (R=G=B). El cuadro de
720x576 cubre la pantalla 4:3 completa, por lo que cada pixel es ~6.7 % mas
ancho que alto; los patrones geometricos estan compensados.

white       Campo blanco 100 %.
            Brillo maximo, pureza y uniformidad, regulacion de alta tension
            (el tamano de la imagen no debe "respirar"), ajuste de G2/screen.

gray        Campo gris 50 %.
            Uniformidad, manchas del tubo, zumbido o barras de 50 Hz en la
            imagen (filtrado de la fuente).

black       Campo negro 0 %.
            Nivel de negro y brillo (que el raster apenas desaparezca),
            lineas de retorno visibles.

crosshatch  Cuadricula de 14 x 10 celdas, lineas blancas de 2 px sobre
            negro, con linea en cada borde exacto del cuadro.
            Altura y ancho, linealidad vertical y horizontal (las celdas
            deben ser iguales arriba y abajo, izquierda y derecha), centrado,
            distorsion de almohadilla, convergencia del foco en esquinas.
            Nota: en 4:3, 14 x 10 no da cuadrados exactos; cada celda es un
            5 % mas alta que ancha. Comparar celdas entre si, no con un
            cuadrado ideal.

circle      Circulo centrado que toca los bordes superior e inferior de la
            zona segura, cruz central, rectangulo en el borde exacto y otro
            en la zona segura (90 %).
            Centrado, relacion de aspecto (el circulo debe verse redondo),
            sobrebarrido (el rectangulo exterior queda fuera de pantalla en
            un TV bien ajustado; el de zona segura debe verse completo).

graysteps   10 barras verticales del negro al blanco en pasos iguales.
            Brillo y contraste: que se distingan los 10 escalones, que el
            negro no se "lave" y el blanco no sature.

window      Rectangulo blanco centrado del 30 % del area sobre negro.
            Estabilidad del sincronismo con carga de video (separador de
            sincronismo, control automatico de ganancia), regulacion de alta
            tension, arrastre o sombras a la derecha del rectangulo.

resolution  Cuatro zonas de lineas verticales blanco/negro de 1, 2, 4 y 8 px.
            Foco y respuesta en frecuencia del amplificador de video. La zona
            de 1 px es el limite de la Pi (~6.75 MHz) y supera el ancho de
            banda de un TV de 5 MHz: se espera verla gris o borrosa; la de
            2 px (~3.4 MHz) debe distinguirse en un TV en buen estado.
