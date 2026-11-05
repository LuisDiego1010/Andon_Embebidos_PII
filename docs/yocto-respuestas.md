# Respuestas a los requisitos de la app para la imagen Yocto (v1)

Para: Eduardo (app). De: Diego (imagen Yocto). Fecha: 2026-11-05.
Responde las preguntas abiertas de `docs/yocto-requisitos.md` v1.

## Respuestas

| # | Pregunta | Respuesta |
| --- | --- | --- |
| 1 | ¿Scarthgap y Python 3.12? | **Sí.** Yocto 5.0 *scarthgap* (poky `b6ae714a`), Python **3.12.15**. En Yocto el paquete `python3` equivale a `python3-modules`: trae la biblioteca estándar completa (`sqlite3`, `json`, `urllib`, `threading`, `logging`). |
| 2 | ¿Versión de `libgpiod` y sus enlaces de Python? | **libgpiod 2.1.3** (meta-oe) y **python3-gpiod 2.1.3** (meta-python): **API v2**. También va `libgpiod-tools` (`gpioset`, `gpioget`, `gpiodetect`). |
| 3 | ¿Cómo se incluye `tev1:0.8b` y qué Ollama? | **Ollama 0.40.13** (binario oficial arm64, solo backend de CPU). Cumple el mínimo de **0.40.4** que pide el modelo. El modelo se descarga en la PC con `scripts/empacar-modelo.sh` y la receta `ollama-model-tev1` lo instala en `/var/lib/ollama/models` (`OLLAMA_MODELS`). Servicio `ollama.service`, usuario `ollama`, escucha en `127.0.0.1:11434`, `OLLAMA_KEEP_ALIVE=-1` (el modelo queda cargado). En Docker se fijó `ollama/ollama:0.40.13` para que coincida. |
| 4 | ¿Pin del bus 1-Wire y overlays? | 1-Wire en **GPIO4** (`ENABLE_W1 = "1"`, overlay `w1-gpio`). I2C en el bus 1 (`ENABLE_I2C = "1"` → `dtparam=i2c_arm=on`) a **400 kHz** (`dtparam=i2c_arm_baudrate=400000`). `i2c-dev` se carga al arrancar. |
| 5 | ¿Usuario de servicio, grupos y udev? | Receta **`andon-app`** crea el usuario de sistema **`andon`** (home `/var/lib/andon`, sin shell) y los grupos **`i2c`** y **`gpio`**. Las reglas udev de meta-raspberrypi (`99-com.rules` de `raspberrypi-sys-mods`) asignan `/dev/i2c-*` al grupo `i2c` y `/dev/gpiochip*` al grupo `gpio`. `andon-sensores` corre con `SupplementaryGroups=i2c gpio`. |
| 6 | ¿Imagen `qemuarm64`? | **No por ahora**: sería otra compilación completa de varias horas. Propuesta: el nivel 3 sigue en QEMU con Debian arm64 y pasamos antes a la placa con la imagen Yocto real, que ya existe (ver abajo). |

## Lo que ya hace la receta `andon-app`

Archivo: `meta-andon/recipes-andon/andon-app/andon-app.bb`.

- Toma el código directo de **`app/` de este mismo repo** (`externalsrc`): no hace falta
  publicar una etiqueta para probar. Para la entrega final se puede fijar a `v1.0-rcN`.
- **Si `app/Makefile` tiene un objetivo `install`**, lo usa: `make install DESTDIR=...`
  (tu instalador de F6). Mientras no exista, copia `app/src/andon` a `/opt/andon/andon`,
  `app/config/*.conf` a `/etc/andon/` y `reportes.json` a `/opt/andon/pruebas/`.
- Crea `/var/lib/andon` (dueño `andon`, permisos 0750).
- Instala tres unidades systemd. Las dejo en la receta; si preferís mantenerlas en
  `app/deploy/`, las movemos:

| Unidad | Comando | Usuario | Depende de |
| --- | --- | --- | --- |
| `andon-sensores.service` | `python3 -m andon.sensores` | `andon` + `i2c`, `gpio` | mosquitto |
| `andon-core.service` | `python3 -m andon.core` | `andon` | mosquitto, ollama |
| `andon-web.service` | `python3 -m andon.web` | `andon` | mosquitto |

  Todas con `PYTHONPATH=/opt/andon` y `ANDON_CONF=/etc/andon/andon.conf`.
  **Vienen desactivadas** hasta que cada módulo tenga su `__main__.py`.

## Lo que necesito de vos

1. **Punto de entrada** de cada servicio: `andon/sensores/__main__.py`,
   `andon/core/__main__.py` y `andon/web/__main__.py` (o decime qué comando usar).
2. **Nombre del archivo de configuración**: asumí `/etc/andon/andon.conf` y la variable
   `ANDON_CONF`. Si es otro, lo cambio en las unidades.
3. **Configuración de Mosquitto, hostapd y dnsmasq** en `app/deploy/` cuando la tengás
   (por ahora Mosquitto usa su configuración por defecto: `127.0.0.1:1883`, anónimo).
4. Confirmar que el puerto **5000** de `andon-web` escucha en `0.0.0.0` (para el celular
   del operario).

## Propuesta de cambio al plan

La imagen Yocto ya compila (falta el primer arranque en la placa, hoy), así que propongo **probar la app sobre la imagen
desde el viernes 6**, en vez de pasar primero por Raspberry Pi OS:

- Diego mide hoy en la placa latencia y exactitud de `tev1:0.8b` con
  `scripts/medir-latencia.py` (mismo cliente y mismos 19 reportes de la prueba de
  contrato) y te pasa los números para recalibrar el timeout y el umbral de D4.
- Para probar cambios sin recompilar: `scp -r app/src/andon root@<pi>:/opt/andon/`
  (ver `docs/pruebas-placa.md`, paso 8).
- Raspberry Pi OS queda solo como contingencia.
