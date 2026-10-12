#!/bin/bash
# Instala Hikari Retro TV en la Pi. Lo corre desplegar.sh (desde la PC) con sudo,
# sobre una copia de plataforma/ en /tmp. Idempotente.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "error: ejecutar con sudo" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
LIB=/usr/local/lib/hikari-tv
CONF=/etc/hikari-tv/hikari-tv.conf
USUARIO=pi
CASA=/home/$USUARIO

# Dependencias: ffmpeg y mbuffer ya estan (canal.sh); PIL dibuja las cartas
for paquete in ffmpeg mbuffer python3-pil fonts-dejavu-core gcc; do
    dpkg -s "$paquete" >/dev/null 2>&1 || faltan="${faltan:-} $paquete"
done
if [ -n "${faltan:-}" ]; then
    echo "instalando:$faltan"
    apt-get install -y $faltan
fi

install -d "$LIB"
install -m 644 "$DIR/hikaritv_comun.py" "$DIR/logo.png" "$LIB/"
install -m 755 "$DIR/hikaritv-canal.sh" "$LIB/hikaritv-canal"
install -m 755 "$DIR/hikaritvd.py" /usr/local/bin/hikaritvd
gcc -O2 -o "$LIB/fbgray" "$DIR/fbgray.c"

# Configuracion: la del equipo manda; solo se agregan claves nuevas
install -d /etc/hikari-tv
if [ ! -f "$CONF" ]; then
    install -m 644 "$DIR/hikari-tv.conf" "$CONF"
else
    grep -E '^[A-Z_]+=' "$DIR/hikari-tv.conf" | while IFS= read -r linea; do
        clave="${linea%%=*}"
        grep -q "^$clave=" "$CONF" || { echo "$linea" >> "$CONF"; echo "conf: agregada $clave"; }
    done
fi

# Categorias: las del repo reemplazan a las del equipo (los favoritos viven
# aparte, en ~/.local/state/hikari-tv/, y no se tocan)
CANALES="$(grep '^DIR_CANALES=' "$CONF" | cut -d= -f2-)"
install -d -o "$USUARIO" -g "$USUARIO" "$CANALES"
rm -f "$CANALES"/*.m3u
install -m 644 -o "$USUARIO" -g "$USUARIO" "$DIR"/canales/*.m3u "$CANALES/"
chown -R "$USUARIO:$USUARIO" "$CASA/.local"

# Fuera de servicio lo que escribe en el framebuffer: canal.sh a mano (su
# salida vuelve a arrancar tvtestd) y tvtestd, que queda instalado pero no
# arranca en el boot.
if pgrep -f stream/canal.sh >/dev/null; then
    pkill -f stream/canal.sh || true
    pkill -x ffmpeg || true
    pkill -x mbuffer || true
    pkill -x fbgray || true
    sleep 2
fi
systemctl disable --now tvtestd 2>/dev/null || true

install -m 644 "$DIR/hikaritvd.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable hikaritvd
systemctl restart hikaritvd
echo "hikaritvd: $(systemctl is-active hikaritvd)"
