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
| 2026-11-06 | RPi 4 (Yocto) | `probar_hal.py` | 3 OK · 0 fallos · 2 avisos: GPIO (libgpiod v2) e I2C abren; MPU-6050 y DS18B20 sin conectar |
| | RPi 4 con hardware | `probar_hal.py --salidas` | 🔌 pendiente: sensores y actuadores sin conseguir |
| 2026-11-06 | RPi 4 (Yocto) | `probar_calentamiento.py --descargar` | calentamiento en frío 37,0 s; consulta caliente 16,9 s (`performance` y `ondemand` iguales, ≈ 17,0 s) |
