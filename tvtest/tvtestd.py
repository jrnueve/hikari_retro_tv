#!/usr/bin/env python3
"""tvtestd - generador de senales de prueba para TV blanco y negro (PAL 576i).

Servicio en segundo plano (systemd). Dibuja patrones en escala de grises en
/dev/fb0 (salida compuesta legacy, 720x576) y genera un tono senoidal por la
salida de audio PWM existente (ALSA bcm2835, mono por GPIO19 + filtro RC).

Se controla con el comando `tvtest` a traves de un socket UNIX local. Cambiar
de patron solo reescribe el framebuffer: el sincronismo lo genera el firmware
de forma continua y no se interrumpe.

Solo usa la biblioteca estandar (la Pi no tiene numpy). Requiere root para
tomar la consola virtual y crear el socket en /run.
"""

import array
import fcntl
import grp
import math
import os
import signal
import socketserver
import struct
import subprocess
import sys
import threading

ANCHO, ALTO = 720, 576
# El cuadro de 720x576 ocupa la pantalla 4:3 completa, asi que cada pixel es
# mas ancho que alto. Se compensa en los patrones geometricos.
PAR = (4 / 3) / (ANCHO / ALTO)          # ancho/alto fisico de un pixel (~1.067)
GROSOR = 2                              # lineas de 2 px (una por campo en 576i)

FB = "/dev/fb0"
VT_PATRON = 8                           # VT sin getty
SOCKET = "/run/tvtest.sock"
PATRON_INICIAL = "crosshatch"
REFRESCO_S = 2.0                        # reescritura periodica del cuadro

ALSA = "plughw:0,0"
TASA = 48000
FREQ_MIN, FREQ_MAX = 100, 10000
FREQ_INICIAL = 1000
VOLUMEN_INICIAL = 50

FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
VT_ACTIVATE = 0x5606
KDSETMODE = 0x4B3A
KD_TEXT, KD_GRAPHICS = 0, 1
F_SETPIPE_SZ = 1031

BLANCO, GRIS, NEGRO = 255, 128, 0


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Patrones: lienzo en escala de grises, 1 byte por pixel, ANCHO*ALTO
# ---------------------------------------------------------------------------

def campo(v):
    return bytearray([v]) * (ANCHO * ALTO)


def rect_lleno(c, x0, y0, x1, y1, v):
    """Rellena [x0, x1) x [y0, y1)."""
    x0, x1 = max(0, x0), min(ANCHO, x1)
    if x1 <= x0:
        return
    tramo = bytes([v]) * (x1 - x0)
    for y in range(max(0, y0), min(ALTO, y1)):
        c[y * ANCHO + x0:y * ANCHO + x1] = tramo


def marco(c, x0, y0, x1, y1, v=BLANCO, g=GROSOR):
    """Rectangulo hueco cuyo borde exterior es [x0, x1) x [y0, y1)."""
    rect_lleno(c, x0, y0, x1, y0 + g, v)
    rect_lleno(c, x0, y1 - g, x1, y1, v)
    rect_lleno(c, x0, y0, x0 + g, y1, v)
    rect_lleno(c, x1 - g, y0, x1, y1, v)


def de_fila(fila):
    """Repite una fila de ANCHO bytes en todo el alto."""
    return bytearray(bytes(fila) * ALTO)


def p_crosshatch(columnas=14, filas=10):
    c = campo(NEGRO)
    for i in range(columnas + 1):
        x = round(i * (ANCHO - GROSOR) / columnas)
        rect_lleno(c, x, 0, x + GROSOR, ALTO, BLANCO)
    for j in range(filas + 1):
        y = round(j * (ALTO - GROSOR) / filas)
        rect_lleno(c, 0, y, ANCHO, y + GROSOR, BLANCO)
    return c


def p_circle():
    c = campo(NEGRO)
    marco(c, 0, 0, ANCHO, ALTO)
    sx, sy = round(ANCHO * 0.05), round(ALTO * 0.05)     # zona segura 90 %
    marco(c, sx, sy, ANCHO - sx, ALTO - sy)

    cx, cy = (ANCHO - 1) / 2, (ALTO - 1) / 2
    b = (ALTO - 2 * sy) / 2          # radio vertical: toca la zona segura
    a = b / PAR                      # radio horizontal en pixeles, compensado
    bi, ai = b - GROSOR, a - GROSOR
    for y in range(ALTO):
        dy = y - cy
        if abs(dy) > b:
            continue
        xo = a * math.sqrt(1 - (dy / b) ** 2)
        xi = ai * math.sqrt(1 - (dy / bi) ** 2) if abs(dy) < bi else 0.0
        izq0, izq1 = round(cx - xo), round(cx - xi)
        der0, der1 = round(cx + xi), round(cx + xo)
        rect_lleno(c, izq0, y, max(izq1, izq0 + 1), y + 1, BLANCO)
        rect_lleno(c, min(der0, der1 - 1), y, der1 + 1, y + 1, BLANCO)

    # Cruz central del diametro del circulo
    x_c, y_c = ANCHO // 2 - GROSOR // 2, ALTO // 2 - GROSOR // 2
    rect_lleno(c, x_c, round(cy - b), x_c + GROSOR, round(cy + b) + 1, BLANCO)
    rect_lleno(c, round(cx - a), y_c, round(cx + a) + 1, y_c + GROSOR, BLANCO)
    return c


def p_graysteps(n=10):
    fila = bytearray(ANCHO)
    for i in range(n):
        v = round(i * 255 / (n - 1))
        x0, x1 = round(i * ANCHO / n), round((i + 1) * ANCHO / n)
        fila[x0:x1] = bytes([v]) * (x1 - x0)
    return de_fila(fila)


def p_window(fraccion=0.30):
    c = campo(NEGRO)
    w = round(ANCHO * math.sqrt(fraccion))
    h = round(ALTO * math.sqrt(fraccion))
    x0, y0 = (ANCHO - w) // 2, (ALTO - h) // 2
    rect_lleno(c, x0, y0, x0 + w, y0 + h, BLANCO)
    return c


def p_resolution(anchos=(1, 2, 4, 8)):
    fila = bytearray(ANCHO)
    zona = ANCHO // len(anchos)
    for k, n in enumerate(anchos):
        for x in range(k * zona, (k + 1) * zona):
            fila[x] = BLANCO if ((x - k * zona) // n) % 2 == 0 else NEGRO
    return de_fila(fila)


PATRONES = {
    "white": ("Campo blanco 100 %", lambda: campo(BLANCO)),
    "gray": ("Campo gris 50 %", lambda: campo(GRIS)),
    "black": ("Campo negro 0 %", lambda: campo(NEGRO)),
    "crosshatch": ("Cuadricula 14x10, lineas de 2 px", p_crosshatch),
    "circle": ("Circulo, cruz, borde exacto y zona segura 90 %", p_circle),
    "graysteps": ("10 barras del negro al blanco", p_graysteps),
    "window": ("Ventana blanca 30 % del area sobre negro", p_window),
    "resolution": ("Lineas verticales de 1, 2, 4 y 8 px", p_resolution),
}


# ---------------------------------------------------------------------------
# Video: framebuffer y consola virtual
# ---------------------------------------------------------------------------

def leer_geometria(fd):
    v = fcntl.ioctl(fd, FBIOGET_VSCREENINFO, bytes(160))
    xres, yres, _, _, _, _, bpp, _ = struct.unpack_from("8I", v, 0)
    f = fcntl.ioctl(fd, FBIOGET_FSCREENINFO, bytes(80))
    # struct fb_fix_screeninfo en ARM 32-bit: line_length queda en el offset 44
    line_length = struct.unpack_from("I", f, 44)[0] or xres * bpp // 8
    return xres, yres, bpp, line_length


def a_framebuffer(gris, bpp, line_length):
    """Convierte el lienzo gris al formato del framebuffer (R=G=B)."""
    bpp_bytes = bpp // 8
    fila_util = ANCHO * bpp_bytes
    if bpp == 32:
        planos = [(k, None) for k in range(3)]          # B, G, R; el 4to queda en 0
    elif bpp == 16:                                     # RGB565
        lo = bytes((((v >> 2) << 5) | (v >> 3)) & 0xFF for v in range(256))
        hi = bytes((((v >> 3) << 11) | ((v >> 2) << 5)) >> 8 for v in range(256))
        planos = [(0, lo), (1, hi)]
    else:
        raise RuntimeError(f"bpp {bpp} no soportado")
    planos = [(k, bytes(gris).translate(t) if t else gris) for k, t in planos]

    if line_length == fila_util:
        out = bytearray(fila_util * ALTO)
        for k, datos in planos:
            out[k::bpp_bytes] = datos
        return bytes(out)
    out = bytearray(line_length * ALTO)
    for y in range(ALTO):
        o = y * line_length
        for k, datos in planos:
            out[o + k:o + fila_util:bpp_bytes] = datos[y * ANCHO:(y + 1) * ANCHO]
    return bytes(out)


class Video:
    def __init__(self):
        self.lock = threading.Lock()
        self.fd = os.open(FB, os.O_RDWR)
        xres, yres, bpp, line_length = leer_geometria(self.fd)
        if (xres, yres) != (ANCHO, ALTO):
            raise RuntimeError(f"framebuffer {xres}x{yres}, se esperaba {ANCHO}x{ALTO}")
        self.cuadros = {}
        for nombre, (_, generar) in PATRONES.items():
            self.cuadros[nombre] = a_framebuffer(generar(), bpp, line_length)
        log(f"fb {xres}x{yres} {bpp}bpp line_length={line_length}, "
            f"{len(self.cuadros)} patrones listos")
        self.actual = None
        self.tty = None

    def tomar_consola(self):
        """Pasa a un VT libre en modo grafico: fbcon deja de dibujar texto y cursor."""
        try:
            self.tty = os.open(f"/dev/tty{VT_PATRON}", os.O_RDWR)
            fcntl.ioctl(self.tty, VT_ACTIVATE, VT_PATRON)
            threading.Event().wait(0.3)
            fcntl.ioctl(self.tty, KDSETMODE, KD_GRAPHICS)
        except OSError as e:
            log(f"aviso: no se pudo tomar la consola ({e})")

    def soltar_consola(self):
        if self.tty is None:
            return
        try:
            fcntl.ioctl(self.tty, KDSETMODE, KD_TEXT)
            fcntl.ioctl(self.tty, VT_ACTIVATE, 1)
        except OSError:
            pass
        os.close(self.tty)
        self.tty = None

    def mostrar(self, nombre=None):
        with self.lock:
            nombre = nombre or self.actual
            os.pwrite(self.fd, self.cuadros[nombre], 0)
            self.actual = nombre


# ---------------------------------------------------------------------------
# Audio: tono senoidal hacia aplay (misma salida ALSA PWM de siempre)
# ---------------------------------------------------------------------------

class Tono:
    def __init__(self):
        self.lock = threading.Lock()
        self.freq = FREQ_INICIAL
        self.volumen = VOLUMEN_INICIAL
        self.proc = None
        self.hilo = None
        self.buf = b""
        self.error = None

    def _tabla(self):
        # Con frecuencia entera, TASA/mcd(f, TASA) muestras contienen un numero
        # entero de periodos: la tabla se repite sin discontinuidad.
        n = TASA // math.gcd(self.freq, TASA)
        amp = 32767 * self.volumen / 100
        w = 2 * math.pi * self.freq / TASA
        tabla = array.array("h", (int(amp * math.sin(w * i)) for i in range(n)))
        repetir = max(1, 2400 // n)                    # bloques de ~50 ms
        return tabla.tobytes() * repetir

    def _escribir(self, proc):
        try:
            while True:
                with self.lock:
                    if self.proc is not proc:
                        break
                    buf = self.buf
                proc.stdin.write(buf)
        except (BrokenPipeError, ValueError, OSError) as e:
            with self.lock:
                if self.proc is proc:
                    self.error = f"aplay termino: {e}"
                    self.proc = None

    def encendido(self):
        return self.proc is not None

    def encender(self, freq=None):
        with self.lock:
            if freq is not None:
                self.freq = freq
            self.buf = self._tabla()
            if self.proc is not None:
                return
            self.error = None
            proc = subprocess.Popen(
                ["aplay", "-q", "-D", ALSA, "-t", "raw", "-f", "S16_LE",
                 "-c", "1", "-r", str(TASA), "-B", "100000", "-"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                # Tuberia chica: el cambio de frecuencia/volumen se escucha enseguida
                fcntl.fcntl(proc.stdin.fileno(), F_SETPIPE_SZ, 4096)
            except OSError:
                pass
            self.proc = proc
            self.hilo = threading.Thread(target=self._escribir, args=(proc,), daemon=True)
            self.hilo.start()

    def apagar(self):
        with self.lock:
            proc, self.proc = self.proc, None
        if proc:
            proc.terminate()
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.wait()

    def fijar_volumen(self, v):
        with self.lock:
            self.volumen = v
            self.buf = self._tabla()


# ---------------------------------------------------------------------------
# Estado del modo de video (driver legacy: vcgencmd)
# ---------------------------------------------------------------------------

NORMAS = {0: "NTSC", 1: "NTSC-J", 2: "PAL", 3: "PAL-M"}
LINEAS = {0: "525 lineas 480i 60 Hz", 1: "525 lineas 480i 60 Hz",
          2: "625 lineas 576i 50 Hz", 3: "525 lineas 480i 60 Hz"}
ASPECTOS = {1: "4:3", 2: "14:9", 3: "16:9"}


def vcgencmd(*args):
    try:
        r = subprocess.run(["vcgencmd", *args], capture_output=True, text=True, timeout=3)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def config_int(nombre):
    salida = vcgencmd("get_config", nombre)
    try:
        return int(salida.split("=", 1)[1], 0)
    except (IndexError, ValueError):
        return None


def modo_video():
    driver = "KMS (vc4)" if os.path.exists("/dev/dri") else "legacy (firmware)"
    modo = config_int("sdtv_mode")
    if modo is None:
        return f"driver {driver}, sin datos de vcgencmd"
    base, progresivo = modo & 0x0F, bool(modo & 0x10)
    norma = NORMAS.get(base, f"desconocida ({modo})")
    barrido = LINEAS.get(base, "?")
    if progresivo:
        barrido = barrido.replace("i ", "p ") + " (PROGRESIVO, no entrelazado)"
    aspecto = ASPECTOS.get(config_int("sdtv_aspect") or 1, "?")
    burst = "sin burst de color" if config_int("sdtv_disable_colourburst") == 1 \
        else "CON burst de color"
    return (f"compuesto {norma} {barrido}, {aspecto}, {burst}, "
            f"framebuffer {vcgencmd('get_lcd_info')}, driver {driver}")


# ---------------------------------------------------------------------------
# Comandos y servidor
# ---------------------------------------------------------------------------

class Servicio:
    def __init__(self, video, tono):
        self.video = video
        self.tono = tono

    def ejecutar(self, linea):
        partes = linea.split()
        if not partes:
            return "error: comando vacio"
        cmd, args = partes[0].lower(), [a.lower() for a in partes[1:]]
        if cmd == "pattern":
            return self.c_pattern(args)
        if cmd == "tone":
            return self.c_tone(args)
        if cmd == "volume":
            return self.c_volume(args)
        if cmd == "status":
            return self.c_status()
        return f"error: comando desconocido '{cmd}'"

    def c_pattern(self, args):
        if not args or args[0] == "list":
            return "\n".join(
                f"{'*' if n == self.video.actual else ' '} {n:<11} {desc}"
                for n, (desc, _) in PATRONES.items())
        if args[0] not in PATRONES:
            return f"error: patron desconocido '{args[0]}' (ver: tvtest pattern list)"
        self.video.mostrar(args[0])
        return f"patron: {args[0]}"

    def c_tone(self, args):
        if not args:
            return "error: uso tone <Hz>|on|off"
        if args[0] == "off":
            self.tono.apagar()
            return "tono: apagado"
        if args[0] == "on":
            self.tono.encender()
            return f"tono: {self.tono.freq} Hz"
        try:
            f = int(args[0])
        except ValueError:
            return f"error: frecuencia invalida '{args[0]}'"
        if not FREQ_MIN <= f <= FREQ_MAX:
            return f"error: frecuencia fuera de rango ({FREQ_MIN}-{FREQ_MAX} Hz)"
        self.tono.encender(f)
        return f"tono: {f} Hz"

    def c_volume(self, args):
        try:
            v = int(args[0])
        except (IndexError, ValueError):
            return "error: uso volume <0-100>"
        if not 0 <= v <= 100:
            return "error: volumen fuera de rango (0-100)"
        self.tono.fijar_volumen(v)
        return f"volumen: {v} %"

    def c_status(self):
        t = self.tono
        estado = f"encendido, {t.freq} Hz" if t.encendido() else f"apagado ({t.freq} Hz)"
        lineas = [f"patron:  {self.video.actual}",
                  f"tono:    {estado}",
                  f"volumen: {t.volumen} %",
                  f"video:   {modo_video()}"]
        if t.error:
            lineas.append(f"aviso:   {t.error}")
        return "\n".join(lineas)


def crear_servidor(servicio):
    class Manejador(socketserver.StreamRequestHandler):
        def handle(self):
            linea = self.rfile.readline().decode("utf-8", "replace").strip()
            try:
                resp = servicio.ejecutar(linea)
            except Exception as e:                     # el servicio no debe caerse
                resp = f"error: {e}"
            self.wfile.write((resp + "\n").encode())

    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    srv = socketserver.ThreadingUnixStreamServer(SOCKET, Manejador)
    srv.daemon_threads = True
    try:
        os.chown(SOCKET, 0, grp.getgrnam("pi").gr_gid)
        os.chmod(SOCKET, 0o660)
    except KeyError:
        os.chmod(SOCKET, 0o666)
    return srv


def main():
    video = Video()
    tono = Tono()
    servicio = Servicio(video, tono)
    video.tomar_consola()
    video.mostrar(PATRON_INICIAL)

    fin = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: fin.set())
    signal.signal(signal.SIGINT, lambda *_: fin.set())

    srv = crear_servidor(servicio)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"escuchando en {SOCKET}; {modo_video()}")

    try:
        # Reescritura periodica por si algo pisa el framebuffer
        while not fin.wait(REFRESCO_S):
            video.mostrar()
    finally:
        srv.shutdown()
        srv.server_close()
        if os.path.exists(SOCKET):
            os.unlink(SOCKET)
        tono.apagar()
        video.soltar_consola()
        log("detenido")


if __name__ == "__main__":
    sys.exit(main())
