#!/bin/sh
# Cambia la estación entre sensores simulados y reales. Correr como root en la placa.
#   sh /opt/andon/modo.sh sim      activa el panel http://<placa>:5000/simulador
#   sh /opt/andon/modo.sh real     vuelve al hardware real
# Reinicia servicios y borra el paro retenido guardado.
set -e
case "$1" in sim|real) ;; *) echo "uso: $0 sim|real" >&2; exit 2 ;; esac

for s in andon-sensores andon-web; do
    d=/etc/systemd/system/$s.service.d
    if [ "$1" = sim ]; then
        mkdir -p "$d"
        printf '[Service]\nEnvironment=ANDON_MODO=sim\n' > "$d/sim.conf"
    else
        rm -f "$d/sim.conf"
    fi
done

paro=$(sed -n 's/^paro_ruta *= *//p' /etc/andon/andon.conf)
systemctl daemon-reload
systemctl stop andon-sensores
rm -f "${paro:-/var/lib/andon/paro.json}"
mosquitto_pub -h 127.0.0.1 -r -n -t andon/e1/sim/ajustar   # controles del panel a valores normales
systemctl start andon-sensores
systemctl restart andon-core andon-web
echo "Modo $1 activo."
