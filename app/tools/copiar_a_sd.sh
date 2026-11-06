#!/usr/bin/env bash
# Copia la app (código, configuración y herramientas de prueba) a la tarjeta SD de la
# Raspberry Pi con la imagen Yocto, SIN regrabar la imagen. Se corre en la PC, con la
# tarjeta conectada y montada (el escritorio la monta en /run/media/$USER/root).
#
#   app/tools/copiar_a_sd.sh                 # usa /run/media/$USER/root
#   app/tools/copiar_a_sd.sh /ruta/a/root    # otro punto de montaje
#
# Pide sudo (la partición root de la imagen es de root). Antes de copiar comprueba que
# el destino es una imagen Yocto con la app instalada, para no escribir en otro disco.
# Al terminar sincroniza y desmonta la tarjeta.
set -euo pipefail

RAIZ_REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-/run/media/${USER}/root}"

[ -d "$DEST" ] || { echo "No existe $DEST: ¿está montada la tarjeta?"; exit 1; }
grep -q 'ID=poky' "$DEST/usr/lib/os-release" 2>/dev/null \
    || { echo "$DEST no parece una imagen Yocto (Poky). No se copia nada."; exit 1; }
[ -d "$DEST/opt/andon/andon" ] \
    || { echo "$DEST no tiene /opt/andon/andon (¿falta la receta andon-app?). No se copia nada."; exit 1; }
[ "$(findmnt -no TARGET -T "$DEST")" != "/" ] \
    || { echo "$DEST está en el disco del sistema, no en la tarjeta. No se copia nada."; exit 1; }

echo ">> Destino: $DEST ($(. "$DEST/usr/lib/os-release"; echo "$PRETTY_NAME"))"
echo ">> Copiando código a /opt/andon/andon ..."
sudo rm -rf "$DEST/opt/andon/andon"
tar -C "$RAIZ_REPO/app/src" --exclude='__pycache__' -cf - andon \
    | sudo tar -C "$DEST/opt/andon" --no-same-owner -xf -

echo ">> Configuración en /etc/andon/andon.conf ..."
sudo install -D -m 0644 "$RAIZ_REPO/app/config/andon.conf" "$DEST/etc/andon/andon.conf"

echo ">> Herramientas de prueba en /opt/andon ..."
sudo install -m 0755 "$RAIZ_REPO/app/tools/probar_hal.py" \
    "$RAIZ_REPO/app/tools/probar_calentamiento.py" "$DEST/opt/andon/"
sudo install -D -m 0644 "$RAIZ_REPO/app/tests/contract/reportes.json" "$DEST/opt/andon/pruebas/reportes.json"

echo ">> Sincronizando y desmontando ..."
sync
BOOT="$(dirname "$DEST")/boot"
umount "$BOOT" 2>/dev/null || true
if umount "$DEST" 2>/dev/null; then
    echo ">> Listo. Ya se puede sacar la tarjeta y ponerla en la Raspberry Pi."
else
    echo ">> Copiado y sincronizado. Expulse la tarjeta desde el escritorio antes de sacarla."
fi
