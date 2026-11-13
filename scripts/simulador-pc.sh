#!/bin/sh
# Levanta la estación completa en un contenedor de la PC, con sensores simulados.
# Abrir http://127.0.0.1:5000/simulador. Ctrl+C la detiene y borra el contenedor.
# El repositorio se monta en solo lectura: no se modifica nada.
#
#   ./scripts/simulador-pc.sh                  Ollama falso (determinista, 1 s por reporte)
#   ./scripts/simulador-pc.sh --ollama-real    Ollama real del compose (tev1:0.8b en el puerto 11434)
#   ./scripts/simulador-pc.sh --lan            además, accesible desde otros equipos (p. ej. un celular)
#
# Usa podman si está instalado; si no, docker. Para --ollama-real, levantar antes el Ollama:
#   docker compose -f docker/compose.yaml up -d --no-deps ollama
set -e
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
OLLAMA_REAL=0
DIRECCION=127.0.0.1
for opcion in "$@"; do
    case "$opcion" in
        --ollama-real) OLLAMA_REAL=1 ;;
        --lan) DIRECCION=0.0.0.0 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) echo "opción desconocida: $opcion (ver --help)" >&2; exit 2 ;;
    esac
done

if command -v podman >/dev/null 2>&1; then
    MOTOR=podman; VOLUMEN="$RAIZ:/work:ro,Z"; ANFITRION=host.containers.internal; EXTRA=""
elif command -v docker >/dev/null 2>&1; then
    MOTOR=docker; VOLUMEN="$RAIZ:/work:ro"; ANFITRION=host.docker.internal
    EXTRA="--add-host=host.docker.internal:host-gateway"   # el Ollama del compose, visto desde el contenedor
else
    echo "Hace falta podman o docker." >&2; exit 1
fi

if [ "$OLLAMA_REAL" = 1 ]; then
    OLLAMA_URL="http://$ANFITRION:11434"
    # Recién levantado, Ollama tarda unos segundos en abrir el puerto: se espera hasta 30 s.
    for _ in $(seq 30); do
        curl -fsS -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
        [ "$_" = 1 ] && echo "Esperando a que Ollama responda en 127.0.0.1:11434…"
        sleep 1
    done
    if ! curl -fsS -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "No responde el Ollama en 127.0.0.1:11434. Levántelo con:" >&2
        echo "  docker compose -f docker/compose.yaml up -d --no-deps ollama" >&2
        exit 1
    fi
else
    OLLAMA_URL="http://127.0.0.1:11500"
fi

if [ "$DIRECCION" = 0.0.0.0 ]; then
    IP_LAN=$(hostname -I 2>/dev/null | awk '{print $1}')
    AVISO="Desde otro equipo de la misma red: http://${IP_LAN:-<IP de esta PC>}:5000"
else
    AVISO="Solo desde esta PC (use --lan para abrirlo desde un celular)"
fi

TTY=""; [ -t 0 ] && TTY="-it"     # sin terminal (lanzado desde otro proceso) corre igual
# shellcheck disable=SC2086
exec $MOTOR run --rm $TTY $EXTRA --name andon-simulador -p "$DIRECCION:5000:5000" -v "$VOLUMEN" \
    -e OLLAMA_REAL="$OLLAMA_REAL" -e OLLAMA_URL="$OLLAMA_URL" -e AVISO="$AVISO" \
    docker.io/library/python:3.12-slim bash -c '
set -e
echo "Instalando dependencias (solo la primera parte tarda)…"
sed -i "s#http://#https://#g" /etc/apt/sources.list.d/*.sources   # algunas redes bloquean el puerto 80
apt-get update -qq >/dev/null; apt-get install -y -qq mosquitto >/dev/null 2>&1
pip install -q --root-user-action=ignore flask paho-mqtt 2>&1 | grep -v notice || true
sed -e "s#^paro_ruta.*#paro_ruta = /tmp/paro.json#" -e "s#^db_ruta.*#db_ruta = /tmp/andon.db#" \
    -e "s#^url = .*#url = $OLLAMA_URL#" /work/app/config/andon.conf > /tmp/andon.conf
export ANDON_CONF=/tmp/andon.conf ANDON_MODO=sim PYTHONPATH=/work/app/src PYTHONDONTWRITEBYTECODE=1
mosquitto -d -p 1883 >/dev/null 2>&1; sleep 1
if [ "$OLLAMA_REAL" = 1 ]; then
    echo "Ollama real: $OLLAMA_URL (el primer reporte espera a que cargue el modelo)"
else
    python /work/app/tools/fake_ollama.py --puerto 11500 --latencia-s 1 >/tmp/ollama.log 2>&1 &
fi
python -m andon.sensores & python -m andon.core & python -m andon.web &
sleep 2; echo; echo ">>> Abra http://127.0.0.1:5000/simulador (PIN 1234)"; echo ">>> $AVISO"; echo
wait'
