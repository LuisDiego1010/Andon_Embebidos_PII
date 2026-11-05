# Requisitos de la app para la imagen Yocto — v1

Para: Diego (imagen Yocto, `meta-andon/`, `kas/`). De: Eduardo (app).
Fecha: 2026-11-04. Versión 1 (F1); la v2 (F6) agrega rutas finales, instalador,
unidades systemd y pruebas `oeqa`.

La app se desarrolla contra estos supuestos y no depende de la imagen. Todo lo marcado
como **pregunta** necesita respuesta tuya.

## 1. Plataforma
- Raspberry Pi 4 (aarch64, Cortex-A72). El código no cambia si se vuelve a RPi 5.
- Yocto **Scarthgap** con **Python 3.12**. **Pregunta:** ¿confirmas ambos?
- Sin Internet en ningún momento (REQ-N01): nada se descarga en el primer arranque.

## 2. Paquetes de Python (bibliotecas de terceros)
Todo lo demás es biblioteca estándar (`urllib`, `sqlite3`, `json`, `threading`, `logging`).

| Dependencia | Uso | Proceso |
|---|---|---|
| `flask` | formulario y `/tablero` | `andon-web` |
| `paho-mqtt` (1.x o 2.x) | MQTT, envuelto en `common/mqtt.py` | todos |
| `smbus2` | MPU-6050 y OLED por I2C | `andon-sensores` |
| `gpiod` (enlaces Python de **libgpiod v2**) | MOSFET, LEDs, zumbador | `andon-sensores` |

- GPIO solo con libgpiod v2 (nunca RPi.GPIO). **Pregunta:** ¿qué versión de
  `libgpiod` trae Scarthgap? Si es 1.x necesito saberlo antes de F2 (la API de Python cambia).
- `pytest` **no** va a la imagen (solo desarrollo y las pruebas `oeqa` si las requieren).

## 3. Servicios y binarios
- **Mosquitto** (broker local, puerto 1883). Configuración que entregaré en
  `app/deploy/mosquitto/` (v2).
- **Ollama ≥ 0.35** para aarch64, como servicio systemd, con el modelo **`tev1:0.8b`
  preinstalado** (REQ-N03). En el desarrollo se usa Ollama 0.40.14; el modelo requiere
  Ollama ≥ 0.40.4 (`ollama show tev1:0.8b` → «requires 0.40.4»), **no 0.35**.
  Hay que fijar esa versión mínima en la receta.
  - Modelo: ≈ 833 MB en disco, ≈ 1,3 GiB de RAM al cargarlo. Espacio de la imagen y
    RAM de la placa deben contemplarlo.
  - Los pesos deben estar en el almacén de Ollama del usuario que corre el servicio
    (`~/.ollama/models` o `OLLAMA_MODELS`). **Pregunta:** ¿cómo los vas a incluir
    (receta con los blobs descargados)? Si hace falta, te doy el manifiesto y los hashes.
  - Endpoint usado: `http://127.0.0.1:11434/v1/systemone`.
- `sqlite3` (módulo de Python) para el registro en `/var/lib/andon`.
- Herramientas de diagnóstico: `i2c-tools` (`i2cdetect`), `libgpiod-tools` (`gpioset`,
  `gpioget`), `mosquitto-clients`, `curl`.
- Punto de acceso propio (Wi-Fi de la estación): `hostapd` y `dnsmasq`. Es lo último
  en el orden de recortes; si no alcanza, se usa router o hotspot.
- `systemd` como init (REQ-N06).

## 4. Núcleo y dispositivos
- **I2C bus 1** habilitado: `/dev/i2c-1` (MPU-6050 en 0x68, OLED SSD1306 en 0x3C).
- **1-Wire** con `w1-gpio` y `w1-therm`: DS18B20 en `/sys/bus/w1/devices/28-*/w1_slave`.
  Hace falta el overlay `w1-gpio` en `config.txt`. **Pregunta:** ¿qué pin usas para
  el bus 1-Wire? (por defecto GPIO4).
- `/dev/gpiochip*` accesible para el usuario del servicio `andon-sensores`.
- Overlay/parámetro de I2C (`dtparam=i2c_arm=on`) y su velocidad (400 kHz).
- Todo GPIO a 3,3 V (REQ-N07); no requiere nada de la imagen.

## 5. Usuarios, rutas y permisos
- Rutas de instalación: `/opt/andon` (código), `/etc/andon/andon.conf`
  (configuración), `/var/lib/andon` (SQLite, escritura).
- Propongo un usuario de sistema `andon` en los grupos `i2c` y `gpio`
  (solo `andon-sensores` toca hardware). **Pregunta:** ¿cómo manejas los grupos y las reglas udev para
  `/dev/i2c-1` y `/dev/gpiochip*`?
- `andon-web` y `andon-core` no necesitan acceso a hardware.
- Servicios previstos (v2): `andon-sensores`, `andon-core`, `andon-web`, con
  dependencia de `mosquitto.service`; `andon-core` además de `ollama.service`.
- Puertos locales: 1883 (MQTT), 11434 (Ollama), 5000 (web, acceso desde la red de la estación).

## 6. Instalación
- La app se instala con `make install DESTDIR=...` (F6): el mismo instalador para
  Raspberry Pi OS, QEMU y la receta. La receta debería llamarlo, no copiar archivos a mano.
- La receta construye siempre desde una **etiqueta** de `app/dev` (`v0.9-sim`,
  `v1.0-rcN`), nunca desde una rama.

## 7. QEMU
- Necesito una imagen `qemuarm64` de la misma capa para el nivel 3 de pruebas
  (systemd, instalador, flujo completo) con `tools/fake_ollama.py` en lugar de Ollama
  real y `ANDON_MODO=sim`.
- En el nivel 3 la app corre con `config/andon-qemu.conf` (URL del Ollama falso).

## 8. Fechas relevantes para ti
- v2 de este documento y etiqueta `v0.9-sim`: al cerrar F6 (antes del lunes 9).
- Fecha límite para que la imagen arranque la app en la RPi 4: **miércoles 11, mediodía**
  (si no, demo sobre Raspberry Pi OS; ver Contingencia en `docs/plan.md`).

## Preguntas abiertas (resumen)
1. ¿Scarthgap y Python 3.12 confirmados?
2. ¿Versión de `libgpiod` y de sus enlaces de Python?
3. ¿Cómo se incluye el modelo `tev1:0.8b` y qué versión de Ollama se empaqueta (≥ 0.40.4)?
4. ¿Pin del bus 1-Wire y overlays de I2C / 1-Wire?
5. ¿Usuario de servicio, grupos y reglas udev?
6. ¿Imagen `qemuarm64` disponible para el nivel 3?
