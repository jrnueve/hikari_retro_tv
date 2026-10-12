#!/usr/bin/env python3
"""Hikari Retro TV (Pi Zero W) - Demonio del televisor: reproductor y web app.

En el U100 el reproductor es mpv y la web app es un cliente de su socket IPC.
En la Pi no hay mpv: cada canal es un pipeline de ffmpeg (hikaritv-canal) y
cambiar de canal es matarlo y lanzar otro. Por eso este demonio hace las dos
cosas en un solo proceso: supervisa el pipeline y sirve la web app. Sigue
habiendo una sola fuente de verdad del canal actual, que es este proceso; y
un solo interprete de Python en 363 MB de RAM, no dos.

Mientras el pipeline junta buffer (unos segundos), en el TV se ve una carta
con el nombre del canal, dibujada directo en el framebuffer. Si el canal se
cae, la carta dice "sin senal" y se reintenta solo.

Web app: clon de la del U100 (pagina /tv), sin volumen (es la perilla del
TV), sin color (el TV es blanco y negro) y sin modos de camaras.

Uso: hikaritvd [--conf /etc/hikari-tv/hikari-tv.conf]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import signal
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "/usr/local/lib/hikari-tv")
from hikaritv_comun import (AZAR, FAVORITOS, Catalogo,  # noqa: E402
                            azar_actual, azar_segundos, escribir_estado,
                            fijar_azar, fijar_azar_segundos, leer_conf,
                            leer_estado, log)

ETIQUETA = "hikaritvd"
LIB = "/usr/local/lib/hikari-tv"
ANCHO, ALTO = 720, 576
ARCHIVO_VIDEO = "/tmp/hikari-tv-video"

# Reintentos de un canal caido: espera creciente, hasta este tope.
REINTENTO_S = (3, 5, 10, 20, 30)
# Si un canal estuvo en el aire al menos esto, la proxima caida vuelve a
# empezar los reintentos desde el primero.
SANO_S = 60
# Un canal que no da imagen en este tiempo se trata como caido: ffmpeg
# reintenta segmentos fallidos (un 403, por ejemplo) sin terminar nunca.
SIN_IMAGEN_S = 45
# En modo azar, un canal que no aparece en este tiempo se saltea.
AZAR_SIN_SENAL_S = 25


def aviso(msg: str) -> None:
    log(ETIQUETA, msg)


# ---------------------------------------------------------------------------
# Pantalla: cartas en el framebuffer
# ---------------------------------------------------------------------------

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:                                   # sin python3-pil
    Image = None

FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FUENTE_NEGRITA = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _leer_sys(nombre: str, defecto: str) -> str:
    try:
        with open(f"/sys/class/graphics/fb0/{nombre}", encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        return defecto


class Pantalla:
    """Escribe imagenes de 720x576 en escala de grises en /dev/fb0.

    Solo la usan las cartas: el video lo escribe fbgray, y nunca escriben
    los dos a la vez (la carta va con el pipeline muerto o antes de que
    llegue su primer cuadro).
    """

    def __init__(self, logo: str):
        self.bpp = int(_leer_sys("bits_per_pixel", "32"))
        self.stride = int(_leer_sys("stride", str(ANCHO * self.bpp // 8)))
        self.logo = None
        if Image is not None:
            try:
                im = Image.open(logo).convert("RGBA")
                fondo = Image.new("RGBA", im.size, (0, 0, 0, 255))
                im = Image.alpha_composite(fondo, im).convert("L")
                alto = 150
                self.logo = im.resize((im.width * alto // im.height, alto))
            except OSError as e:
                aviso(f"sin logo: {e}")

    def _escribir(self, crudo: bytes) -> None:
        """crudo: cuadro ya en el formato del framebuffer, filas contiguas."""
        fila = ANCHO * self.bpp // 8
        try:
            with open("/dev/fb0", "r+b", buffering=0) as fb:
                if self.stride == fila:
                    fb.write(crudo)
                else:
                    for y in range(ALTO):
                        fb.seek(y * self.stride)
                        fb.write(crudo[y * fila:(y + 1) * fila])
        except OSError as e:
            aviso(f"framebuffer: {e}")

    def _a_crudo(self, im) -> bytes:
        if self.bpp == 32:
            return im.convert("RGB").convert("RGBX").tobytes()
        return im.convert("RGB").tobytes("raw", "BGR;16")

    def liso(self, v: int = 0) -> None:
        if self.bpp == 32:
            self._escribir(bytes((v, v, v, 0)) * (ANCHO * ALTO))
        else:
            p = ((v >> 3) << 11) | ((v >> 2) << 5) | (v >> 3)
            self._escribir(p.to_bytes(2, "little") * (ANCHO * ALTO))

    def carta(self, nombre: str, detalle: str, estado: str) -> None:
        """Carta entre canales: logo, nombre del canal, detalle y estado.

        Se dibuja en 768x576 (pixeles cuadrados) y se lleva a 720x576: el
        cuadro PAL ocupa la pantalla 4:3 entera, asi que cada pixel es un
        poco mas ancho que alto. Margenes amplios: un CRT recorta los bordes.
        """
        if Image is None:
            self.liso(16)
            return
        im = Image.new("L", (768, ALTO), 0)
        d = ImageDraw.Draw(im)
        if self.logo is not None:
            im.paste(self.logo, ((768 - self.logo.width) // 2, 50))
        grande = ImageFont.truetype(FUENTE_NEGRITA, 46)
        chica = ImageFont.truetype(FUENTE, 26)
        y = 245
        for linea in _partir(d, nombre or "-", grande, 600)[:2]:
            ancho = d.textlength(linea, font=grande)
            d.text(((768 - ancho) / 2, y), linea, font=grande, fill=225)
            y += 58
        for texto, color, alto in ((detalle, 150, y + 18), (estado, 110, 470)):
            ancho = d.textlength(texto, font=chica)
            d.text(((768 - ancho) / 2, alto), texto, font=chica, fill=color)
        self._escribir(self._a_crudo(im.resize((ANCHO, ALTO), Image.BILINEAR)))


def _partir(d, texto: str, fuente, ancho_max: int) -> list[str]:
    """Parte un texto en lineas que entren en ancho_max pixeles."""
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if d.textlength(prueba, font=fuente) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


# ---------------------------------------------------------------------------
# Eleccion de variante HLS
# ---------------------------------------------------------------------------

_RE_RES = re.compile(r"RESOLUTION=(\d+)x(\d+)")
_RE_BW = re.compile(r"[^-]BANDWIDTH=(\d+)")
_SIN_VERIFICAR = ssl._create_unverified_context()


# Lo mas grande que la Pi mueve sin saturarse, en pixeles por cuadro
# (medido: 720x576 70 %, 640x360 64 %; 1024x576 y 1280x720 llegan al 100 %).
PIXELES_MAX = 720 * 576


def elegir_variante(url: str) -> tuple[str, int, int, str]:
    """Si la URL es una lista maestra HLS, la variante que conviene bajar.

    ffmpeg con una lista maestra abre todas las variantes y se queda con la
    de mayor resolucion: en la Pi eso es el doble de WiFi y de CPU para un
    TV de 576 lineas. Se elige la variante mas grande que no pase de
    PIXELES_MAX (a igual tamano, la de menos kbps); si todas pasan, la mas
    chica. Si el audio va en una lista aparte (grupos EXT-X-MEDIA con URI),
    se deja la maestra: la variante sola no lo trae.

    Sin verificar TLS, como ffmpeg: si no, quedan como caidos canales que
    ffmpeg reproduce bien (leccion del U100).

    Devuelve (url a reproducir, ancho, alto, descripcion para el log);
    ancho y alto en 0 si no se saben.
    """
    if ".m3u8" not in url.lower():
        return url, 0, 0, "directa"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8,
                                    context=_SIN_VERIFICAR) as r:
            base = r.geturl()
            texto = r.read(200_000).decode("utf-8", "replace")
    except Exception as e:                                # noqa: BLE001
        return url, 0, 0, f"sin leer la lista ({e})"
    if "#EXT-X-STREAM-INF" not in texto:
        return url, 0, 0, "lista simple"
    if re.search(r"#EXT-X-MEDIA:[^\n]*TYPE=AUDIO[^\n]*URI=", texto):
        return url, 0, 0, "maestra con audio aparte"
    variantes, inf = [], None
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("#EXT-X-STREAM-INF"):
            inf = linea
        elif linea and not linea.startswith("#") and inf:
            m, bw = _RE_RES.search(inf), _RE_BW.search(inf)
            variantes.append((int(m.group(1)) if m else 0,
                              int(m.group(2)) if m else 0,
                              int(bw.group(1)) if bw else 0,
                              urllib.parse.urljoin(base, linea)))
            inf = None
    if not variantes:
        return url, 0, 0, "maestra sin variantes"
    entran = [v for v in variantes if 0 < v[0] * v[1] <= PIXELES_MAX]
    if entran:
        ancho, alto, bw, elegida = max(
            entran, key=lambda v: (v[0] * v[1], -v[2]))
    else:
        ancho, alto, bw, elegida = min(
            variantes, key=lambda v: (v[0] * v[1] or 1 << 30, v[2]))
    return (elegida, ancho, alto,
            f"variante {ancho}x{alto} {bw // 1000} kbps de {len(variantes)}")


# Proporcion del video, de la linea de ffmpeg que describe la entrada:
#   Stream #0:0[0x100]: Video: h264 (Main) (...), yuv420p(...), 720x576
#   [SAR 64:45 DAR 16:9], 25 fps, ...
_RE_VIDEO = re.compile(r"Video: h264.*?, (\d{2,5})x(\d{2,5})"
                       r"(?: \[SAR \d+:\d+ DAR (\d+):(\d+)\])?")
_RE_RUIDO = re.compile(r"error|fail|invalid|warn|denied|refused|not found",
                       re.IGNORECASE)


def rectangulo_activo(dar: float) -> tuple[int, int]:
    """(ancho, alto) que ocupa en el TV 4:3 una imagen de proporcion dar.

    La pantalla mide 768x576 en pixeles cuadrados (576 * 4/3 = 768) y se
    dibuja en 720x576. Un 16:9 da 720x432 (bandas arriba y abajo); uno mas
    angosto que 4:3, bandas a los costados.
    """
    if dar <= 0:
        return ANCHO, ALTO
    if dar >= 4 / 3:
        return ANCHO, min(ALTO, int(round(768 / dar / 2)) * 2)
    return min(ANCHO, int(round(ANCHO * dar / (4 / 3) / 2)) * 2), ALTO


# ---------------------------------------------------------------------------
# Reproductor
# ---------------------------------------------------------------------------

SINTONIZANDO, EN_AIRE, SIN_SENAL = "sintonizando", "en el aire", "sin senal"


class Reproductor:
    """Un canal a la vez: lanza hikaritv-canal y lo vigila.

    Toda la nocion de "que se esta viendo" vive aca: categoria, lista,
    posicion y estado de la senal. Persiste categoria y canal para que el
    televisor arranque donde quedo.
    """

    def __init__(self, cat: Catalogo, pantalla: Pantalla, conf: dict):
        self.cat = cat
        self.pantalla = pantalla
        self.conf = conf
        self.env = {**os.environ,
                    **{k: conf[k] for k in ("ALSA", "BUFFER", "BUFFER_PORC")
                       if k in conf},
                    "ARCHIVO_VIDEO": ARCHIVO_VIDEO}
        self.bandas = conf.get("ASPECTO", "bandas") != "estirar"
        self.categoria = cat.actual() or ""
        self.lista = cat.canales(self.categoria) if self.categoria else []
        guardado = leer_estado("canal")
        self.pos = next((c["pos"] for c in self.lista
                         if c["url"] == guardado), 0)
        self.senal = SINTONIZANDO
        self.desde = time.monotonic()        # ultimo cambio de senal
        self.sintonizado = time.monotonic()  # ultimo cambio de canal
        self._tarea: asyncio.Task | None = None
        self._cerrojo = asyncio.Lock()

    # --- Consultas -----------------------------------------------------------

    def canal(self) -> dict | None:
        if 0 <= self.pos < len(self.lista):
            return self.lista[self.pos]
        return None

    def _fijar_senal(self, senal: str) -> None:
        self.senal = senal
        self.desde = time.monotonic()

    # --- Cambios de canal ----------------------------------------------------

    async def sintonizar(self, pos: int | None = None,
                         categoria: str | None = None) -> None:
        """Cambia de canal (y de categoria, si se pide) y lo reproduce."""
        async with self._cerrojo:
            if categoria is not None and categoria != self.categoria:
                self.categoria = categoria
                self.lista = self.cat.canales(categoria)
                self.cat.fijar(categoria)
            if not self.lista:
                return
            self.pos = (pos if pos is not None else self.pos) % len(self.lista)
            escribir_estado("canal", self.lista[self.pos]["url"])
            await self._detener()
            self.sintonizado = time.monotonic()
            self._tarea = asyncio.create_task(self._reproducir(self.canal()))

    async def paso(self, delta: int) -> None:
        await self.sintonizar(self.pos + delta)

    async def ir_a(self, url: str, categoria: str | None = None) -> bool:
        """Por URL y no por posicion: la lista de la pagina puede estar
        desfasada (un favorito quitado sigue aca hasta la proxima carga)."""
        lista = (self.cat.canales(categoria)
                 if categoria and categoria != self.categoria else self.lista)
        i = next((c["pos"] for c in lista if c["url"] == url), None)
        if i is None:
            return False
        await self.sintonizar(i, categoria)
        return True

    async def _detener(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
            self._tarea = None

    async def apagar(self) -> None:
        await self._detener()

    # --- Vigilancia del pipeline ---------------------------------------------

    def _carta(self, canal: dict, estado: str) -> None:
        detalle = "   ".join(filter(None, [
            self.categoria, f"{canal['pos'] + 1}/{len(self.lista)}",
            canal.get("pais", "")]))
        self.pantalla.carta(canal["nombre"], detalle, estado)

    async def _reproducir(self, canal: dict) -> None:
        """Reproduce un canal hasta que lo cancelen; si se cae, reintenta."""
        intento = 0
        while True:
            self._fijar_senal(SINTONIZANDO)
            await asyncio.to_thread(self._carta, canal, "sintonizando...")
            url, ancho, alto, como = await asyncio.to_thread(
                elegir_variante, canal["url"])
            aviso(f"canal {canal['pos'] + 1} {canal['nombre']}: {como}")
            # Sin archivo hasta que ffmpeg describa el video: fbgray lo
            # espera, y uno viejo seria el tamano de otro canal
            try:
                os.remove(ARCHIVO_VIDEO)
            except OSError:
                pass
            inicio = time.monotonic()
            rc = await self._correr(url)
            aire = time.monotonic() - inicio if self.senal == EN_AIRE else 0
            if aire >= SANO_S:
                intento = 0
            espera = REINTENTO_S[min(intento, len(REINTENTO_S) - 1)]
            intento += 1
            aviso(f"el pipeline termino (rc={rc}, {aire:.0f} s en el aire); "
                  f"reintento en {espera} s")
            self._fijar_senal(SIN_SENAL)
            await asyncio.to_thread(self._carta, canal,
                                    f"sin senal - reintento en {espera} s")
            await asyncio.sleep(espera)

    def _video(self, texto: str) -> None:
        """Con la linea que describe el video, le pasa a fbgray el tamano
        real y el rectangulo donde dibujarlo."""
        m = _RE_VIDEO.search(texto)
        if not m:
            return
        ancho, alto = int(m.group(1)), int(m.group(2))
        dar = (int(m.group(3)) / int(m.group(4)) if m.group(3)
               else ancho / alto)
        # Un SD de 720 de ancho solo puede ser 16:9 o 4:3; muchos declaran
        # SAR 1:1 por error (DAR 5:4 o 3:2) y eso es 4:3
        if ancho == 720:
            dar = 16 / 9 if dar > 1.6 else 4 / 3
        act = rectangulo_activo(dar) if self.bandas else (ANCHO, ALTO)
        aviso(f"video {ancho}x{alto}, proporcion {dar:.2f}: "
              f"en pantalla {act[0]}x{act[1]}")
        try:
            with open(ARCHIVO_VIDEO + ".tmp", "w", encoding="ascii") as f:
                f.write(f"{ancho} {alto} {act[0]} {act[1]}\n")
            os.replace(ARCHIVO_VIDEO + ".tmp", ARCHIVO_VIDEO)
        except OSError as e:
            aviso(f"no se pudo escribir {ARCHIVO_VIDEO}: {e}")

    async def _correr(self, url: str) -> int | None:
        """Corre hikaritv-canal hasta que termine; lo mata si lo cancelan."""
        proc = await asyncio.create_subprocess_exec(
            f"{LIB}/hikaritv-canal", url,
            env=self.env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True)
        try:
            vistas = 0
            limite = time.monotonic() + SIN_IMAGEN_S
            while True:
                espera = (None if self.senal == EN_AIRE
                          else max(0.0, limite - time.monotonic()))
                try:
                    linea = await asyncio.wait_for(proc.stderr.readline(),
                                                   espera)
                except asyncio.TimeoutError:
                    aviso(f"sin imagen en {SIN_IMAGEN_S} s")
                    break
                if not linea:
                    break
                texto = linea.decode("utf-8", "replace").rstrip()
                if "fbgray: primer cuadro" in texto:
                    self._fijar_senal(EN_AIRE)
                elif "Video: h264" in texto:
                    self._video(texto)
                elif vistas < 20 and _RE_RUIDO.search(texto):
                    vistas += 1                   # sin inundar el journal
                    aviso(texto)
            if proc.returncode is None and self.senal != EN_AIRE:
                await _matar_grupo(proc)          # sin imagen: se corta
            return await proc.wait()
        finally:
            if proc.returncode is None:
                await _matar_grupo(proc)


async def _matar_grupo(proc) -> None:
    """Mata el grupo entero (bash, dos ffmpeg, mbuffer, fbgray) y espera.

    Hay que esperar: el siguiente canal necesita el dispositivo ALSA libre.
    """
    for sen, plazo in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(proc.pid, sen)
        except ProcessLookupError:
            return
        limite = time.monotonic() + plazo
        while time.monotonic() < limite:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                await proc.wait()
                return
            await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# Modo azar
# ---------------------------------------------------------------------------

async def bucle_azar(rep: Reproductor, conf: dict) -> None:
    """Cambia de canal al azar cada N segundos en el aire.

    RND: entre todos los canales; PAIS: los del pais del canal actual;
    CATEG: los de la categoria actual. RND y PAIS mudan el televisor a la
    categoria del canal elegido, como en el U100. Un canal que no aparece en
    AZAR_SIN_SENAL_S se saltea.
    """
    while True:
        await asyncio.sleep(2)
        criterio = azar_actual()
        if criterio == "no" or not rep.lista:
            continue
        ahora = time.monotonic()
        if rep.senal == EN_AIRE:
            vencido = ahora - rep.desde >= azar_segundos(
                conf.get("AZAR_SEGUNDOS", ""))
        else:
            vencido = ahora - rep.sintonizado >= AZAR_SIN_SENAL_S
        if not vencido:
            continue
        actual = rep.canal() or {}
        if criterio == "categ":
            candidatos = rep.lista
        else:
            candidatos = rep.cat.todos()
            if criterio == "pais" and actual.get("pais"):
                candidatos = [c for c in candidatos
                              if c["pais"] == actual["pais"]]
        candidatos = [c for c in candidatos if c["url"] != actual.get("url")]
        if not candidatos:
            continue
        elegido = random.choice(candidatos)
        aviso(f"azar {criterio}: {elegido['nombre']}")
        if criterio == "categ":
            await rep.sintonizar(elegido["pos"])
        else:
            await rep.sintonizar(elegido["pos"], elegido["categoria"])


# ---------------------------------------------------------------------------
# Web app (clon de la del U100, solo la pagina /tv)
# ---------------------------------------------------------------------------

CSS = """
:root{--amb:#ffb414}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#111;color:#ccc;font-family:monospace;padding:16px;
     max-width:520px;margin:auto}
h1{color:var(--amb);font-size:1.3em;letter-spacing:3px;display:inline-block}
h1 small{color:#555;font-size:.55em;letter-spacing:2px;margin-left:8px}
#estado{color:#888;font-size:.85em;margin:14px 0;min-height:3.2em;
        line-height:1.6;border-left:2px solid #333;padding-left:10px;
        display:flex;align-items:center;gap:10px}
#estado .txt{flex:1;min-width:0}
#canal{color:var(--amb);font-size:1.05em}
#senal.sin{color:#c55}
.lbl{color:#444;font-size:.7em;letter-spacing:3px;text-transform:uppercase;
     margin:16px 0 7px}
.g{display:flex;flex-wrap:wrap;gap:8px}
button.b{display:flex;align-items:center;justify-content:center;
    padding:13px 14px;border:1px solid #333;border-radius:6px;color:#aaa;
    background:none;font-size:.95em;font-family:monospace;
    flex:1 1 auto;min-width:72px;cursor:pointer;text-transform:uppercase}
button.b:active{background:#222}
button.b.act{border-color:var(--amb);color:var(--amb)}
input[type=text]{background:#181818;border:1px solid #333;border-radius:4px;
    color:#ccc;font-family:monospace;padding:10px;width:100%;margin:8px 0}
table{width:100%;border-collapse:collapse;font-size:.82em}
td{padding:7px 4px;border-bottom:1px solid #222;vertical-align:middle}
td.n{color:#555;width:3em}
td.meta{color:#555;text-align:right;white-space:nowrap;font-size:.85em}
tr.cur td{background:#1a1710}
tr.cur td.t{color:var(--amb)}
a.cn{color:#bbb;text-decoration:none}
#msg{font-size:.78em;color:#666;min-height:1.3em;margin-top:10px}
hr.sep{border:none;border-top:1px solid #222;margin:18px 0}
.fila{flex-wrap:nowrap;gap:6px}
.fila button.b{flex:1 1 0;min-width:0;padding:13px 2px}
.nota{color:#666;font-size:.78em;margin-top:6px;min-height:1.2em}
#fav{display:none;flex-direction:column;align-items:center;cursor:pointer;
     background:none;border:none;font-family:monospace;padding:0 4px}
#fav .c{font-size:1.3em;line-height:1;color:#555}
#fav .t{font-size:.65em;letter-spacing:1px;color:#555;margin-top:2px}
#fav.si .c,#fav.si .t{color:var(--amb)}
td.x{width:2.4em;text-align:right}
td.x button{background:none;border:1px solid #333;border-radius:4px;
            color:#888;cursor:pointer;padding:3px 8px;font-family:monospace}
"""

CUERPO = """
<h1>HIKARI RETRO TV<small>B/N</small></h1>
<div id="estado">
  <div class="txt">
    <div id="canal">...</div>
    <div id="sub"></div>
    <div id="senal"></div>
  </div>
  <button id="fav" onclick="alternarFavorito()" title="favorito">
    <span class="c"></span><span class="t">favorito</span>
  </button>
</div>

<div class="lbl">canal</div>
<div class="g">
  <button class="b" onclick="cmd('prev')">anterior</button>
  <button class="b" onclick="cmd('next')">siguiente</button>
</div>
<div class="g fila" id="azar" style="margin-top:8px"></div>
<div class="g fila" id="azarTiempos" style="margin-top:8px;display:none"></div>
<div class="nota" id="azarNota"></div>

<hr class="sep">
<div class="lbl">categoria</div>
<div class="g" id="cats"></div>

<input type="text" id="filtro" placeholder="filtrar por nombre, pais o idioma"
       oninput="pintarLista()">
<div id="msg"></div>
<table><tbody id="lista"></tbody></table>
"""

JS = """
let datos = {}, canales = [], catCargada = null;
const DURACIONES = __DURACIONES__;
const AZAR_NOTA = {rnd: 'al azar entre todos los canales',
                   pais: 'al azar entre los canales del mismo pais',
                   categ: 'al azar dentro de la categoria'};

function cmd(c){
  fetch('/cmd/' + c).then(() => setTimeout(actualizar, 400));
}

// Por URL: la posicion de la pagina puede no coincidir con la del equipo.
function irA(url){
  fetch('/cmd/ir?url=' + encodeURIComponent(url) +
        '&cat=' + encodeURIComponent(catCargada || ''))
    .then(() => setTimeout(actualizar, 400));
}

function fijarAzar(m){
  datos.azar = (datos.azar === m) ? 'no' : m;
  pintarAzar();
  fetch('/cmd/azar/' + datos.azar).then(() => setTimeout(actualizar, 400));
}

function fijarAzarSegundos(s){
  datos.azar_segundos = s;
  pintarAzar();
  fetch('/cmd/azar/segundos/' + s).then(() => setTimeout(actualizar, 400));
}

function pintarAzar(){
  const g = document.getElementById('azar');
  g.innerHTML = '';
  (datos.azares || []).forEach(a => {
    const b = document.createElement('button');
    b.className = 'b' + (a.clave === datos.azar ? ' act' : '');
    b.textContent = a.nombre;
    b.onclick = () => fijarAzar(a.clave);
    g.appendChild(b);
  });
  const activo = datos.azar && datos.azar !== 'no';
  const t = document.getElementById('azarTiempos');
  t.style.display = activo ? 'flex' : 'none';
  t.innerHTML = '';
  DURACIONES.forEach(([s, etiqueta]) => {
    const b = document.createElement('button');
    b.className = 'b' + (s === datos.azar_segundos ? ' act' : '');
    b.textContent = etiqueta;
    b.onclick = () => fijarAzarSegundos(s);
    t.appendChild(b);
  });
  const d = DURACIONES.find(([s]) => s === datos.azar_segundos);
  document.getElementById('azarNota').textContent = activo
    ? AZAR_NOTA[datos.azar] + ', cada ' +
      (d ? d[1].toLowerCase() : datos.azar_segundos + 's')
    : '';
}

function alternarFavorito(){
  datos.favorito = !datos.favorito;
  pintarCorazon();
  fetch('/cmd/favorito').then(() => setTimeout(actualizar, 400));
}

function quitarFavorito(pos){
  fetch('/cmd/favorito/quitar/' + pos).then(() => {
    catCargada = null;
    setTimeout(actualizar, 400);
  });
}

function pintarCorazon(){
  const f = document.getElementById('fav');
  f.style.display = datos.conectado ? 'flex' : 'none';
  f.className = datos.favorito ? 'si' : '';
  f.querySelector('.c').textContent = datos.favorito ? '\\u2665' : '\\u2661';
  f.title = datos.favorito ? 'quitar de favoritos' : 'agregar a favoritos';
}

// Tocar una categoria solo la muestra; el equipo cambia al elegir un canal
// de la lista (o con el boton "ver" para ir al primero).
function verCat(nombre){
  if (nombre === catCargada) return;
  cargarCanales(nombre);
}

function pintarCats(){
  const g = document.getElementById('cats');
  g.innerHTML = '';
  (datos.categorias || []).forEach(c => {
    const b = document.createElement('button');
    b.className = 'b' + (c === (catCargada || datos.categoria) ? ' act' : '');
    b.textContent = c === 'favoritos' ? '\\u2665 favoritos' : c;
    b.onclick = () => verCat(c);
    g.appendChild(b);
  });
}

function pintarLista(){
  const q = document.getElementById('filtro').value.toLowerCase().trim();
  const cuerpo = document.getElementById('lista');
  const vistos = canales.filter(c => !q ||
      c.nombre.toLowerCase().includes(q) ||
      (c.pais || '').toLowerCase().includes(q) ||
      (c.idiomas || []).join(',').toLowerCase().includes(q));
  cuerpo.innerHTML = '';
  vistos.slice(0, 300).forEach(c => {
    const tr = document.createElement('tr');
    if (c.url === datos.path && catCargada === datos.categoria) tr.className = 'cur';
    tr.innerHTML = '<td class="n">' + (c.pos + 1) + '</td>' +
      '<td class="t"><a class="cn" href="#"></a></td>' +
      '<td class="meta">' + [c.pais, c.resolucion].filter(Boolean).join(' ') +
      '</td>';
    const a = tr.querySelector('a.cn');
    a.textContent = c.nombre;
    a.onclick = () => { irA(c.url); return false; };
    if (catCargada === 'favoritos'){
      const td = document.createElement('td');
      td.className = 'x';
      const b = document.createElement('button');
      b.textContent = '\\u2715';
      b.title = 'quitar de favoritos';
      b.onclick = () => quitarFavorito(c.pos);
      td.appendChild(b);
      tr.appendChild(td);
    }
    cuerpo.appendChild(tr);
  });
  const otra = catCargada && catCargada !== datos.categoria;
  document.getElementById('msg').textContent =
    vistos.length + ' de ' + canales.length + ' canales' +
    (vistos.length > 300 ? ' (se muestran los primeros 300)' : '') +
    (otra ? ' - toca uno para cambiar a ' + catCargada : '');
}

function cargarCanales(cat){
  fetch('/api/canales?cat=' + encodeURIComponent(cat))
    .then(r => r.json()).then(j => {
      canales = j.canales || [];
      catCargada = cat;
      pintarCats();
      pintarLista();
    });
}

function pintar(j){
  document.getElementById('canal').textContent = j.total
    ? (j.pos + 1) + '/' + j.total + '  ' + (j.canal || '-') : 'sin canales';
  document.getElementById('sub').textContent =
    [j.categoria, j.pais, j.resolucion].filter(Boolean).join('   ');
  const s = document.getElementById('senal');
  s.textContent = j.senal + ' (' + j.segundos + ' s)';
  s.className = j.senal === 'sin senal' ? 'sin' : '';
  pintarCorazon();
  pintarAzar();
  pintarCats();
  if (catCargada === null) cargarCanales(j.categoria);
  else pintarLista();
}

function actualizar(){
  fetch('/status').then(r => r.json()).then(j => {
    datos = j;
    pintar(j);
  }).catch(() => {
    datos.conectado = false;
    document.getElementById('canal').textContent = 'sin conexion con el equipo';
  });
}

actualizar();
// Solo se sondea con la pagina visible.
setInterval(() => { if (!document.hidden) actualizar(); }, 3000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) actualizar();
});
"""

# Opciones del tiempo por canal en modo azar: (segundos, etiqueta).
DURACIONES = [(30, "30S"), (60, "1M"), (300, "5M"), (900, "15M"),
              (1800, "30M"), (3600, "1H")]

PAGINA = ("""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hikari Retro TV</title>
<style>""" + CSS + """</style>
</head>
<body>
""" + CUERPO + """
<script>
""" + JS.replace("__DURACIONES__", json.dumps(DURACIONES)) + """
</script>
</body>
</html>
""").encode("utf-8")


class Control:
    def __init__(self, rep: Reproductor, conf: dict):
        self.rep = rep
        self.cat = rep.cat
        self.conf = conf

    def estado(self) -> dict:
        rep = self.rep
        canal = rep.canal() or {}
        url = canal.get("url", "")
        return {
            "conectado": True,
            "pos": rep.pos,
            "total": len(rep.lista),
            "canal": canal.get("nombre", ""),
            "pais": canal.get("pais", ""),
            "resolucion": canal.get("resolucion", ""),
            "path": url,
            "favorito": bool(url) and self.cat.es_favorito(url),
            "categoria": rep.categoria,
            "categorias": self.cat.categorias(),
            "senal": rep.senal,
            "segundos": int(time.monotonic() - rep.desde),
            "azar": azar_actual(),
            "azares": [{"clave": k, "nombre": n} for k, n in AZAR.items()],
            "azar_segundos": azar_segundos(self.conf.get("AZAR_SEGUNDOS", "")),
        }

    def alternar_favorito(self) -> bool:
        """Corazon: agrega o quita el canal en pantalla. No cambia de canal."""
        canal = self.rep.canal()
        if not canal:
            return False
        if self.cat.es_favorito(canal["url"]):
            self._quitar_favorito(url=canal["url"])
            return True
        return self.cat.agregar_favorito(canal["url"], canal["nombre"])

    def _quitar_favorito(self, pos: int | None = None,
                         url: str | None = None) -> bool:
        """Quita un favorito; si se esta viendo favoritos, rehace la lista.

        El canal en pantalla queda en la lista aunque se lo quite (si no,
        las posiciones se corren y el siguiente toque al corazon borraria
        otro; paso en el U100 y se perdieron 4 favoritos).
        """
        rep = self.rep
        if self.cat.quitar_favorito(pos=pos, url=url) is None:
            return False
        actual = (rep.canal() or {}).get("url")
        if rep.categoria == FAVORITOS:
            nueva = self.cat.canales(FAVORITOS)
            i = next((c["pos"] for c in nueva if c["url"] == actual), None)
            if i is not None:
                rep.lista, rep.pos = nueva, i
        return True

    async def ejecutar(self, ruta: str, query: dict) -> bool:
        """Aplica un comando /cmd/<ruta>. Devuelve si se reconocio."""
        partes = ruta.strip("/").split("/")
        c = partes[0] if partes else ""
        rep = self.rep

        if c == "next":
            await rep.paso(1)
        elif c == "prev":
            await rep.paso(-1)
        elif c == "canal" and len(partes) > 1:
            try:
                await rep.sintonizar(int(partes[1]))
            except ValueError:
                return False
        elif c == "ir":
            cat = (query.get("cat") or [""])[0] or None
            if cat is not None and cat not in self.cat.categorias():
                return False
            return await rep.ir_a((query.get("url") or [""])[0], cat)
        elif c == "categoria" and len(partes) > 1:
            nombre = urllib.parse.unquote(partes[1])
            if nombre not in self.cat.categorias():
                return False
            await rep.sintonizar(0, nombre)
        elif c == "azar" and len(partes) > 2 and partes[1] == "segundos":
            try:
                fijar_azar_segundos(int(partes[2]))
            except ValueError:
                return False
        elif c == "azar" and len(partes) == 2:
            try:
                fijar_azar(partes[1])
            except ValueError:
                return False
        elif c == "favorito" and len(partes) == 1:
            return self.alternar_favorito()
        elif c == "favorito" and len(partes) > 2 and partes[1] == "quitar":
            try:
                return self._quitar_favorito(pos=int(partes[2]))
            except ValueError:
                return False
        else:
            return False
        return True


def _responder(writer, cuerpo: bytes, tipo: str = "text/html; charset=utf-8",
               codigo: str = "200 OK", extra: str = "") -> None:
    cab = (f"HTTP/1.1 {codigo}\r\n"
           f"Content-Type: {tipo}\r\n"
           f"Content-Length: {len(cuerpo)}\r\n"
           "Cache-Control: no-store\r\n"
           f"Connection: close\r\n{extra}\r\n")
    writer.write(cab.encode("latin-1") + cuerpo)


def _json(writer, datos: dict, codigo: str = "200 OK") -> None:
    _responder(writer, json.dumps(datos, ensure_ascii=False).encode("utf-8"),
               "application/json; charset=utf-8", codigo)


def crear_handler(control: Control):
    async def handler(reader, writer):
        try:
            linea = await asyncio.wait_for(reader.readline(), timeout=5.0)
            while True:
                h = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if h in (b"\r\n", b"\n", b""):
                    break

            partes = linea.decode("latin-1", "replace").split()
            if len(partes) < 2:
                return
            destino = urllib.parse.urlsplit(partes[1])
            ruta = destino.path
            query = urllib.parse.parse_qs(destino.query)

            if ruta == "/":
                _responder(writer, b"", codigo="302 Found",
                           extra="Location: /tv\r\n")
            elif ruta == "/tv":
                _responder(writer, PAGINA)
            elif ruta == "/status":
                _json(writer, control.estado())
            elif ruta == "/api/canales":
                cat = (query.get("cat") or [control.rep.categoria])[0]
                _json(writer, {"categoria": cat,
                               "canales": control.cat.canales(cat)})
            elif ruta.startswith("/cmd/"):
                ok = await control.ejecutar(ruta[len("/cmd/"):], query)
                _json(writer, {"ok": ok}, "200 OK" if ok else "400 Bad Request")
            else:
                _responder(writer, b"no encontrado", "text/plain; charset=utf-8",
                           "404 Not Found")
            await writer.drain()
        except (asyncio.TimeoutError, ConnectionError):
            pass
        except Exception as e:                                # noqa: BLE001
            aviso(f"error atendiendo request: {e}")
        finally:
            try:
                writer.close()
            except Exception:                                 # noqa: BLE001
                pass
    return handler


# ---------------------------------------------------------------------------

async def principal(conf: dict) -> None:
    cat = Catalogo(conf.get("DIR_CANALES",
                            os.path.expanduser("~/.local/share/hikari-tv/canales")),
                   conf.get("CATEGORIA_INICIAL", ""))
    pantalla = Pantalla(conf.get("LOGO", f"{LIB}/logo.png"))
    rep = Reproductor(cat, pantalla, conf)
    aviso(f"categorias: {cat.categorias() or 'ninguna'}")
    if Image is None:
        aviso("sin python3-pil: las cartas seran una pantalla lisa")

    puerto = int(conf.get("PUERTO", "8080"))
    server = await asyncio.start_server(crear_handler(Control(rep, conf)),
                                        "0.0.0.0", puerto)
    aviso(f"web app en http://0.0.0.0:{puerto}")

    fin = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sen in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sen, fin.set)

    if rep.lista:
        await rep.sintonizar()
    else:
        pantalla.carta("sin canales", cat.dir.as_posix(), "")
    azar = asyncio.create_task(bucle_azar(rep, conf))
    async with server:
        await fin.wait()
    azar.cancel()
    await rep.apagar()
    pantalla.liso(0)
    aviso("detenido")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", default="/etc/hikari-tv/hikari-tv.conf")
    args = ap.parse_args()
    asyncio.run(principal(leer_conf(args.conf)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
