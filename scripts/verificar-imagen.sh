#!/bin/sh
# Verifica, DENTRO de la Raspberry Pi, que la imagen Yocto cumple lo que la app
# necesita (docs/yocto-requisitos.md). Pruebas de salida de E1, E2 y E3.
#   sh verificar-imagen.sh            (como root)
# No modifica nada. Al final imprime un resumen con los fallos.

OK=0; FALLO=0; AVISO=0
bien()  { echo "  [OK]    $1"; OK=$((OK+1)); }
mal()   { echo "  [FALLO] $1"; FALLO=$((FALLO+1)); }
aviso() { echo "  [AVISO] $1"; AVISO=$((AVISO+1)); }
seccion() { echo; echo "== $1"; }

seccion "E1 · Sistema base"
[ "$(uname -m)" = "aarch64" ] && bien "arquitectura aarch64" || mal "arquitectura: $(uname -m)"
grep -q "Poky\|Yocto" /etc/os-release 2>/dev/null && bien "imagen Yocto: $(. /etc/os-release; echo "$PRETTY_NAME")" || aviso "no parece una imagen Yocto"
echo "        kernel: $(uname -r)"
F=$(systemctl --failed --no-legend 2>/dev/null | wc -l)
[ "$F" -eq 0 ] && bien "sin servicios fallidos" || mal "$F servicio(s) fallido(s): systemctl --failed"
RAM=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
echo "        RAM total: ${RAM} MB · disponible: $(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo) MB"
echo "        disco /: $(df -h / | awk 'NR==2{print $4 " libres de " $2}')"

seccion "Python y bibliotecas de la app"
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
[ "$PYV" = "3.12" ] && bien "Python $PYV" || mal "Python: ${PYV:-no encontrado} (se esperaba 3.12)"
for m in flask paho.mqtt.client smbus2 gpiod sqlite3 json urllib.request threading logging; do
    python3 -c "import $m" 2>/dev/null && bien "import $m" || mal "falta el módulo $m"
done
GV=$(python3 -c 'import gpiod; print(gpiod.__version__)' 2>/dev/null)
case "$GV" in 2.*) bien "python3-gpiod $GV (API v2)";; *) mal "python3-gpiod: ${GV:-?} (se esperaba 2.x)";; esac

seccion "E3 · Ollama y modelo"
OV=$(ollama --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | tail -1)
[ -n "$OV" ] && bien "ollama $OV" || mal "no se encontró el binario ollama"
systemctl is-active -q ollama && bien "servicio ollama activo" || mal "servicio ollama inactivo: journalctl -u ollama"
curl -sf http://127.0.0.1:11434/api/version >/dev/null && bien "API en 127.0.0.1:11434" || mal "la API no responde"
ollama list 2>/dev/null | grep -q "tev1:0.8b" && bien "modelo tev1:0.8b instalado" || mal "falta el modelo tev1:0.8b"

seccion "MQTT"
systemctl is-active -q mosquitto && bien "servicio mosquitto activo" || mal "mosquitto inactivo"
if command -v mosquitto_sub >/dev/null; then
    ( mosquitto_sub -h 127.0.0.1 -t andon/prueba -C 1 -W 3 > /tmp/.mqtt_prueba 2>/dev/null & )
    sleep 1; mosquitto_pub -h 127.0.0.1 -t andon/prueba -m hola 2>/dev/null; sleep 1
    grep -q hola /tmp/.mqtt_prueba 2>/dev/null && bien "publicar/suscribir en 127.0.0.1:1883" || mal "MQTT no entregó el mensaje"
    rm -f /tmp/.mqtt_prueba
else
    mal "faltan mosquitto_pub/mosquitto_sub (mosquitto-clients)"
fi

seccion "E2 · Buses y GPIO"
[ -e /dev/i2c-1 ] && bien "/dev/i2c-1 ($(stat -c '%G %a' /dev/i2c-1))" || mal "no existe /dev/i2c-1"
CFG=""; for c in /boot/config.txt /boot/firmware/config.txt; do [ -f "$c" ] && CFG=$c; done
if [ -n "$CFG" ]; then
    grep -q "i2c_arm=on" "$CFG" && bien "config.txt: i2c_arm=on" || mal "config.txt sin i2c_arm=on"
    grep -q "i2c_arm_baudrate=400000" "$CFG" && bien "config.txt: I2C a 400 kHz" || aviso "config.txt sin i2c_arm_baudrate=400000"
    grep -q "w1-gpio" "$CFG" && bien "config.txt: overlay w1-gpio" || mal "config.txt sin dtoverlay=w1-gpio"
else
    aviso "no encontré config.txt (¿partición boot sin montar?)"
fi
ls /sys/bus/w1/devices/ 2>/dev/null | grep -q w1_bus_master && bien "bus 1-Wire activo" || mal "no hay bus 1-Wire (/sys/bus/w1)"
S=$(ls /sys/bus/w1/devices/ 2>/dev/null | grep '^28-' | head -n 1)
[ -n "$S" ] && bien "DS18B20 detectado: $S" || aviso "no hay DS18B20 conectado (normal sin hardware)"
if command -v i2cdetect >/dev/null && [ -e /dev/i2c-1 ]; then
    D=$(i2cdetect -y 1 2>/dev/null)
    echo "$D" | grep -q " 68" && bien "MPU-6050 en 0x68" || aviso "no hay MPU-6050 en 0x68 (normal sin hardware)"
    echo "$D" | grep -q " 3c" && bien "OLED en 0x3c" || aviso "no hay OLED en 0x3c (normal sin hardware)"
fi
command -v gpiodetect >/dev/null && bien "gpiodetect: $(gpiodetect 2>/dev/null | head -n 1)" || mal "faltan las herramientas de libgpiod"
ls /dev/gpiochip* >/dev/null 2>&1 && bien "gpiochip: $(stat -c '%n %G' /dev/gpiochip0 2>/dev/null)" || mal "no hay /dev/gpiochip*"

seccion "App Andon (receta andon-app)"
if id andon >/dev/null 2>&1; then
    bien "usuario andon: $(id andon)"
    id -nG andon | grep -qw i2c && id -nG andon | grep -qw gpio && bien "andon está en i2c y gpio" || mal "andon no está en los grupos i2c y gpio"
else
    mal "no existe el usuario andon (¿falta andon-app en la imagen?)"
fi
[ -d /opt/andon/andon ] && bien "código en /opt/andon" || mal "no existe /opt/andon/andon"
[ -d /etc/andon ] && bien "/etc/andon" || mal "no existe /etc/andon"
[ -d /var/lib/andon ] && bien "/var/lib/andon ($(stat -c '%U' /var/lib/andon))" || mal "no existe /var/lib/andon"
PYTHONPATH=/opt/andon python3 -c "import andon.core.ollama" 2>/dev/null && bien "import andon.core.ollama" || mal "no se puede importar andon.core.ollama"
for u in andon-sensores andon-core andon-web; do
    systemctl cat $u >/dev/null 2>&1 && echo "        $u: $(systemctl is-enabled $u 2>/dev/null) / $(systemctl is-active $u 2>/dev/null)" || mal "falta la unidad $u.service"
done

seccion "Red"
echo "        IP: $(ip -4 -o addr show scope global 2>/dev/null | awk '{print $2 " " $4}' | tr '\n' ' ')"
systemctl is-active -q avahi-daemon && bien "avahi: ssh root@$(hostname).local" || aviso "avahi-daemon inactivo (usar la IP)"

echo
echo "== Resumen: $OK OK · $FALLO fallos · $AVISO avisos"
[ "$FALLO" -eq 0 ] && echo "   La imagen cumple lo que necesita la app." || echo "   Revisar las líneas [FALLO] de arriba."
exit "$FALLO"
