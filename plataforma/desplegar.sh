#!/bin/bash
# Despliega Hikari Retro TV en la Pi desde la PC (Git Bash). Uso:
#   plataforma/desplegar.sh [usuario@host]
# Copia plataforma/ a /tmp de la Pi e instala con sudo (sin clave en la Pi).
# Reinicia hikaritvd: el TV vuelve a sintonizar el canal en el que estaba.
set -euo pipefail
DESTINO="${1:-pi@192.168.1.40}"
DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTO=/tmp/hikari-tv

ssh "$DESTINO" "rm -rf $REMOTO && mkdir -p $REMOTO/canales"
scp -q "$DIR"/{hikaritvd.py,hikaritv_comun.py,hikaritv-canal.sh,fbgray.c,logo.png,hikari-tv.conf,hikaritvd.service,instalar.sh} "$DESTINO:$REMOTO/"
scp -q "$DIR"/canales/*.m3u "$DESTINO:$REMOTO/canales/"
ssh "$DESTINO" "sudo bash $REMOTO/instalar.sh"
