# 05 - Plataforma IPTV (hikaritvd)

Televisor IPTV para el TV blanco y negro, equivalente al Hikari TV del U100
(`D:\electronica\hikari_tv`) pero sobre la Pi Zero W. Sin controles fisicos
por ahora: el volumen es la perilla del TV; canal y categoria se manejan
desde la web app, clonada de la del U100.

Codigo en [`plataforma/`](../../plataforma/).

## Arquitectura

```
                  +--------------------------------------------+
  celular ------> |  hikaritvd (Python, asyncio, un proceso)   |
  :8080           |   - web app (pagina /tv, API /status /cmd)  |
                  |   - catalogo, favoritos, azar               |
                  |   - supervisa el pipeline y las cartas      |
                  +------------------+-------------------------+
                                     | lanza / mata (grupo de procesos)
                                     v
  hikaritv-canal:  ffmpeg (descarga) | mbuffer | ffmpeg (h264_v4l2m2m) | fbgray -> /dev/fb0
                                                         \-> ALSA PWM (audio mono)
```

En el U100 el reproductor es mpv y la web app es cliente de su socket IPC.
En la Pi no hay mpv: cada canal es un pipeline de ffmpeg y cambiar de canal
es matarlo y lanzar otro. Por eso un solo demonio hace las dos cosas: sigue
habiendo una unica fuente de verdad del canal actual, y un solo interprete
de Python en 363 MB de RAM.

| Pieza | En la Pi |
|---|---|
| `hikaritvd` | `/usr/local/bin/hikaritvd`, servicio `hikaritvd.service` (usuario `pi`, VT 8) |
| Pipeline y fbgray | `/usr/local/lib/hikari-tv/` |
| Configuracion | `/etc/hikari-tv/hikari-tv.conf` |
| Categorias | `~/.local/share/hikari-tv/canales/*.m3u` |
| Estado (categoria, canal, favoritos, azar) | `~/.local/state/hikari-tv/` |

`tvtestd` queda instalado pero deshabilitado: el servicio declara
`Conflicts=tvtestd.service`, asi que arrancar uno detiene al otro. Ojo:
`stream/canal.sh` al terminar arranca `tvtestd`, lo que detiene `hikaritvd`
(volver con `sudo systemctl start hikaritvd`).

## Web app

`http://192.168.1.40:8080` (desde el celular, por IP: ver la leccion del
U100 sobre https forzado y mDNS en Android).

Igual que la del U100: anterior/siguiente, azar (RND, PAIS, CATEG con
tiempos), corazon de favoritos, categorias y lista con filtro. Sin volumen,
sin color y sin modos de camaras. Una diferencia a proposito: tocar una
categoria solo muestra su lista; el TV cambia al elegir un canal. En la Pi
cada sintonia cuesta ~8 s de buffer, y asi se puede recorrer sin cambiar.

## Cartas

Mientras el pipeline junta buffer, en el TV se ve una carta dibujada con
PIL directo en el framebuffer: logo, nombre del canal, categoria, posicion,
pais y estado ("sintonizando...", "sin senal - reintento en N s"). Se
dibuja en 768x576 (pixeles cuadrados) y se lleva a 720x576, con margenes
amplios por el sobrebarrido del CRT.

## Tamano de imagen: fbgray hace todo, ffmpeg no escala nada

Medicion que define el diseno: **escalar con swscale satura la Pi.** ART
(720x576 anamorfico 16:9) con bandas hechas por ffmpeg (`scale`+`pad`):
100 % de CPU; estirado sin escalar: 82 %. Cambiar el algoritmo a
`neighbor` no mejoro nada: el costo es pasar el cuadro por swscale.

Solucion: ffmpeg entrega la luma en el tamano nativo del canal y fbgray la
lleva a pantalla por vecino mas cercano con tablas precalculadas, pintando
negro alrededor. Cuesta lo mismo que la copia que ya hacia.

fbgray necesita saber el tamano de entrada antes del primer cuadro
(rawvideo no lleva cabecera). La etapa 2 de ffmpeg corre con
`-loglevel info` y describe el video (`720x576 [SAR 64:45 DAR 16:9]`) antes
de entregar cuadros; hikaritvd lo lee y escribe `/tmp/hikari-tv-video`
("ancho alto ancho_activo alto_activo"). fbgray espera el primer dato en
stdin y recien ahi lee el archivo. Reglas de proporcion:

- La pantalla es 4:3 (768x576 en pixeles cuadrados). Un 16:9 queda en
  720x432 con bandas; uno mas angosto que 4:3, con bandas a los costados.
- Un SD de 720 de ancho solo puede ser 16:9 o 4:3. Muchos declaran SAR 1:1
  por error (DAR 3:2 en 720x480): se redondea a 4:3.
- El atributo RESOLUTION de una lista maestra puede mentir: Canal 9
  Resistencia dice 720x480 y el video es 720x406. Por eso manda lo que dice
  ffmpeg, no la lista.

`ASPECTO=estirar` en la conf desactiva las bandas.

## Que canales entran

CPU total medida en la Pi con el pipeline completo (promedio de 20-30 s):

| Video | CPU | |
|---|---|---|
| 640x360 | 64 % | entra |
| 720x406 (16:9) | 70 % | entra |
| 720x480 | 72 % | entra |
| 720x576 16:9, con bandas | 80 % | entra |
| 854x480, 2 Mbps | 95 % | entra, al limite |
| 1024x576 | 100 % | se sacrifica |
| 1280x720 | 100 % | se sacrifica |

Criterio: **ancho x alto <= 720x576 y al menos 360 lineas** (debajo la
imagen queda muy pobre). hikaritvd elige en cada lista maestra la variante
mas grande que cumpla; ffmpeg con una maestra baja todas las variantes y se
queda con la mayor, que en la Pi es el doble de WiFi y CPU.

Catalogo: `plataforma/relevar_sd.py` (en la PC) sondea las listas del
catalogo del U100 (7.379 canales H.264): **3.551 aptos**. Se sacrifican
2.149 maestras sin variante apta, 810 listas simples de otro tamano, 476
maestras con audio en lista aparte (la variante sola no trae audio) y 393
que no responden. `plataforma/armar_canales.py` arma las categorias por
tema (general, noticias, peliculas, musica, infantiles, documentales,
entretenimiento, deportes, religion) mas espanol y argentina. `pruebas` va
a mano.

## Fallas y recuperacion

- Si el pipeline termina, carta "sin senal" y reintento a los 3, 5, 10, 20
  y 30 s (y despues cada 30). Un canal que estuvo 60 s en el aire vuelve a
  empezar la escalera.
- Si no hay imagen en 45 s, el canal se da por caido: ffmpeg reintenta
  segmentos fallidos sin terminar nunca.
- Hay CDN que dan 403 al User-Agent de ffmpeg (Lavf): la descarga va con
  `-user_agent "Mozilla/5.0"`. Lo mismo la lectura de la lista maestra en
  hikaritvd, que ademas no verifica TLS, igual que ffmpeg (si no, quedan
  como caidos canales que funcionan; leccion del U100).
- Canal sin audio: la salida ALSA queda sin pista y ffmpeg falla; cuenta
  como caido. Pendiente.

## Despliegue

Desde la PC (Git Bash): `plataforma/desplegar.sh`. Copia `plataforma/` a
`/tmp` de la Pi y corre `instalar.sh` con sudo (sin clave en esta Pi):
instala dependencias (`python3-pil`), compila fbgray, agrega claves nuevas
a la conf sin pisar la existente, reemplaza las categorias (los favoritos
no se tocan) y reinicia el servicio. El TV vuelve al canal en que estaba.

Para medir CPU por proceso: `/tmp/cpu.sh 30` en la Pi (script de esta
sesion; no sobrevive un reinicio).
