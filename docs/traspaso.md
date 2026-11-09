# Traspaso y guía de continuación

Documento para que Diego, o Eduardo más adelante, retome la app sin leer todo el historial.
Última actualización: **6 nov 2026**, al cerrar **F4**. El detalle por fase está en
`docs/plan.md`; las pruebas y sus resultados, en `docs/pruebas.md`.

## 1. Qué es y dónde estamos

Estación Andon: una RPi 4 junto a una máquina (ventilador DC) mide vibración (MPU-6050) y
temperatura (DS18B20), recibe reportes de texto del operario, los clasifica con Ollama
(`tev1:0.8b`, `/v1/systemone`) y señaliza o detiene la máquina. Todo local, sin Internet.
Tres servicios que solo hablan por MQTT: `andon-sensores` (único dueño del hardware y del lazo
de seguridad), `andon-core` (decisión, Ollama, SQLite) y `andon-web` (formulario y tablero).

| Fase | Estado | Qué quedó |
|---|---|---|
| F0 entorno · F1 base y contrato | ✅ | Docker, cliente `/v1/systemone`, D4 |
| F2 capa de hardware | ✅ en sim y con dobles | `hal/base`, `hal/sim`, `hal/rpi` (sin sensores reales) |
| F3 `andon-sensores` | ✅ | Lazo de 100 Hz, paro retenido, falla de sensor; 3b en la RPi 4 ✅ |
| F4 `andon-core` | ✅ en Docker | Estados, Tabla 9, SQLite, recarga; **pendiente de probar en la placa** |
| F5 `andon-web` | ✅ en contenedor | Formulario, PIN, `/tablero`, umbrales; **pendiente de probar en la placa** (`tools/probar_sin_hardware.py`) |
| F6 empaquetado y QEMU | ⏳ | `make install`, unidades, QEMU, `oeqa`, `yocto-requisitos` v2, `v0.9-sim` |
| Bloque hardware | ⏳ sin fecha | Cableado, calibración, OLED (D5), CU con sensores reales |

Entrega para Diego: `docs/yocto-requisitos.md`, notas **v1.4** al final (`andon-core` ya existe).

## 2. Qué falta, en orden

1. **Probar `andon-core` en la placa (nivel 3b del core).** Pendiente. Procedimiento en
   `docs/pruebas.md`, «CU-03, CU-04 y CU-05»; mismo método que el 3b de `andon-sensores`
   (sección «Nivel 3b»). Esperado en la RPi 4: ≈ 17 s por reporte, luz amarilla «Analizando…»
   durante la consulta, el paro por umbral < 1 s aunque Ollama esté calculando, y que el
   directorio `/var/lib/andon` sea escribible para `andon.db`.
2. **F5 `andon-web`** (Flask): formulario ≤ 280 caracteres con la hora del navegador (D9), PIN de
   supervisor/admin validado en la web antes de publicar `cmd/maquina reiniciar` (D8), `/tablero`
   con torre virtual alimentada por `salidas`, `estado` y `evento` (D10), edición de umbrales con
   `cmd/recargar` (CU-07). El servicio `web` va en `compose.yaml` como `sensores` y `core`.
3. **F6:** instalador `make install DESTDIR=...` (el mismo para Raspberry Pi OS, QEMU y Yocto),
   unidades systemd, configuración de Mosquitto/hostapd/dnsmasq, `config/andon-qemu.conf`,
   QEMU Debian arm64 como respaldo, pruebas `oeqa`, etiqueta `v0.9-sim`.
4. **Bloque hardware:** cuando lleguen los sensores. Orden en `docs/plan.md`; mapa de pines y reglas
   de 3,3 V en `docs/hardware.md`; procedimiento en `docs/pruebas.md` («Verificación de
   periféricos»). Sin sensores, `andon-sensores` en modo `rpi` detiene la máquina a los 2 s (D13).
5. **Calibrar** umbrales de vibración/temperatura con valores reales y **recalibrar el umbral de
   confianza** (0,92, provisional) con más reportes, incluidos difíciles.
6. **Decisiones abiertas:** D5 (controlador OLED), D8–D10 (se cierran en F5), H1 (`wait-online` retrasa
   Mosquitto; `docs/yocto-requisitos.md`, hallazgos H1–H3), confirmar el mapa de pines con quien cablee.

REQ-N05 (≤ 3 s por reporte) **no se cumple** y está reportado (D4): ≈ 17 s en la RPi 4. La mitigación
es el flujo asíncrono (luz amarilla durante el análisis, la web no se bloquea) y el calentamiento
del modelo al arrancar. El paro de seguridad no depende del modelo.

## 3. Contrato MQTT (prefijo `andon/e1/`, JSON)

Fuente de verdad en código: `app/src/andon/common/topicos.py`. Un cambio de contrato se acuerda
primero y se anota aquí, en `topicos.py` y en una decisión (ver D12, D14).

| Tópico | De → a | Campos |
|---|---|---|
| `lecturas` | sensores → * | ts, vib_rms_g, temp_c |
| `seguridad` (retenido) | sensores → core, web | ts, activo, sensor, valor, umbral |
| `cmd/maquina` | core, web → sensores | accion: parar \| reiniciar, origen. `reiniciar` solo se acepta con origen `web` |
| `cmd/senal` | core → sensores | luz: verde \| amarilla \| roja, zumbador, oled (lista de líneas) |
| `reporte` | web → core | id, texto (≤ 280), ts_navegador |
| `evento` | core → público | id, ts, lecturas, texto, categoria, prob, accion, area, latencia_ms, error (D14); probs, umbral, entrada (D16) |
| `estado` (retenido) | core → web | estado, ultimo_evento |
| `cmd/recargar` | web → * | — |
| `salidas` (retenido) | sensores → web | ts, maquina, luz, zumbador, oled (D12) |
| `sim/inyectar` | pruebas → sensores | solo modo sim: vib_g, temp_c, duracion_s |
| `sim/ajustar` (retenido) | web → sensores | solo modo sim: vib_g, ruido_g, temp_c (null = automática), mpu_ok, ds18b20_ok (D15) |

`estado.estado` ∈ `calentando`, `reposo`, `analizando`, `atencion`, `detenida`, `paro_seguridad`.
`evento.accion` ∈ `ninguna`, `parar_maquina`, `avisar`, `revision_manual`, `paro_activo`,
`maquina_detenida`, `descartado`.

## 4. Invariantes de seguridad (no romper)

1. El paro por umbral se decide en `andon-sensores`, sin MQTT ni modelo, en < 1 s (REQ-N04).
2. Un paro retenido ignora órdenes de luz o arranque hasta `cmd/maquina reiniciar` de origen `web`
   (PIN validado por la web, CU-06). Sobrevive a reinicios (`paro.json`).
3. Ningún resultado del modelo arranca la máquina (el core solo ordena `parar`).
4. Si Ollama falla, agota el timeout (45 s) o la probabilidad < umbral → luz amarilla y revisión manual.
5. 2 s sin lectura válida de un sensor → paro retenido `mpu6050_fallo` / `ds18b20_fallo` (D13).

Tabla 9 (solo con probabilidad ≥ umbral): operacion_normal → verde · falla_mecanica y falla_electrica →
roja, se detiene, aviso a mantenimiento · problema_calidad → amarilla, aviso a calidad ·
material_faltante → amarilla, aviso a supervisión.

## 5. Cómo trabajar

**Entorno (PC Ubuntu x86, Docker):**
```bash
BUILDX_BUILDER=default docker compose -f docker/compose.yaml up -d --build   # primera vez
docker compose -f docker/compose.yaml run --rm --no-deps dev pytest app/tests/unit   # nivel 1
docker run --rm --platform linux/arm64 -v "$PWD":/work:ro -w /work -e PYTHONPATH=/work/app/src \
  -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim sh -c "pip install -q pytest paho-mqtt && python -m pytest -p no:cacheprovider -q app/tests/unit"   # nivel 2
```
- **Siempre `--no-deps`** con `run`/`up`: `compose.yaml` fija Ollama 0.40.13 y, si el contenedor
  local es otro, Compose intenta bajar ≈ 8 GB (`docs/entorno.md`, punto 9).
- Las pruebas de integración usan el Mosquitto de compose y se omiten sin broker. **Detener** los
  servicios `sensores` y `core` de compose antes de correr `pytest`; si no, chocan en el broker.
- Servicios en simulación: `docker compose -f docker/compose.yaml --profile sim up -d --no-deps sensores core`.
- Herramientas (`app/tools/`): `inyector.py` (fallas), `enviar_reporte.py` (hace de web),
  `fake_ollama.py` (Ollama falso y determinista), `probar_hal.py`, `probar_calentamiento.py`,
  `copiar_a_sd.sh` (copia la app a la SD de la imagen Yocto sin regrabarla).
- Modo simulado: `ANDON_MODO=sim` cambia `hal/rpi.py` por `hal/sim.py`. Por defecto es `rpi`, y
  `sim/inyectar` se ignora fuera de sim. En la placa el modo sim solo se activa con un *drop-in*
  de systemd de prueba, nunca en la receta (D11).

**La placa:** el cable directo no da DHCP; acceso por IPv6 link-local:
`ssh root@fe80::<dirección>%enp1s0f0` (sin contraseña; `scp` necesita corchetes:
`root@[fe80::...%enp1s0f0]:/ruta`). BusyBox: sin `head -N`. El reloj de la placa no es fiable.
Detalle y hallazgos H1–H3 en `docs/yocto-requisitos.md` y `docs/pruebas-placa.md`.

**Git:** ramas cortas `app/<tema>` desde `app/dev`; se fusionan a `app/dev` con `--no-ff` solo con
las pruebas en verde. `main` no recibe nada hasta que la app esté 100 % probada en la RPi 4 (decisión
del usuario). Commits `tipo(ámbito): descripción [REQ-xxx]`. Añadir archivos con rutas explícitas
(no `git add docs`: la bitácora individual vive en `docs/`). `meta-andon/` y `andon.yml` son de Diego.

**Configuración:** `app/config/andon.conf` (→ `/etc/andon/andon.conf`). Se recarga sin reiniciar con
`cmd/recargar` (D7). Rutas instaladas: `/opt/andon`, `/etc/andon/andon.conf`, `/var/lib/andon`
(`paro.json`, `andon.db`).

## 6. Mapa de documentos

| Documento | Para qué |
|---|---|
| `docs/plan.md` | Fases, decisiones, niveles de prueba, avance |
| `docs/pruebas.md` | Procedimientos y resultados por CU, tabla simulación/hardware |
| `docs/decisiones/` | D4 (Ollama), D7 (configuración), D11 (simulación), D12 (`salidas`), D13 (falla de sensor), D14 (`evento`) |
| `docs/evidencias/` | Salidas reales de las pruebas (F3, 3b, F4) |
| `docs/yocto-requisitos.md` | Lo que la app necesita de la imagen (v1 a v1.4) |
| `docs/hardware.md` | Mapa de pines, reglas de 3,3 V |
| `docs/entorno.md` | Estado del entorno de desarrollo y sus trampas |
| `docs/pruebas-placa.md` | Guía de Diego para probar la imagen en la RPi 4 |
