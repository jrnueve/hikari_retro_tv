r"""Arma las categorias de la Pi a partir de relevamiento_sd.json.

Solo entran los canales con una variante que la Pi mueve (ver relevar_sd.py);
sus datos (pais, idiomas, categorias de iptv-org) salen del catalogo del U100
(D:\electronica\hikari_tv\iptv\catalogo.json). Un canal puede estar en varias
categorias. La URL es la original (lista maestra): hikaritvd elige la
variante SD al sintonizar, asi no se guardan URL de variantes que vencen.

pruebas.m3u se escribe a mano y no se toca.

Uso: python armar_canales.py
"""

import json
from pathlib import Path

AQUI = Path(__file__).parent
CATALOGO = Path(r"D:\electronica\hikari_tv\iptv\catalogo.json")
DESTINO = AQUI / "canales"

# Categoria de iptv-org -> categoria de Hikari Retro TV
TEMAS = {
    "general": "general",
    "news": "noticias", "business": "noticias",
    "movies": "peliculas", "series": "peliculas", "classic": "peliculas",
    "comedy": "peliculas",
    "music": "musica",
    "kids": "infantiles", "family": "infantiles", "animation": "infantiles",
    "documentary": "documentales", "culture": "documentales",
    "education": "documentales", "outdoor": "documentales",
    "entertainment": "entretenimiento", "lifestyle": "entretenimiento",
    "cooking": "entretenimiento", "auto": "entretenimiento",
    "shop": "entretenimiento", "sports": "deportes",
    "religious": "religion",
}


def extinf(c: dict, r: dict, grupo: str) -> str:
    def limpio(s: str) -> str:
        # Una coma o comilla dentro de un atributo rompe el #EXTINF
        return (s or "").replace('"', "").replace(",", ";").strip()
    nombre = limpio(c["nombre"])
    return (f'#EXTINF:-1 tvg-id="{limpio(c.get("id"))}" tvg-name="{nombre}" '
            f'tvg-country="{limpio(c.get("pais"))}" '
            f'tvg-language="{";".join(c.get("idiomas") or [])}" '
            f'group-title="{grupo}" resolution="{r["ancho"]}x{r["alto"]}" '
            f'codec="h264",{nombre}')


def main() -> None:
    catalogo = {c["url_original"]: c
                for c in json.loads(CATALOGO.read_text(encoding="utf-8"))}
    aptos = [r for r in json.loads((AQUI / "relevamiento_sd.json")
                                   .read_text(encoding="utf-8")) if r["apto"]]
    grupos: dict[str, list[tuple[dict, dict]]] = {}
    for r in aptos:
        c = catalogo[r["url_original"]]
        destinos = {TEMAS.get(k, "general") for k in c.get("categorias") or []}
        destinos = destinos or {"general"}
        if "spa" in (c.get("idiomas") or []):
            destinos.add("espanol")
        if c.get("pais") == "AR":
            destinos.add("argentina")
        for g in destinos:
            grupos.setdefault(g, []).append((c, r))

    DESTINO.mkdir(exist_ok=True)
    for viejo in DESTINO.glob("*.m3u"):
        if viejo.name != "pruebas.m3u":
            viejo.unlink()
    for g, canales in sorted(grupos.items()):
        canales.sort(key=lambda cr: (cr[0].get("pais") or "~",
                                     cr[0]["nombre"].lower()))
        lineas = ["#EXTM3U",
                  f"# Categoria: {g}  |  hasta 720x576 pixeles  |  "
                  "de relevamiento_sd.json"]
        for c, r in canales:
            lineas += [extinf(c, r, g), r["url_original"]]
        (DESTINO / f"{g}.m3u").write_text("\n".join(lineas) + "\n",
                                          encoding="utf-8")
        print(f"{g:16} {len(canales):4}")


if __name__ == "__main__":
    main()
