SUMMARY = "Imagen de la Estación Andon Inteligente de Borde"
DESCRIPTION = "Linux para Raspberry Pi 4 con Ollama, el modelo tev1:0.8b \
y las dependencias de la estación (I2C, 1-Wire, GPIO, MQTT, Wi-Fi)."
LICENSE = "MIT"

require recipes-core/images/core-image-base.bb

IMAGE_FEATURES += "ssh-server-openssh"

IMAGE_INSTALL:append = " \
    ollama-bin \
    ollama-model-tev1 \
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
    hostapd \
    dnsmasq \
    curl \
"

# Espacio extra en la partición raíz para logs y la base de datos de eventos (KB)
IMAGE_ROOTFS_EXTRA_SPACE = "1048576"
