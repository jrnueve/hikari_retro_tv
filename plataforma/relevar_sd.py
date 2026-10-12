r"""Releva que canales del catalogo del U100 tienen una variante que la Pi
Zero puede mover: hasta 720x576 pixeles por cuadro y al menos 360 lineas.

fbgray adapta cualquier tamano a la pantalla sin costo, pero decodificar y
pasar por la tuberia cuadros mas grandes satura la Pi (medido: 720x576 70 %,
640x360 64 %, 1024x576 y 1280x720 100 %). Debajo de 360 lineas la imagen
queda muy pobre en el TV. El resto se sacrifica. Corre en la PC.

Para cada canal H.264 apto del catalogo (D:\electronica\hikari_tv\iptv\
catalogo.json) baja su lista original:
  - maestra: busca la variante apta mas grande segun RESOLUTION (que a
    veces miente: hikaritvd usa el tamano real que informa ffmpeg). Si el audio
    va en una lista aparte, no sirve (la Pi reproduce la maestra entera).
  - simple: vale el ancho/alto que el U100 ya midio con ffprobe.

Salida: relevamiento_sd.json (un registro por canal, apto o no) junto a
este script. Uso: python relevar_sd.py [--hilos 20]
"""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

CATALOGO = Path(r"D:\electronica\hikari_tv\iptv\catalogo.json")
SALIDA = Path(__file__).parent / "relevamiento_sd.json"
PIXELES_MAX = 720 * 576
ALTO_MIN = 360


def cabe(ancho, alto) -> bool:
    return bool(ancho and alto) and ancho * alto <= PIXELES_MAX and alto >= ALTO_MIN
_SIN_VERIFICAR = ssl._create_unverified_context()
_RE_RES = re.compile(r"RESOLUTION=(\d+)x(\d+)")
_RE_BW = re.compile(r"[^-]BANDWIDTH=(\d+)")


def relevar(canal: dict) -> dict:
    r = {"id": canal.get("id"), "nombre": canal["nombre"],
         "url_original": canal["url_original"], "apto": False}
    url = canal["url_original"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10,
                                    context=_SIN_VERIFICAR) as resp:
            base = resp.geturl()
            texto = resp.read(300_000).decode("utf-8", "replace")
    except Exception as e:                                # noqa: BLE001
        r["motivo"] = f"no responde ({type(e).__name__})"
        return r
    if "#EXT-X-STREAM-INF" not in texto:
        if cabe(canal.get("ancho"), canal.get("alto")):
            r.update(apto=True, ancho=720, alto=canal["alto"], tipo="simple")
        else:
            r.update(motivo=f"simple {canal.get('ancho')}x{canal.get('alto')}")
        return r
    if re.search(r"#EXT-X-MEDIA:[^\n]*TYPE=AUDIO[^\n]*URI=", texto):
        r["motivo"] = "maestra con audio aparte"
        return r
    variantes, inf = [], None
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("#EXT-X-STREAM-INF"):
            inf = linea
        elif linea and not linea.startswith("#") and inf:
            m, bw = _RE_RES.search(inf), _RE_BW.search(inf)
            if m:
                variantes.append((int(m.group(1)), int(m.group(2)),
                                  int(bw.group(1)) if bw else 0,
                                  urllib.parse.urljoin(base, linea)))
            inf = None
    r["variantes"] = sorted({f"{a}x{b}" for a, b, _, _ in variantes})
    aptas = [v for v in variantes if cabe(v[0], v[1])]
    if not aptas:
        r["motivo"] = "maestra sin variante apta"
        return r
    ancho, alto, bw, _ = max(aptas, key=lambda v: (v[0] * v[1], -v[2]))
    r.update(apto=True, ancho=ancho, alto=alto, kbps=bw // 1000, tipo="maestra")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hilos", type=int, default=20)
    args = ap.parse_args()
    canales = [c for c in json.loads(CATALOGO.read_text(encoding="utf-8"))
               if c.get("ok") and c.get("codec") == "h264"]
    print(f"{len(canales)} canales H.264 a relevar", file=sys.stderr)
    salida = []
    with ThreadPoolExecutor(args.hilos) as ex:
        futuros = [ex.submit(relevar, c) for c in canales]
        for i, f in enumerate(as_completed(futuros), 1):
            salida.append(f.result())
            if i % 500 == 0:
                print(f"  {i}/{len(canales)}", file=sys.stderr)
    salida.sort(key=lambda r: r["url_original"])
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    aptos = [r for r in salida if r["apto"]]
    print(f"aptos: {len(aptos)} de {len(salida)}")
    tamanos: dict[str, int] = {}
    for r in aptos:
        k = f"{r['ancho']}x{r['alto']}"
        tamanos[k] = tamanos.get(k, 0) + 1
    print("  " + ", ".join(f"{k}: {n}" for k, n in
                           sorted(tamanos.items(), key=lambda x: -x[1])[:10]))
    motivos: dict[str, int] = {}
    for r in salida:
        if not r["apto"]:
            m = r["motivo"].split(" (")[0] if r["motivo"].startswith("no") else (
                r["motivo"] if not r["motivo"].startswith("simple") else "simple no SD")
            motivos[m] = motivos.get(m, 0) + 1
    for m, n in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f"  {n:5}  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
