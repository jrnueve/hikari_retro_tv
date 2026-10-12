"""Hikari Retro TV (Pi Zero W) - Catalogo, favoritos y estado persistente.

Clonado de hikaritv_comun.py del proyecto U100 (D:\\electronica\\hikari_tv),
sin el cliente del socket IPC de mpv: en la Pi no hay mpv, el reproductor es
un pipeline de ffmpeg que maneja hikaritvd. El formato de las categorias
(.m3u con atributos tvg-), de los favoritos y de los archivos de estado es el
mismo, asi que las listas del U100 se copian tal cual.

Se instala en /usr/local/lib/hikari-tv/.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

NL = "\n"

SEGUNDOS_POR_DEFECTO = 60
SEGUNDOS_MIN = 10
SEGUNDOS_MAX = 24 * 3600


def log(etiqueta: str, msg: str) -> None:
    print(f"[{etiqueta}] {msg}", flush=True)


def leer_conf(ruta: str) -> dict[str, str]:
    """Lee un archivo CLAVE=valor simple, al estilo de hikari-tv.conf."""
    conf: dict[str, str] = {}
    p = Path(ruta)
    if not p.is_file():
        return conf
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        conf[k.strip()] = v.strip().strip('"').strip("'")
    return conf


# ---------------------------------------------------------------------------
# Archivos de estado (~/.local/state/hikari-tv/)
# ---------------------------------------------------------------------------

def _estado(nombre: str) -> Path:
    base = os.environ.get("XDG_STATE_HOME",
                          os.path.expanduser("~/.local/state"))
    return Path(base) / "hikari-tv" / nombre


def leer_estado(nombre: str) -> str:
    try:
        return _estado(nombre).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def escribir_estado(nombre: str, valor: str) -> None:
    p = _estado(nombre)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(valor + NL, encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


# --- Modo TV al azar ---------------------------------------------------------

# Criterio -> etiqueta de la web. "no" es apagado.
AZAR = {"rnd": "RND", "pais": "PAIS", "categ": "CATEG"}


def azar_actual() -> str:
    m = leer_estado("azar")
    return m if m in AZAR else "no"


def fijar_azar(criterio: str) -> None:
    if criterio != "no" and criterio not in AZAR:
        raise ValueError(f"criterio desconocido: {criterio}")
    escribir_estado("azar", criterio)


def azar_segundos(por_defecto: int | str = "") -> int:
    for valor in (leer_estado("azar_segundos"), str(por_defecto)):
        try:
            n = int(valor)
        except ValueError:
            continue
        if SEGUNDOS_MIN <= n <= SEGUNDOS_MAX:
            return n
    return SEGUNDOS_POR_DEFECTO


def fijar_azar_segundos(n: int) -> None:
    if not SEGUNDOS_MIN <= n <= SEGUNDOS_MAX:
        raise ValueError(f"fuera de rango: {n}")
    escribir_estado("azar_segundos", str(n))


# ---------------------------------------------------------------------------
# Catalogo de categorias y canales
# ---------------------------------------------------------------------------

_RE_ATRIB = re.compile(r'([a-zA-Z-]+)="([^"]*)"')

FAVORITOS = "favoritos"


def _entradas_m3u(ruta: Path) -> list[tuple[str, str]]:
    """Pares (linea #EXTINF, URL) de un m3u, en orden."""
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    salida, extinf = [], None
    for linea in lineas:
        linea = linea.strip()
        if linea.startswith("#EXTINF"):
            extinf = linea
        elif linea and not linea.startswith("#"):
            if extinf:
                salida.append((extinf, linea))
            extinf = None
    return salida


class Catalogo:
    """Categorias como archivos .m3u en un directorio, mas los favoritos.

    La categoria vigente se guarda en un archivo de estado, para que al
    reiniciar el televisor siga donde estaba.

    Los favoritos son una categoria mas, "favoritos", que aparece al final
    cuando tiene al menos un canal (~/.local/state/hikari-tv/favoritos.m3u).
    """

    def __init__(self, dir_canales: str, categoria_inicial: str = ""):
        self.dir = Path(dir_canales)
        self.estado = _estado("categoria")
        self.inicial = categoria_inicial
        self.favoritos = self.estado.parent / f"{FAVORITOS}.m3u"
        # Lineas de los favoritos quitados: si se vuelve a marcar uno que no
        # esta en ninguna categoria, sus datos (pais, idioma, resolucion)
        # salen de aca.
        self.historial = self.favoritos.with_name(f"{FAVORITOS}-historial.m3u")

    def categorias(self) -> list[str]:
        cats = (sorted(p.stem for p in self.dir.glob("*.m3u"))
                if self.dir.is_dir() else [])
        if _entradas_m3u(self.favoritos):
            cats.append(FAVORITOS)
        return cats

    def actual(self) -> str | None:
        cats = self.categorias()
        if not cats:
            return None
        guardada = leer_estado("categoria")
        for c in (guardada, self.inicial):
            if c in cats:
                return c
        return cats[0]

    def fijar(self, categoria: str) -> None:
        escribir_estado("categoria", categoria)

    def ruta(self, categoria: str) -> Path:
        if categoria == FAVORITOS:
            return self.favoritos
        return self.dir / f"{categoria}.m3u"

    def canales(self, categoria: str) -> list[dict]:
        """Canales de una categoria, leidos del m3u.

        El m3u lleva los atributos tvg- que escribio el relevador del U100
        (pais, idioma, resolucion, codec), ya verificados con ffprobe.
        """
        salida: list[dict] = []
        for extinf, url in _entradas_m3u(self.ruta(categoria)):
            atrib = dict(_RE_ATRIB.findall(extinf))
            nombre = extinf.rpartition(",")[2].strip()
            salida.append({
                "pos": len(salida),
                "nombre": nombre or atrib.get("tvg-name", "?"),
                "pais": atrib.get("tvg-country", ""),
                # Separador ";": una coma dentro de un atributo rompe el
                # parseo del titulo del EXTINF.
                "idiomas": [i for i in
                            atrib.get("tvg-language", "").split(";") if i],
                "resolucion": atrib.get("resolution", ""),
                "categoria": categoria,
                "url": url,
            })
        return salida

    def todos(self) -> list[dict]:
        """Canales de todas las categorias (sin favoritos), para el azar."""
        salida: list[dict] = []
        for c in self.categorias():
            if c != FAVORITOS:
                salida += self.canales(c)
        return salida

    # --- Favoritos -----------------------------------------------------------

    def es_favorito(self, url: str) -> bool:
        return any(u == url for _, u in _entradas_m3u(self.favoritos))

    def _guardar_favoritos(self, entradas: list[tuple[str, str]]) -> None:
        lineas = ["#EXTM3U", "# Favoritos de Hikari Retro TV (los escribe la web app)"]
        for extinf, url in entradas:
            lineas += [extinf, url]
        self.favoritos.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.favoritos.with_suffix(".tmp")
        tmp.write_text(NL.join(lineas) + NL, encoding="utf-8")
        os.replace(tmp, self.favoritos)

    def agregar_favorito(self, url: str, titulo: str = "") -> bool:
        """Agrega un canal a favoritos. Falso si ya estaba.

        Se copia su linea #EXTINF de la categoria donde esta; si no esta en
        ninguna, la del historial; si tampoco, una linea minima.
        """
        entradas = _entradas_m3u(self.favoritos)
        if any(u == url for _, u in entradas):
            return False
        extinf = None
        archivos = sorted(self.dir.glob("*.m3u")) if self.dir.is_dir() else []
        for archivo in archivos + [self.historial]:
            extinf = next((e for e, u in _entradas_m3u(archivo) if u == url), None)
            if extinf:
                break
        if extinf:
            extinf = re.sub(r'group-title="[^"]*"', f'group-title="{FAVORITOS}"',
                            extinf)
        else:
            limpio = (titulo or url).replace('"', "").replace(",", ";")
            extinf = (f'#EXTINF:-1 tvg-name="{limpio}" '
                      f'group-title="{FAVORITOS}",{limpio}')
        self._guardar_favoritos(entradas + [(extinf, url)])
        return True

    def quitar_favorito(self, pos: int | None = None,
                        url: str | None = None) -> int | None:
        """Quita un favorito por posicion o por URL. Devuelve su posicion."""
        entradas = _entradas_m3u(self.favoritos)
        if pos is None:
            pos = next((i for i, (_, u) in enumerate(entradas) if u == url), None)
        if pos is None or not 0 <= pos < len(entradas):
            return None
        self._recordar(entradas[pos])
        del entradas[pos]
        self._guardar_favoritos(entradas)
        return pos

    def _recordar(self, entrada: tuple[str, str]) -> None:
        """Guarda la linea de un favorito quitado en el historial."""
        previas = [e for e in _entradas_m3u(self.historial) if e[1] != entrada[1]]
        lineas = ["#EXTM3U", "# Favoritos quitados: sus datos, por si se los"
                  " vuelve a marcar"]
        for extinf, url in previas + [entrada]:
            lineas += [extinf, url]
        try:
            tmp = self.historial.with_suffix(".tmp")
            tmp.write_text(NL.join(lineas) + NL, encoding="utf-8")
            os.replace(tmp, self.historial)
        except OSError:
            pass
