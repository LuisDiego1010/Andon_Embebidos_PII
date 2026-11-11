SUMMARY = "Imagen de la Estación Andon Inteligente de Borde"
DESCRIPTION = "Linux para Raspberry Pi 4 con Ollama, el modelo tev1:0.8b, \
la aplicación Andon y sus dependencias (I2C, 1-Wire, GPIO, MQTT, Wi-Fi)."
LICENSE = "MIT"

require recipes-core/images/core-image-base.bb

IMAGE_FEATURES += "ssh-server-openssh"

# Contraseña de root (con allow-root-login de andon.yml, sirve también por SSH). El hash es SHA-512;
# el repositorio es público y la contraseña es simple: cambiarla en la placa al grabarla (passwd).
inherit extrausers
ANDON_ROOT_HASH = "\$6\$7pa.QpjUwRaTlg5U\$Kjkk0.uvk1HAxdEaUhQYwxVzQCAhjEZCiUYzImG7t9sFgPbIYV/I6hQoSff6nWL8g5eBgbyJoBEKgEDLkAsLF0"
EXTRA_USERS_PARAMS = "usermod -p '${ANDON_ROOT_HASH}' root;"

IMAGE_INSTALL:append = " \
    ollama-bin \
    ollama-model-tev1 \
    andon-app \
    \
    i2c-tools \
    libgpiod \
    libgpiod-tools \
    \
    python3 \
    python3-requests \
    python3-flask \
    python3-paho-mqtt \
    python3-smbus2 \
    python3-gpiod \
    sqlite3 \
    \
    mosquitto \
    mosquitto-clients \
    hostapd \
    dnsmasq \
    curl \
    avahi-daemon \
"

# Nota: en Yocto el paquete "python3" equivale a python3-modules,
# así que la biblioteca estándar completa (sqlite3, json, urllib...) ya viene.

# avahi-daemon anuncia la placa en la red: ssh root@raspberrypi4-64.local

# Espacio extra en la partición raíz para logs y la base de datos de eventos (KB)
IMAGE_ROOTFS_EXTRA_SPACE = "1048576"
