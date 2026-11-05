#!/usr/bin/env bash
# Descarga el modelo tev1:0.8b y lo empaqueta para meter dentro de la imagen.
#
# Se corre UNA vez en la máquina de desarrollo (Ubuntu x86_64), antes de compilar.
# No instala nada en el sistema: usa una copia temporal de Ollama en .cache/.
# Los archivos del modelo (GGUF + manifiesto) no dependen de la arquitectura,
# así que lo que se descarga en la PC sirve tal cual en la Raspberry Pi.
#
# Uso:  ./scripts/empacar-modelo.sh
set -euo pipefail

OLLAMA_VERSION="0.40.13"   # misma versión que la receta ollama-bin
MODELO="tev1:0.8b"
PUERTO="11555"             # puerto temporal, para no chocar con otro Ollama

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$RAIZ/.cache/empacar-modelo"
SALIDA="$RAIZ/meta-andon/recipes-ai/ollama/files/tev1-0.8b-models.tar.gz"
OLLAMA_DIR="$CACHE/ollama-$OLLAMA_VERSION"
MODELOS="$CACHE/models"

command -v zstd >/dev/null || { echo "Falta zstd: sudo apt install zstd"; exit 1; }
mkdir -p "$CACHE"

# 1. Ollama para la PC (solo binario + backend de CPU, sin CUDA)
if [ ! -x "$OLLAMA_DIR/bin/ollama" ]; then
    echo ">> Descargando Ollama $OLLAMA_VERSION para x86_64..."
    mkdir -p "$OLLAMA_DIR"
    curl -fL "https://github.com/ollama/ollama/releases/download/v$OLLAMA_VERSION/ollama-linux-amd64.tar.zst" \
        | zstd -dc \
        | tar -x -C "$OLLAMA_DIR" --exclude='lib/ollama/cuda_*' --exclude='lib/ollama/vulkan*'
fi

# 2. Levantar un Ollama temporal que guarde los modelos en $MODELOS
rm -rf "$MODELOS"; mkdir -p "$MODELOS"
echo ">> Iniciando Ollama temporal en el puerto $PUERTO..."
OLLAMA_MODELS="$MODELOS" OLLAMA_HOST="127.0.0.1:$PUERTO" \
    "$OLLAMA_DIR/bin/ollama" serve >"$CACHE/ollama.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
    curl -sf "http://127.0.0.1:$PUERTO/api/version" >/dev/null && break
    sleep 1
done

# 3. Descargar el modelo
echo ">> Descargando $MODELO..."
OLLAMA_HOST="127.0.0.1:$PUERTO" "$OLLAMA_DIR/bin/ollama" pull "$MODELO"
OLLAMA_HOST="127.0.0.1:$PUERTO" "$OLLAMA_DIR/bin/ollama" list

kill $PID; wait $PID 2>/dev/null || true; trap - EXIT

# 4. Empaquetar: el .tar.gz contiene la carpeta models/ (blobs + manifests)
echo ">> Empaquetando en $SALIDA"
tar -czf "$SALIDA" -C "$CACHE" models
ls -lh "$SALIDA"
echo ">> Listo. Ya se puede compilar la imagen."
