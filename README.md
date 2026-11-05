# Andon_Embebidos_PII

This project is an edge AI system for industrial monitoring: a smart Andon station that runs Ollama and the tev1:0.8b decision model (JEV API) on a Raspberry Pi 4 with a custom Yocto Linux image. EL5841 · ITCR.

**Estación Andon Inteligente de Borde.** Un nodo junto a una máquina une lo que miden los
sensores con lo que escribe el operario, clasifica la falla con un modelo de decisión local
(Ollama + API JEV, `/v1/systemone`) y señaliza, escala o detiene la máquina, sin Internet.

Equipo: Eduardo Tencio (director · auditor de calidad, app) y Luis Diego García Rojas
(líder técnico · investigador, imagen Yocto). Prof. Dr. Ing. Johan Carvajal Godínez.

| Pieza | Versión |
| --- | --- |
| Placa | Raspberry Pi 4 (aarch64), `MACHINE = raspberrypi4-64` |
| Yocto Project | 5.0 **scarthgap** (LTS), Python 3.12 |
| Ollama | 0.40.13 (binario oficial arm64, solo CPU) |
| Modelo | `tev1:0.8b`, precargado en la imagen |

## Estructura

```
andon.yml              Configuración de kas: capas, versiones fijas y local.conf
meta-andon/            Capa Yocto propia
  recipes-core/images/andon-image.bb      La imagen completa
  recipes-ai/ollama/                      Ollama, el modelo y su servicio systemd
  recipes-andon/andon-app/                La app (toma el código de app/)
app/                   Aplicación en Python (andon-sensores, andon-core, andon-web)
docker/                Entorno de desarrollo de la app (Ollama + Mosquitto + Python 3.12)
scripts/
  empacar-modelo.sh    Descarga tev1:0.8b y lo empaqueta para la imagen
  verificar-imagen.sh  En la Pi: comprueba que la imagen cumple lo que pide la app
  medir-latencia.py    En la Pi: latencia y exactitud del modelo (REQ-N05)
  probar-ollama.sh     En la Pi: consulta JEV de prueba
docs/
  plan.md                      Plan por fases de la app
  yocto-requisitos.md          Lo que la app necesita de la imagen
  yocto-respuestas.md          Cómo lo resuelve la imagen
  pruebas-placa.md             Guía de pruebas en la Raspberry Pi
  decisiones/                  Registro de decisiones (D1–D10)
  evidencias/                  Resultados de pruebas
```

## Generar la imagen

### Requisitos de la PC

- Linux x86_64 (probado en Ubuntu 26.04). Ruta del repo **sin espacios ni tildes**.
- 4+ núcleos, 8–16 GB de RAM, **~150 GB libres**.
- `git`, `curl`, `zstd`, `bmap-tools`, `podman` y `kas` (incluye `kas-container`):

```bash
sudo apt install -y git curl zstd bmap-tools podman kas
```

Se compila **dentro de un contenedor** (`kas-container`), así que la versión de Ubuntu
de la PC no afecta a Yocto.

### Pasos

```bash
git clone https://github.com/<usuario>/Andon_Embebidos_PII.git
cd Andon_Embebidos_PII

# 1. Modelo (una sola vez, ~1 GB; no se sube a git)
./scripts/empacar-modelo.sh

# 2. Compilar (la primera vez tarda horas; después, minutos)
KAS_CONTAINER_ENGINE=podman kas-container build andon.yml 2>&1 | tee compilacion.log
```

Resultado:
`build/tmp/deploy/images/raspberrypi4-64/andon-image-raspberrypi4-64.rootfs.wic.bz2`

### Grabar la microSD

```bash
lsblk                                   # identificar la tarjeta (¡no el disco del sistema!)
sudo umount /dev/sdX*
cd build/tmp/deploy/images/raspberrypi4-64/
sudo bmaptool copy andon-image-raspberrypi4-64.rootfs.wic.bz2 /dev/sdX
```

### Primer arranque

- Cable de red a un router, o a la laptop con la conexión en "Compartida con otros equipos".
- `ssh root@raspberrypi4-64.local` (sin contraseña: `debug-tweaks`, solo desarrollo).
- Pruebas de la imagen: ver [`docs/pruebas-placa.md`](docs/pruebas-placa.md).

## Desarrollo de la app

Ver [`docs/plan.md`](docs/plan.md) y [`docs/entorno.md`](docs/entorno.md).

```bash
docker compose -f docker/compose.yaml up -d --build
docker compose -f docker/compose.yaml exec dev pytest app/tests
```

## Decisiones de diseño de la imagen

- **Ollama precompilado.** No existe capa oficial de Ollama para Yocto; se empaqueta el
  binario oficial y se descartan las bibliotecas CUDA (~2,2 GB) que la Pi no usa.
- **Modelo dentro de la imagen.** La estación funciona sin Internet desde el primer
  arranque (REQ-N03).
- **Ollama solo en `127.0.0.1`.** Solo `andon-core` lo consulta.
- **App desde el mismo repo.** La receta `andon-app` toma `app/` con `externalsrc` y usa
  `make install DESTDIR=...` cuando la app lo provee.
