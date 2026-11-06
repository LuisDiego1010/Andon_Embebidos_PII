# Guía de pruebas

Se escribe a lo largo de F2–F6 y se cierra en F6 (requisitos previos, procedimiento por
nivel y por caso de uso, y tabla de resultados). Estado: **en construcción**.

## Niveles de prueba
Ver `docs/plan.md` (Niveles de prueba). Comandos base:

```bash
# Nivel 1 · Docker dev (x86)
docker compose -f docker/compose.yaml up -d
docker compose -f docker/compose.yaml exec dev pytest app/tests/unit
docker compose -f docker/compose.yaml exec dev pytest app/tests/contract -s   # requiere Ollama

# Nivel 2 · aarch64 (emulado)
docker run --rm --platform linux/arm64 -v "$PWD":/work:ro -w /work \
    -e PYTHONPATH=/work/app/src -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim \
    sh -c "pip install -q pytest && python -m pytest -p no:cacheprovider -q app/tests/unit"
```

## Estado por requisito: simulación y hardware (D11)

Cada requisito tiene dos columnas para no dar por probado en hardware lo que solo se
simuló. «Hardware» significa sensores y actuadores reales; el modelo en la RPi 4 cuenta
como hardware porque no necesita sensores.

Leyenda: ✅ probado · 🟡 parcial · ⏳ pendiente · ❌ no cumple · — no aplica

| Requisito | Simulación | Hardware | Notas |
|---|---|---|---|
| REQ-F01 vibración ≥ 100 Hz, RMS cada 1 s | ✅ | ⏳ | Lazo medido a 100,0 Hz sin atrasos (PC); RMS de ventana de 1 s cada 100 ms |
| REQ-F02 temperatura ≥ 1 Hz | ✅ | ⏳ | Hilo aparte a 1 Hz; el DS18B20 real tarda ~750 ms por lectura |
| REQ-F03 formulario web (≤ 280) | ⏳ F5 | — | |
| REQ-F04 estado → `/v1/systemone` | ✅ | ✅ | Cliente probado en Docker y en la RPi 4 (D4) |
| REQ-F05 cinco categorías | ✅ | ✅ | 16/16 reportes claros; conjunto pequeño y fácil |
| REQ-F06 área responsable | ⏳ F4 | — | |
| REQ-F07 paro por umbral sin modelo | ✅ | ⏳ | Decidido en `andon-sensores` sin MQTT ni modelo. Umbrales provisionales hasta calibrar |
| REQ-F08 amarillo si baja confianza | 🟡 | ⏳ | Los fallos del cliente ya se detectan; falta la regla del umbral (F4) |
| REQ-F09 torre, zumbador, OLED | 🟡 F2–F3 | ⏳ | Salidas probadas con dobles y GPIO abierto en la placa; sin torre conectada. OLED pendiente (D5) |
| REQ-F10 registro de eventos | ⏳ F4 | — | |
| REQ-F11 publicación MQTT | 🟡 F3 | — | `lecturas`, `seguridad` y `salidas` publicados; falta `evento` (F4) |
| REQ-N01 sin Internet | 🟡 | 🟡 | Modelo y servicios locales (Diego); se cierra en F7 |
| REQ-N02 RPi + Yocto | — | 🟡 | La imagen arranca en la RPi 4; falta la app activa |
| REQ-N03 Ollama y modelo preinstalados | — | ✅ | `ollama list` en la imagen, sin descargas (Diego, 5 nov; verificado 6 nov) |
| REQ-N04 paro < 1 s | ✅ | ⏳ | Sim en PC: ≈ 200 ms desde la inyección y 0,7–1,1 ms desde la muestra que cruza el umbral. Falta 3b (Ollama calculando) y sensores reales |
| REQ-N05 clasificación ≤ 3 s | — | ❌ | ≈ 17 s en la RPi 4; no se cumple y se reporta (D4) |
| REQ-N06 arranque automático (systemd) | ⏳ F6 | ⏳ | Unidades en la imagen, desactivadas hasta tener `__main__.py` |
| REQ-N07 ningún GPIO > 3,3 V | — | ⏳ | Reglas en `docs/hardware.md`; se verifica al cablear |

## CU-01 y CU-02 en simulación (F3)

Evidencia: `docs/evidencias/f3-cu01-cu02-cu06-sim.txt`. Requisitos: `docker compose up -d mosquitto`
y no tener otro `andon-sensores` publicando en el mismo broker.

```bash
# Automáticas (hilos y reloj real; con Mosquitto si está disponible)
docker compose -f docker/compose.yaml exec dev pytest app/tests/unit -q -s

# Manual: servicio real en Docker
docker compose -f docker/compose.yaml --profile sim up -d sensores
mosquitto_sub -h localhost -t 'andon/e1/#' -v                          # en otra terminal
docker compose -f docker/compose.yaml exec dev python app/tools/inyector.py --vib-g 2.0 --esperar-paro
docker compose -f docker/compose.yaml exec dev python app/tools/inyector.py --reiniciar
docker compose -f docker/compose.yaml --profile sim stop sensores
```

| Caso | Pasos | Esperado | Resultado (6 nov, PC) |
|---|---|---|---|
| **CU-01** operación normal | Arrancar `sensores` en sim | Máquina en marcha, luz verde; `lecturas` cada 1 s con vibración ≈ 0,10 g y temperatura creciente; `seguridad.activo=false` | ✅ 4 lecturas en 4 s: 0,100–0,103 g; 30,1 → 30,6 °C |
| **CU-02** paro por vibración | `inyector --vib-g 2.0 --esperar-paro` | Máquina detenida, luz roja, zumbador; `seguridad` retenido con `activo=true`; < 1 s | ✅ 201–204 ms (automática), 349 ms hasta el aviso con MQTT real; 0,7 ms de la muestra que cruza el umbral al paro |
| **CU-02** paro por temperatura | `inyector --temp-c 90` | Igual, con `sensor=temperatura` | ✅ 421 ms (la temperatura se lee a 1 Hz: hasta ~1 s según el momento) |
| Paro retenido | Esperar a que termine la falla | La máquina sigue detenida | ✅ |
| Invariante 3 | `cmd/maquina reiniciar` con `origen: core` | Se ignora | ✅ |
| Invariante 2 | `cmd/senal` luz verde durante el paro | Se ignora | ✅ |
| **CU-06** reinicio | `cmd/maquina reiniciar` con `origen: web` | Paro liberado, luz verde; el PIN lo valida `andon-web` (F5) | ✅ |
| Paro sobrevive al reinicio | `docker compose restart sensores` con paro activo | La máquina sigue detenida (`paro.json`) | ✅ |
| D13 falla de sensor | Sensor sin lectura > 2 s (prueba automática) | Paro retenido `mpu6050_fallo` / `ds18b20_fallo` | ✅ |
| D11 modo sim seguro | `sim/inyectar` con `ANDON_MODO=rpi` | Se ignora (no se suscribe) | ✅ prueba automática |

Pendientes de estos CU: sensores reales (bloque hardware) y el nivel 3b de abajo.

## Nivel 3b · la RPi 4 con la imagen Yocto, `ANDON_MODO=sim`

Pendiente de ejecutar (bloqueado por permisos el 6 nov). Valida systemd, el usuario
`andon` y el paro con Ollama calculando (REQ-N04 bajo contención de CPU). Desde la PC:

```bash
PI="root@fe80::<dirección de la placa>%enp1s0f0"      # ver docs/yocto-requisitos.md, H3
tar -C app/src --exclude=__pycache__ -cf - andon | ssh $PI 'rm -rf /opt/andon/andon && tar -C /opt/andon -xof -'
scp app/config/andon.conf $PI:/etc/andon/andon.conf
scp app/tools/inyector.py $PI:/opt/andon/inyector.py
```

En la placa (el modo sim se activa solo con este *drop-in*, nunca en la receta):

```bash
mkdir -p /etc/systemd/system/andon-sensores.service.d
printf '[Service]\nEnvironment=ANDON_MODO=sim\n' > /etc/systemd/system/andon-sensores.service.d/sim.conf
systemctl daemon-reload && systemctl start andon-sensores
journalctl -u andon-sensores -n 20 --no-pager

# CU-02 en la placa
python3 /opt/andon/inyector.py --host 127.0.0.1 --vib-g 2.0 --esperar-paro
python3 /opt/andon/inyector.py --host 127.0.0.1 --reiniciar

# Paro con Ollama calculando: lanzar una consulta (~17 s) y, mientras tanto, inyectar
(PYTHONPATH=/opt/andon python3 /opt/andon/probar_calentamiento.py --consultas 2 &) ; sleep 4
python3 /opt/andon/inyector.py --host 127.0.0.1 --vib-g 2.0 --esperar-paro
journalctl -u andon-sensores | grep -E "se retras|PARO"      # sin retrasos = el lazo aguanta
```

Esperado: paro < 1 s con y sin Ollama; ningún aviso «se retrasó». Si aparece, ver D11
(prioridad `Nice`, afinidad de núcleo, `OLLAMA_NUM_THREAD`). Para volver al estado normal:
`systemctl stop andon-sensores && rm -r /etc/systemd/system/andon-sensores.service.d && systemctl daemon-reload`.

## Verificación de periféricos (F2)

Criterio de salida de F2: la simulación y la placa pasan las **mismas pruebas de la
interfaz** (`app/tests/unit/test_hal_interfaz.py`, parametrizada sobre `sim` y `rpi`;
`rpi` con dobles de gpiod, smbus2 y sysfs).

### En la PC (sin hardware)
`pytest app/tests/unit` → incluye `test_hal_interfaz.py`, `test_hal_sim.py` y `test_hal_rpi.py`.

### En la Raspberry Pi 4 (imagen Yocto)
Requisitos: `docs/pruebas-placa.md` pasos 1–4. Desde la PC:

```bash
scp -r app/src/andon app/config/andon.conf app/tools/probar_hal.py app/tools/probar_calentamiento.py \
    root@raspberrypi4-64.local:/tmp/
```

En la placa (como root):

```bash
# Governor performance (opcional: no cambió la latencia medida el 6 nov)
for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > $f; done

# 1. Lectura de sensores y apertura de GPIO/I2C (sin mover salidas)
PYTHONPATH=/tmp ANDON_CONF=/tmp/andon.conf python3 /tmp/probar_hal.py

# 2. Con la torre, el zumbador y el MOSFET conectados
PYTHONPATH=/tmp ANDON_CONF=/tmp/andon.conf python3 /tmp/probar_hal.py --salidas

# 3. Calentamiento del modelo y latencia en caliente
PYTHONPATH=/tmp python3 /tmp/probar_calentamiento.py --descargar
```

Las comprobaciones manuales con herramientas del sistema (independientes de la app):
`i2cdetect -y 1` (esperado 0x68 y 0x3c), `ls /sys/bus/w1/devices/` (esperado `28-*`),
`gpioset -c gpiochip0 22=1` (LED verde).

### Resultados

| Fecha | Entorno | Prueba | Resultado |
|---|---|---|---|
| 2026-11-06 | PC x86 (Docker) | `pytest app/tests/unit` | 97 pruebas en verde |
| 2026-11-06 | aarch64 (Docker emulado) | `pytest app/tests/unit` | 97 pruebas en verde |
| 2026-11-06 | PC x86 (Docker) | `probar_calentamiento.py --descargar` | calentamiento en frío 6,0 s; consulta caliente 3,5 s |
| 2026-11-06 | PC x86 (Docker, Mosquitto real) | `pytest app/tests/unit` | 193 pruebas en verde (incluye paro < 1 s en tiempo real y extremo a extremo con MQTT) |
| 2026-11-06 | aarch64 (Docker emulado) | `pytest app/tests/unit` | 191 en verde, 2 omitidas (sin broker); el paro < 1 s también pasa bajo emulación |
| 2026-11-06 | PC (Docker) | CU-01, CU-02, CU-06 con `sensores` real | ver `docs/evidencias/f3-cu01-cu02-cu06-sim.txt` |
| 2026-11-06 | RPi 4 (Yocto) | `probar_hal.py` | 3 OK · 0 fallos · 2 avisos: GPIO (libgpiod v2) e I2C abren; MPU-6050 y DS18B20 sin conectar |
| | RPi 4 con hardware | `probar_hal.py --salidas` | 🔌 pendiente: sensores y actuadores sin conseguir |
| 2026-11-06 | RPi 4 (Yocto) | `probar_calentamiento.py --descargar` | calentamiento en frío 37,0 s; consulta caliente 16,9 s (`performance` y `ondemand` iguales, ≈ 17,0 s) |
