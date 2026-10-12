#!/bin/bash
# Instala tvtest en la Pi: respalda y ajusta config.txt / cmdline.txt e
# instala el servicio tvtestd. Uso: sudo ./install.sh  (reiniciar despues)
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "error: ejecutar con sudo" >&2; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
BOOT=/boot/firmware
CFG="$BOOT/config.txt"
CMD="$BOOT/cmdline.txt"

if grep -q 'systemd\.run=' "$CMD"; then
    echo "error: $CMD todavia tiene systemd.run=, no se modifica" >&2
    exit 1
fi

# Respaldos: solo la primera vez, para conservar siempre el original
for f in "$CFG" "$CMD"; do
    if [ ! -e "$f.bak-tvtest" ]; then
        cp -p "$f" "$f.bak-tvtest"
        echo "respaldo: $f.bak-tvtest"
    fi
done

# config.txt: sin subportadora de color (TV monocromo)
if ! grep -q '^sdtv_disable_colourburst=1' "$CFG"; then
    printf '\n# tvtest: TV blanco y negro, sin subportadora de color\n[all]\nsdtv_disable_colourburst=1\n' >> "$CFG"
    echo "config.txt: agregado sdtv_disable_colourburst=1"
fi
grep -q '^sdtv_mode=2' "$CFG"   || echo "AVISO: falta sdtv_mode=2 (PAL) en $CFG"
grep -q '^sdtv_aspect=1' "$CFG" || echo "AVISO: falta sdtv_aspect=1 (4:3) en $CFG"
grep -q '^enable_tvout=1' "$CFG" || echo "AVISO: falta enable_tvout=1 en $CFG"

# cmdline.txt: una sola linea; sin cursor, sin texto del kernel, sin blanqueo
for p in consoleblank=0 vt.global_cursor_default=0 loglevel=3 quiet logo.nologo; do
    if ! grep -qw -- "$p" "$CMD"; then
        sed -i "1 s/\$/ $p/" "$CMD"
        echo "cmdline.txt: agregado $p"
    fi
done

install -D -m 755 "$DIR/tvtestd.py" /opt/tvtest/tvtestd.py
install -m 755 "$DIR/tvtest" /usr/local/bin/tvtest
install -m 644 "$DIR/tvtestd.service" /etc/systemd/system/tvtestd.service
systemctl daemon-reload
systemctl enable tvtestd
echo "instalado. Reiniciar para aplicar config.txt/cmdline.txt: sudo reboot"
