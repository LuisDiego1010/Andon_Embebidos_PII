# Estación Andon Inteligente de Borde — EL5841, II Proyecto

Nodo embebido junto a una máquina (simulada con un ventilador DC) que combina
sensores (vibración y temperatura) con reportes de texto libre del operario.
Clasifica la falla con Ollama (`tev1:0.8b`, endpoint `/v1/systemone`) y
señaliza, escala o detiene la máquina. Todo local, sin Internet.

## Entorno de trabajo
- Claude Code se abre en la raíz de este repositorio con acceso a la carpeta padre:
  `cd proy2/<repo> && claude --add-dir ..`
- La carpeta padre `proy2/` contiene los PDF del instructivo del proyecto y de la
  propuesta de diseño entregada. Son la fuente de los requerimientos (RG, REQ, CU).
  **Solo lectura**: no se modifican ni se copian al repositorio.
- PC de desarrollo: Ubuntu, x86_64.
- **Nunca ejecutar `sudo`.** Si algo requiere privilegios, entregar los comandos
  exactos al usuario para que los ejecute y luego verificar el resultado.

## Alcance y responsables
- `app/`, `docker/`, `docs/` → aplicación (Eduardo). Aquí se trabaja.
- `meta-andon/`, `kas/` → imagen Yocto (Diego). **No modificar** salvo pedido explícito.
- La app no depende de la imagen: se desarrolla contra los supuestos de plataforma.
- Lo que la imagen debe incluir se comunica a Diego en `docs/yocto-requisitos.md`.

## Plataforma objetivo (supuestos)
- Raspberry Pi 4 (aarch64, Cortex-A72). La propuesta decía RPi 5; el cambio está
  registrado. Si vuelve a RPi 5, el código no cambia (todo GPIO va por libgpiod).
- Imagen Yocto Scarthgap → **Python 3.12** (pendiente de confirmación de Diego).
- GPIO solo con libgpiod v2 (nunca RPi.GPIO). I2C bus 1 (MPU-6050 0x68, OLED 0x3C).
  DS18B20 por sysfs (`/sys/bus/w1/devices/28-*/w1_slave`).
- Desarrollo y pruebas: Docker (x86 y arm64) y la placa. QEMU se recortó (D17). La placa es un préstamo
  disponible solo entre semana; el resto del tiempo se trabaja en modo simulado.

## Arquitectura (decisiones: ver docs/plan.md y docs/decisiones/)
- `andon-sensores`: ÚNICO proceso que toca hardware (MPU-6050, DS18B20, MOSFET,
  LEDs, zumbador, OLED). Corre el lazo de seguridad.
- `andon-core`: máquina de estados, cliente de Ollama, registro en SQLite,
  publicación de eventos.
- `andon-web`: formulario (Flask), página `/tablero`, acciones con PIN.
- Comunicación entre servicios SOLO por MQTT (Mosquitto local).

## Invariantes de seguridad (no romper nunca)
1. El paro por umbral (REQ-F07) se decide dentro de `andon-sensores`, sin MQTT
   ni modelo, en < 1 s desde la lectura que cruza el umbral (REQ-N04).
2. Un paro por umbral queda retenido: se ignoran órdenes de luz o de arranque
   hasta `cmd/maquina: reiniciar` con PIN válido (CU-06).
3. Ningún resultado del modelo puede arrancar la máquina.
4. Si Ollama falla, supera el timeout o devuelve probabilidad menor al umbral de
   confianza → luz amarilla y revisión manual (REQ-F08). Nunca se bloquea el servicio.
5. Si el MPU-6050 o el DS18B20 no entregan lectura válida durante 2 s seguidos → paro
   retenido (`seguridad` con `sensor: "mpu6050_fallo"` o `"ds18b20_fallo"`), igual que un
   paro por umbral (D13).

## Lógica de decisión de andon-core (Tabla 9 de la propuesta)
Solo si la probabilidad supera el umbral de confianza:

| Categoría | Luz | Máquina | Aviso a |
|---|---|---|---|
| operacion_normal | verde | sigue | — |
| falla_mecanica | roja | se detiene | mantenimiento |
| falla_electrica | roja | se detiene | mantenimiento |
| problema_calidad | amarilla | sigue | calidad |
| material_faltante | amarilla | sigue | supervisión |

## Contrato MQTT (prefijo `andon/e1/`, payload JSON)
| Tópico | De → a | Campos |
|---|---|---|
| `lecturas` | sensores → * | ts, vib_rms_g, temp_c |
| `seguridad` (retenido) | sensores → core, web | ts, activo, sensor, valor, umbral |
| `cmd/maquina` | core, web → sensores | accion: parar \| reiniciar, origen |
| `cmd/senal` | core → sensores | luz: verde \| amarilla \| roja, zumbador, oled |
| `reporte` | web → core | id, texto (≤ 280), ts_navegador |
| `evento` | core → público | id (del reporte), ts (hora del navegador + latencia, D9), lecturas, texto, categoria, prob, accion, area, latencia_ms, error (null \| timeout \| conexion \| respuesta \| cola_llena); probs, umbral, entrada (D16) |
| `estado` (retenido) | core → web | estado, ultimo_evento |
| `cmd/recargar` | web → * | — |
| `salidas` (retenido) | sensores → web | ts, maquina, luz (verde\|amarilla\|roja\|null), zumbador, oled — estado real de las salidas, en sim y en la placa (D12) |
| `sim/inyectar` | pruebas → sensores | solo en modo sim: vib_g, temp_c, duracion_s |
| `sim/ajustar` (retenido) | web → sensores | solo en modo sim: vib_g, ruido_g, temp_c (null = automática), mpu_ok, ds18b20_ok (D15) |

Cualquier cambio a este contrato se consulta primero y se refleja aquí y en
`app/src/andon/common/topicos.py`.

## Modo simulado
- `ANDON_MODO=sim` cambia `hal/rpi.py` por `hal/sim.py`.
- `ANDON_MODO=hibrido` (D18): sensores de `hal/sim.py` (panel `/simulador`) y salidas reales
  (LEDs, zumbador, OLED) de `hal/rpi.py`. `sim/*`, `/simulador` y `/defensa` existen en sim e hibrido.
- La simulación genera muestras crudas de aceleración a 100 Hz (no el RMS ya
  calculado), para que el cálculo y los umbrales sean el mismo código que en la placa.
- En modo sim, las salidas (luces, zumbador, OLED) se publican en `salidas` y `/tablero`
  dibuja una torre virtual (también se publican en la placa).
- El modo por defecto es `rpi`; `sim/inyectar` se ignora fuera del modo sim. En la placa,
  el modo sim se activa solo con un *drop-in* de systemd de prueba, nunca en la receta (D11).
- Niveles: Docker (1 y 2), la RPi en modo sim con el Ollama real (3b) y la RPi con hardware (4).
  El nivel 3 (QEMU Debian arm64) se recortó (D17). Respaldo sin placa: `scripts/simulador-pc.sh`.
  Ver docs/plan.md, D11 y D17.
- La URL de Ollama va en la configuración: real (Docker o placa) o
  `tools/fake_ollama.py` (pruebas deterministas y `simulador-pc.sh`).

## Dependencias permitidas
- Biblioteca estándar primero (`urllib`, `sqlite3`, `json`, `threading`, `logging`).
- Terceros permitidos: `flask`, `paho-mqtt` (envuelto en `common/mqtt.py`,
  compatible con 1.x y 2.x), `smbus2`, `gpiod` (solo en `hal/rpi.py`).
- Pruebas: `pytest` (solo en desarrollo, no va a la imagen).
- Agregar cualquier otra dependencia requiere consultarlo: cada una es una receta de Yocto.

## Estructura
```
app/
  src/andon/
    common/    config, topicos, mqtt, logging
    hal/       base.py (interfaz), rpi.py, sim.py, ssd1306.py
    sensores/  lazo de 100 Hz, RMS, umbrales, paro
    core/      máquina de estados, cliente Ollama, registro SQLite
    web/       Flask, plantillas, /tablero
  config/      andon.conf
  deploy/      systemd/, mosquitto/, hostapd/, dnsmasq/
  tools/       fake_ollama.py, inyector de fallas, calibración
  tests/       unit/, contract/ (Ollama), oeqa/ (testimage de Yocto)
docker/        Dockerfile.dev, compose.yaml
docs/          plan.md, bitácora, entorno.md, yocto-requisitos.md, pruebas.md,
               decisiones/, evidencias/
```
Rutas instaladas: `/opt/andon`, `/etc/andon/andon.conf`, `/var/lib/andon`.
La receta `andon-app` instala la app; `make install DESTDIR=...` es opcional (D17).

## Comandos
- Entorno: `docker compose -f docker/compose.yaml up -d`
- Pruebas: `docker compose -f docker/compose.yaml run --rm dev pytest app/tests/unit`
- aarch64: `docker run --rm --platform linux/arm64 ...` (ver docs/pruebas.md)
- Inyectar falla: `mosquitto_pub -t andon/e1/sim/inyectar -m '{"vib_g": 2.0, "duracion_s": 5}'`

## Ramas, etiquetas y `main`
- Trabajo diario: ramas cortas `app/<tema>` que salen de `app/dev`.
  Se fusionan a `app/dev` solo con las pruebas en verde.
- Etiquetas en `app/dev`: `v0.9-sim` (fin del desarrollo) y `v1.0-rcN` (durante las
  pruebas). La receta de Yocto construye siempre desde una etiqueta.
- **`main` no recibe nada hasta que la app esté 100 % probada en la RPi 4**:
  cumplimiento de lo solicitado por el proyecto (RG-1 a RG-5 y requerimientos de la
  propuesta), verificado con la tabla de resultados de `docs/pruebas.md`.
  Fusionar a `main` es una decisión del usuario; nunca se hace por iniciativa propia.
- Commits: `tipo(ámbito): descripción [REQ-xxx]`,
  p. ej. `feat(sensores): paro por vibración [REQ-F07]`.

## Convenciones
- Código, identificadores, comentarios y documentación en español.

## Forma de trabajar
- Autonomía para crear, modificar y probar código, pruebas, configuración y
  documentación dentro de `app/`, `docker/` y `docs/`.
- **Consultar antes** de:
  - cambiar la arquitectura (procesos, responsabilidades, invariantes de seguridad);
  - cambiar el contrato MQTT;
  - agregar una dependencia;
  - desviarse de `docs/plan.md` (fases, alcance o recortes).
- No tocar `meta-andon/` ni `kas/`.
- Correr las pruebas antes de dar algo por terminado.
- **Al cerrar cada sesión:**
  1. marcar el avance en `docs/plan.md`;
  2. redactar la entrada de la sesión en la bitácora de `docs/`, siguiendo su
     plantilla, para que el usuario la revise.

## Resumen de requerimientos
- REQ-F01 vibración ≥ 100 Hz, RMS cada 1 s · REQ-F02 temperatura ≥ 1 Hz
- REQ-F03 formulario web, texto ≤ 280 · REQ-F04 estado (reporte + lecturas) → /v1/systemone
- REQ-F05 cinco categorías · REQ-F06 área responsable · REQ-F07 paro por umbral sin modelo
- REQ-F08 luz amarilla si baja confianza · REQ-F09 torre de luces, zumbador, OLED
- REQ-F10 registro: fecha, lecturas, texto, categoría, probabilidad, acción, latencia
- REQ-F11 publicación MQTT · REQ-N01 sin Internet · REQ-N02 RPi + Yocto
- REQ-N03 Ollama y modelo preinstalados · REQ-N04 paro < 1 s · REQ-N05 meta ≤ 3 s por reporte
- REQ-N06 arranque automático (systemd) · REQ-N07 ningún GPIO > 3,3 V
- CU-01 operación normal · CU-02 paro por umbral · CU-03 falla que los sensores no ven
- CU-04 reporte de calidad · CU-05 reporte ambiguo · CU-06 reinicio tras paro
- CU-07 configuración de umbrales sin reiniciar
