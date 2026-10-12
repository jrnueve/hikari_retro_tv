#!/bin/bash
# Desinstala tvtest y restaura config.txt / cmdline.txt originales.
# Uso: sudo ./uninstall.sh  (reiniciar despues)
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "error: ejecutar con sudo" >&2; exit 1; }
BOOT=/boot/firmware

systemctl disable --now tvtestd 2>/dev/null || true
rm -f /etc/systemd/system/tvtestd.service /usr/local/bin/tvtest
rm -rf /opt/tvtest
systemctl daemon-reload

for f in "$BOOT/config.txt" "$BOOT/cmdline.txt"; do
    if [ -e "$f.bak-tvtest" ]; then
        cp -p "$f.bak-tvtest" "$f"
        echo "restaurado: $f"
    fi
done
echo "desinstalado. Reiniciar para aplicar: sudo reboot"
