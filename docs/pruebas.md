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
| REQ-F03 formulario web (≤ 280) | ✅ F5 | — | Formulario, tablero, supervisor y simulador; probado en navegador (Chromium) en la PC y en la RPi 4 (9 nov) |
| REQ-F04 estado → `/v1/systemone` | ✅ | ✅ | Cliente probado en Docker y en la RPi 4 (D4) |
| REQ-F05 cinco categorías | ✅ | ✅ | 16/16 reportes claros; conjunto pequeño y fácil |
| REQ-F06 área responsable | ✅ F4 | — | Tabla 9: mantenimiento, calidad o supervisión en cada `evento` (CU-03/04/05, modelo real en Docker y en la RPi 4) |
| REQ-F07 paro por umbral sin modelo | ✅ | ⏳ | Decidido en `andon-sensores` sin MQTT ni modelo. Umbrales provisionales hasta calibrar |
| REQ-F08 amarillo si baja confianza | ✅ F4 | ⏳ | Probabilidad < 0,92, timeout, error HTTP o JSON inválido → amarilla y revisión manual, sin parar la máquina (pruebas unitarias y CU-05 con el modelo real) |
| REQ-F09 torre, zumbador, OLED | ✅ | 🟡 | Torre, zumbador y OLED virtuales en la web. En la placa, los 5 GPIO quedan como salidas de `andon-sensores` y GPIO17 en bajo durante el paro (9 nov). OLED: controlador escrito y probado con dobles, sin pantalla real (D5) |
| REQ-F10 registro de eventos | ✅ F4 | ✅ | SQLite (`db_ruta`): fecha, lecturas, texto, categoría, probabilidad, acción, área, latencia y error. En la placa se escribe en `/var/lib/andon/andon.db` (9 nov) |
| REQ-F11 publicación MQTT | ✅ F3–F5 | ✅ | `lecturas`, `seguridad`, `salidas`, `evento` y `estado` con Mosquitto real, en Docker y en la placa |
| REQ-N01 sin Internet | 🟡 | 🟡 | Modelo y servicios locales (Diego); se cierra en F7 |
| REQ-N02 RPi + Yocto | — | ✅ | La imagen arranca la app completa en la RPi 4 (9 nov) |
| REQ-N03 Ollama y modelo preinstalados | — | ✅ | `ollama list` en la imagen, sin descargas (Diego, 5 nov; verificado 6 nov) |
| REQ-N04 paro < 1 s | ✅ | 🟡 | Sim en PC: ≈ 200 ms desde la inyección y 0,7–1,1 ms desde la muestra que cruza el umbral. En la RPi 4 en modo sim con Ollama calculando: 272–375 ms (6 y 9 nov), 340 ms visto desde el navegador. Faltan sensores reales |
| REQ-N05 clasificación ≤ 3 s | — | ❌ | ≈ 17 s en la RPi 4; no se cumple y se reporta (D4) |
| REQ-N06 arranque automático (systemd) | — | ✅ | Los tres servicios habilitados en la imagen; arriba a los 8,6 s del arranque, sin DHCP (H1 resuelto). Falta probar un corte de corriente con la app en marcha |
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

Pendientes de estos CU: sensores reales (bloque hardware). El nivel 3b se ejecutó el 6 nov (abajo).

## CU-03, CU-04 y CU-05 en simulación (F4)

Evidencia: `docs/evidencias/f4-cu03-cu04-cu05-modelo-real.txt`. Requisitos: `mosquitto` y `ollama` de
compose arriba; sin otros `andon-sensores`/`andon-core` publicando. Con `fake_ollama` (sin modelo)
las mismas pruebas corren en `app/tests/unit/test_flujo_integracion.py`.

```bash
docker compose -f docker/compose.yaml --profile sim up -d --no-deps sensores core   # --no-deps: no recrea Ollama
mosquitto_sub -h localhost -t 'andon/e1/#' -v -F '%I %t %p'                          # en otra terminal
R="docker exec -e ANDON_MQTT_HOST=mosquitto andon-dev-1 python /work/app/tools/enviar_reporte.py"
$R "Huele a quemado y salió una chispa del cable de alimentación" --reiniciar          # CU-03 y CU-06
$R "Las piezas salen rayadas y fuera de especificación"                                # CU-04
$R "Algo raro pasa, no sé qué es"                                                      # CU-05
docker compose -f docker/compose.yaml --profile sim stop sensores core                # antes de pytest
```

| Caso | Reporte | Esperado | Resultado (6 nov, PC, modelo real) |
|---|---|---|---|
| **CU-03** falla que los sensores no ven | «Huele a quemado y salió una chispa del cable de alimentación» | `falla_electrica` ≥ 0,92 → máquina detenida (primero `cmd/maquina parar`, luego luz roja y zumbador), aviso a mantenimiento; sin paro de seguridad | ✅ 0,987; 3,7 s; luz roja, zumbador, `maquina:false` |
| **CU-04** reporte de calidad | «Las piezas salen rayadas y fuera de especificación» | `problema_calidad` → luz amarilla, la máquina sigue, aviso a calidad | ✅ 0,999; 3,6 s |
| **CU-05** reporte ambiguo | «Algo raro pasa, no sé qué es» | Probabilidad < 0,92 → amarilla, revisión manual, la máquina sigue | ✅ 0,684; 3,6 s |
| Operación normal | «Todo funciona bien, la máquina corre sin problemas» | `operacion_normal` → verde | ✅ 0,9999; 3,6 s |
| **CU-06** reinicio tras detención del core | `cmd/maquina reiniciar` origen `web` | Máquina en marcha, luz verde, estado `reposo` | ✅ |
| Ollama colgado / caído | `fake_ollama --modo colgado` (timeout 1 s) | Amarilla y revisión manual; el paro por umbral sigue funcionando | ✅ prueba automática |
| Paro de seguridad durante el análisis | Falla inyectada mientras se consulta | Gana el paro: sin órdenes de luz ni de máquina; acción `paro_activo` | ✅ pruebas unitarias |
| Invariante 3 | Cualquier clasificación | El core solo ordena `parar`, nunca arrancar; `reiniciar` con origen `core` se ignora | ✅ |

Hallazgo: «Salen chispas del cable y huele a quemado cerca del motor» dio 0,886 con el modelo real y
fue a revisión manual. La confianza depende de la redacción (D4, hallazgo 4): la demostración de CU-03
usa la frase de la tabla (0,987). En la RPi 4 la latencia será ≈ 17 s por reporte (REQ-N05 no se cumple, D4);
durante el análisis la luz queda amarilla («Analizando…») y la web no se bloquea.

**Pendiente de probar en la placa:** repetir en la RPi 4 con la imagen (nivel 3b, `andon-core` + `andon-sensores` en modo sim, drop-in de la sección «Nivel 3b», Ollama de la imagen). Se espera ≈ 17 s por reporte, la luz amarilla «Analizando…» durante la consulta, el paro por umbral < 1 s mientras Ollama calcula y `andon.db` creado en `/var/lib/andon`. Procedimiento: copiar la app como en «Nivel 3b», `systemctl start andon-sensores andon-core` (con el drop-in sim en `andon-sensores`) y enviar los reportes con `python3 /opt/andon/enviar_reporte.py --host 127.0.0.1 "..."` (copiar `app/tools/enviar_reporte.py`).

## App completa en la RPi 4 con la imagen Yocto (9 nov)

Todo lo que no necesita sensores, con el modelo real. En la placa, como root:

```bash
python3 /opt/andon/probar_sin_hardware.py        # ≈ 6 min; deja la placa como estaba
sh /opt/andon/modo.sh sim                         # panel: http://<placa>:5000/simulador y /defensa
sh /opt/andon/modo.sh real
```

| Prueba | Resultado (9 nov) |
|---|---|
| Arranque sin DHCP (H1) | ✅ Mosquitto y los servicios arriba a los 8,6 s; 0 servicios fallidos |
| `verificar-imagen.sh` | ✅ 34 OK · 0 fallos · 3 avisos (sensores y OLED ausentes) |
| Modo real sin sensores | ✅ paro `mpu6050_fallo` (D13); 5 GPIO tomados por `andon-sensores`, GPIO17 en bajo |
| CU-01 a CU-07 con el modelo real | ✅ CU-03 98,6 % → máquina detenida; CU-04 99,9 %; CU-05 68 % → revisión manual; ≈ 17 s por reporte |
| Paro con el modelo calculando | ✅ 340–375 ms |
| Ollama detenido | ✅ revisión manual; el paro sigue funcionando |
| `probar_sin_hardware.py` | 69 OK · 1 fallo: el lazo se retrasaba 1 s cada 10–25 s **solo en modo real sin MPU-6050** (el bus vacío cuelga ~1 de cada 1000 intentos de iniciarlo). Corregido: reintento cada 0,5 s; 0 retrasos en 3 min |
| `/defensa`, Ejecutar todos | ✅ 10 de 10 en 94 s |

Evidencias: `docs/evidencias/f7-placa-sin-hardware-20261109.txt`, `f7-defensa-placa-20261109.txt` y `.png`.

## Nivel 3b · la RPi 4 con la imagen Yocto, `ANDON_MODO=sim`

**Ejecutado el 6 nov** (evidencia: `docs/evidencias/f3-3b-rpi-sim.txt`). Valida systemd, el usuario
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

**Resultado:** paro de 304 ms sin carga y de 272–363 ms con Ollama calculando (carga de CPU 2,8);
desde la muestra que cruza el umbral hasta la máquina detenida, 1–2 ms; 0 avisos «se retrasó». Cumple
REQ-N04 con margen en la placa (aún con sensores simulados). Al repetir una inyección hay que esperar a
que expire la falla (`--duracion-s`) antes de reiniciar, o el sistema vuelve a parar (correcto).

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
