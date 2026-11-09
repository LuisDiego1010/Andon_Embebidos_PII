#!/bin/sh
# Levanta la estación completa en un contenedor de la PC, con sensores simulados y Ollama falso.
# Abrir http://127.0.0.1:5000/simulador. Ctrl+C la detiene y borra el contenedor.
# El repositorio se monta en solo lectura: no se modifica nada. Para el modelo real, usar la placa.
set -e
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
TTY=""; [ -t 0 ] && TTY="-it"     # sin terminal (lanzado desde otro proceso) corre igual
exec podman run --rm $TTY --name andon-simulador -p 127.0.0.1:5000:5000 -v "$RAIZ":/work:ro,Z \
    docker.io/library/python:3.12-slim bash -c '
set -e
echo "Instalando dependencias (solo la primera parte tarda)…"
sed -i "s#http://#https://#g" /etc/apt/sources.list.d/*.sources   # algunas redes bloquean el puerto 80
apt-get update -qq >/dev/null; apt-get install -y -qq mosquitto >/dev/null 2>&1
pip install -q --root-user-action=ignore flask paho-mqtt 2>&1 | grep -v notice || true
sed -e "s#^paro_ruta.*#paro_ruta = /tmp/paro.json#" -e "s#^db_ruta.*#db_ruta = /tmp/andon.db#" \
    -e "s#^url = .*#url = http://127.0.0.1:11500#" /work/app/config/andon.conf > /tmp/andon.conf
export ANDON_CONF=/tmp/andon.conf ANDON_MODO=sim PYTHONPATH=/work/app/src PYTHONDONTWRITEBYTECODE=1
mosquitto -d -p 1883 >/dev/null 2>&1; sleep 1
python /work/app/tools/fake_ollama.py --puerto 11500 --latencia-s 1 >/tmp/ollama.log 2>&1 &
python -m andon.sensores & python -m andon.core & python -m andon.web &
sleep 2; echo; echo ">>> Abrí http://127.0.0.1:5000/simulador (PIN 1234)"; echo
wait'
