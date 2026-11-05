# Estación Andon Inteligente de Borde · Imagen Yocto

Imagen de Linux para **Raspberry Pi 4 (64 bits)** con Ollama y el modelo de decisión
`tev1:0.8b` incluidos, lista para la Estación Andon (EL5841, II Proyecto EdgeAI).

| Pieza | Versión |
| --- | --- |
| Yocto Project | 5.0 **scarthgap** (LTS) |
| Máquina | `raspberrypi4-64` |
| Ollama | 0.40.13 (binario oficial arm64, solo CPU) |
| Modelo | `tev1:0.8b` precargado en `/var/lib/ollama/models` |

## Qué hay en este repositorio

```
andon.yml                  Configuración de kas: capas, versiones y local.conf
meta-andon/                Nuestra capa
  conf/layer.conf
  recipes-core/images/
    andon-image.bb         La imagen: core-image-base + todo lo de la estación
  recipes-ai/ollama/
    ollama-bin_0.40.13.bb  Ollama empaquetado desde el binario oficial
    ollama-model-tev1_0.8b.bb  El modelo copiado dentro de la imagen
    ollama-user.inc        Usuario de sistema "ollama"
    files/ollama.service   Servicio systemd (arranca solo, escucha en localhost)
scripts/
  empacar-modelo.sh        Descarga tev1:0.8b en la PC y lo empaqueta (paso 3)
  probar-ollama.sh         Prueba de salida de E3, se corre en la Pi
```

**kas** es una herramienta que descarga las capas de Yocto en las versiones exactas
de `andon.yml` y genera `local.conf` y `bblayers.conf`. Así los dos integrantes
compilan exactamente lo mismo.

## Requisitos de la máquina de desarrollo

- Ubuntu 22.04 o 24.04
- 4 o más núcleos, 16 GB de RAM (8 GB funciona, pero lento)
- **120 GB libres** en disco
- La primera compilación tarda **varias horas**; las siguientes, minutos

## Paso a paso

### 1. Paquetes del sistema (una sola vez)

```bash
sudo apt update
sudo apt install -y gawk wget git diffstat unzip texinfo gcc build-essential \
  chrpath socat cpio python3 python3-pip python3-pexpect xz-utils debianutils \
  iputils-ping python3-git python3-jinja2 python3-subunit zstd liblz4-tool \
  file locales libacl1 bmap-tools pipx
sudo locale-gen en_US.UTF-8
pipx install kas
pipx ensurepath   # cerrar y abrir la terminal después
```

> En Ubuntu 24.04, si bitbake se queja de "user namespaces" (AppArmor), ejecutar:
> `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`

### 2. Clonar el repositorio

```bash
git clone <URL-del-repo> andon-yocto
cd andon-yocto
```

### 3. Empacar el modelo (una sola vez, ~1 GB)

```bash
./scripts/empacar-modelo.sh
```

Descarga una copia temporal de Ollama para la PC, baja `tev1:0.8b` y deja el archivo
`meta-andon/recipes-ai/ollama/files/tev1-0.8b-models.tar.gz`. Ese archivo **no se sube
a git** (está en `.gitignore`); cada integrante lo genera con este script.

### 4. Compilar

```bash
kas build andon.yml
```

La imagen queda en:

```
build/tmp/deploy/images/raspberrypi4-64/andon-image-raspberrypi4-64.rootfs.wic.bz2
```

### 5. Grabar la microSD

Identificar la tarjeta con `lsblk` (por ejemplo `/dev/sdX`; **revisar bien**, se borra todo):

```bash
cd build/tmp/deploy/images/raspberrypi4-64/
sudo bmaptool copy andon-image-raspberrypi4-64.rootfs.wic.bz2 /dev/sdX
```

### 6. Primer arranque

- Usuario `root`, sin contraseña (solo para desarrollo: lo habilita `debug-tweaks`).
- Por cable de red: `ssh root@<ip-de-la-pi>`.
- Por consola serial (UART habilitada): GPIO 14/15, 115200 baudios.

## Pruebas de salida de cada etapa

**E1 · Imagen base**

```bash
uname -a                 # kernel de la Raspberry Pi, aarch64
systemctl --failed       # no debería haber servicios fallidos
```

**E2 · Hardware** (con los sensores conectados)

```bash
i2cdetect -y 1           # 0x68 = MPU-6050, 0x3c = OLED
ls /sys/bus/w1/devices/  # 28-xxxxxxxxxxxx = DS18B20
gpiodetect               # controladores GPIO disponibles
```

**E3 · Ollama y modelo**

```bash
sh probar-ollama.sh      # copiar el script a la Pi con scp
```

Debe responder `falla_electrica` con su probabilidad, sin Internet, y mostrar la latencia.
La primera consulta es más lenta porque carga el modelo; repetirla para medir la normal.

## Comandos útiles durante el desarrollo

```bash
kas shell andon.yml                        # abre una terminal con bitbake listo
bitbake ollama-bin                         # compila una sola receta
bitbake -c cleansstate ollama-bin          # la limpia para recompilarla desde cero
bitbake -e andon-image | grep ^IMAGE_INSTALL=   # ver qué entra en la imagen
```

## Decisiones de diseño

- **Ollama precompilado.** No existe una capa oficial de Ollama para Yocto. Compilarlo
  implica Go más llama.cpp con CMake; empaquetar el binario oficial es más rápido y
  menos riesgoso. Se instalan solo `bin/ollama` y el backend de CPU (~65 MB) y se
  descartan las bibliotecas CUDA (~2,2 GB) que la Pi no usa. Ollama escoge solo la
  variante `libggml-cpu-armv8.0`, que corresponde al Cortex-A72 de la Pi 4.
- **Modelo dentro de la imagen.** Así la estación funciona sin Internet desde el
  primer arranque (REQ-N03).
- **Ollama solo escucha en `127.0.0.1`.** Nadie fuera de la Pi puede consultarlo
  directamente; solo `andon-core`.
- **`OLLAMA_KEEP_ALIVE=-1`.** El modelo queda cargado en memoria para que cada
  decisión no pague el tiempo de carga.

## Pendiente (etapa E4)

Agregar a `meta-andon` las recetas de la aplicación: `andon-sensores`, `andon-core`,
`andon-web`, la configuración de `hostapd`/`dnsmasq` para la red Wi-Fi propia y la
de `mosquitto`.
