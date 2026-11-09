# Traspaso y guía de continuación

Documento para que Eduardo, o Diego, retome el proyecto sin leer todo el historial.
Última actualización: **9 nov 2026**, al cerrar F5 y probar la app completa en la RPi 4 con la imagen
Yocto (rama `app/imagen-servicios`). El detalle por fase está en `docs/plan.md`; las pruebas y sus
resultados, en `docs/pruebas.md`.

## 0. Qué cambió el 9 nov (leer primero)

- **Decisión del equipo: la defensa se hace sin sensores físicos.** Los sensores se reemplazan por el
  panel `/simulador`, que alimenta el mismo código de producción (muestras crudas a 100 Hz, RMS,
  umbrales, paro). Hay que confirmar con el profesor que lo acepta: el instructivo pide sensores y
  actuadores. El hardware queda opcional (`docs/guia-hardware.md`).
- **F5 `andon-web` terminada** y **la app completa probada en la placa con el modelo real**:
  `probar_sin_hardware.py` 69/70 (el fallo se corrigió) y `/defensa` 10 de 10. Evidencias en
  `docs/evidencias/f7-*`.
- **La imagen Yocto ya arranca la app**: los tres servicios habilitados, H1 resuelto (todo arriba a
  los 8,6 s sin DHCP). La última imagen compilada (9 nov, 16:35) trae todo lo de esta rama.
- **Nada de esto está en `app/dev` todavía**: falta revisar y fusionar `app/imagen-servicios`.

## 1. Qué es y dónde estamos

Estación Andon: una RPi 4 junto a una máquina (ventilador DC) mide vibración (MPU-6050) y
temperatura (DS18B20), recibe reportes de texto del operario, los clasifica con Ollama
(`tev1:0.8b`, `/v1/systemone`) y señaliza o detiene la máquina. Todo local, sin Internet.
Tres servicios que solo hablan por MQTT: `andon-sensores` (único dueño del hardware y del lazo
de seguridad), `andon-core` (decisión, Ollama, SQLite) y `andon-web` (formulario, tablero,
supervisor, simulador y defensa).

| Fase | Estado | Qué quedó |
|---|---|---|
| F0 entorno · F1 base y contrato | ✅ | Docker, cliente `/v1/systemone`, D4 |
| F2 capa de hardware | ✅ en sim, dobles y placa sin sensores | `hal/base`, `hal/sim`, `hal/rpi`, OLED `hal/ssd1306` (sin probar en pantalla real) |
| F3 `andon-sensores` | ✅ en la placa | Lazo de 100 Hz, paro retenido, falla de sensor; reintento del MPU-6050 cada 0,5 s |
| F4 `andon-core` | ✅ en la placa | Estados, Tabla 9, SQLite, recarga; evento con probabilidades (D16) |
| F5 `andon-web` | ✅ en la placa | Formulario, `/tablero`, `/supervisor` (PIN), `/simulador` (D15), `/defensa` |
| F6 empaquetado | 🟡 | Unidades y receta listas y habilitadas; **falta** Wi-Fi para la demo, `make install`, QEMU, `oeqa` |
| Bloque hardware | ⏳ opcional | Cableado, calibración, OLED real, CU con sensores reales |

## 2. Por dónde seguir, en orden

1. **Revisar y fusionar `app/imagen-servicios` en `app/dev`** (`--no-ff`, pruebas en verde: 339 pasan,
   8 omitidas sin broker). Cambios en `app/` que conviene revisar con calma:
   `core/servicio.py` (hora del navegador, D9; evento con probabilidades, D16), `hal/rpi.py` (cerrojo
   del bus I2C, reintento del MPU-6050), `hal/sim.py` (`ajustar`, D15) y todo `web/`.
2. **Red para la defensa (decisión pendiente).** Hoy se llega a la placa por cable y túnel SSH.
   Para que el público o un celular abran la web: punto de acceso propio (hostapd y dnsmasq ya
   están en la imagen; falta configurarlos) o la placa como cliente del hotspot de un celular.
3. **Probar el arranque tras cortar la corriente** (REQ-N06): los servicios están habilitados y
   arrancan solos al encender, pero no se probó un corte de corriente con la app en marcha.
4. **Confirmar con el profesor** que acepta sensores simulados y la fecha de la demo.
5. **Antes de la entrega:** quitar `debug-tweaks` de `andon.yml` (root sin contraseña), cambiar el PIN
   `1234` en `andon.conf`, ajustar REQ-N05 en la propuesta (17 s medidos frente a la meta de 3 s).
6. **Opcional:** `make install` (la receta ya instala sin él), QEMU y `oeqa`, recalibrar el umbral de
   confianza (0,92) con más reportes, bloque hardware.

REQ-N05 (≤ 3 s por reporte) **no se cumple** y está reportado (D4): ≈ 17 s en la RPi 4. La mitigación
es el flujo asíncrono (luz amarilla durante el análisis, la web no se bloquea) y el calentamiento
del modelo al arrancar (~38 s). El paro de seguridad no depende del modelo: 340 ms medidos con el
modelo analizando.

## 3. La defensa

1. Placa con la imagen y la red (punto 2 de arriba). En la placa: `sh /opt/andon/modo.sh sim`.
2. Abrir `http://<placa>:5000/defensa`, ingresar el PIN y **Ejecutar todos** (≈ 1,5 min con el modelo
   real). Muestra salud del sistema, 10 casos con esperado frente a obtenido, la torre en vivo y las
   probabilidades del modelo en barras. **Exportar resultados** baja un CSV.
3. `http://<placa>:5000/simulador` para la parte libre: perillas de vibración y temperatura, sensores
   desconectados, reportes escritos a mano.
4. Al terminar: `sh /opt/andon/modo.sh real` (sin sensores, la máquina se detiene: es lo esperado).

Sin placa: `./scripts/simulador-pc.sh` levanta todo en un contenedor de la PC con Ollama falso
(`http://127.0.0.1:5000`). Sirve para probar la interfaz, no la latencia ni el modelo.

## 4. Contrato MQTT (prefijo `andon/e1/`, JSON)

Fuente de verdad en código: `app/src/andon/common/topicos.py`. Un cambio de contrato se acuerda
primero y se anota aquí, en `topicos.py` y en una decisión (ver D12, D14, D15, D16).

| Tópico | De → a | Campos |
|---|---|---|
| `lecturas` | sensores → * | ts, vib_rms_g, temp_c |
| `seguridad` (retenido) | sensores → core, web | ts, activo, sensor, valor, umbral |
| `cmd/maquina` | core, web → sensores | accion: parar \| reiniciar, origen. `reiniciar` solo se acepta con origen `web` |
| `cmd/senal` | core → sensores | luz: verde \| amarilla \| roja, zumbador, oled (lista de líneas) |
| `reporte` | web → core | id, texto (≤ 280), ts_navegador |
| `evento` | core → público | id, ts, lecturas, texto, categoria, prob, accion, area, latencia_ms, error (D14); probs, umbral, entrada (D16) |
| `estado` (retenido) | core → web | estado, ultimo_evento |
| `cmd/recargar` | web → * | origen |
| `salidas` (retenido) | sensores → web | ts, maquina, luz, zumbador, oled (D12) |
| `sim/inyectar` | pruebas → sensores | solo modo sim: vib_g, temp_c, duracion_s |
| `sim/ajustar` (retenido) | web → sensores | solo modo sim: vib_g, ruido_g, temp_c (null = automática), mpu_ok, ds18b20_ok (D15) |

`estado.estado` ∈ `calentando`, `reposo`, `analizando`, `atencion`, `detenida`, `paro_seguridad`.
`evento.accion` ∈ `ninguna`, `parar_maquina`, `avisar`, `revision_manual`, `paro_activo`,
`maquina_detenida`, `descartado`. `evento.ts` es la hora del navegador más la latencia (D9: la placa no
tiene hora fiable).

## 5. Invariantes de seguridad (no romper)

1. El paro por umbral se decide en `andon-sensores`, sin MQTT ni modelo, en < 1 s (REQ-N04).
2. Un paro retenido ignora órdenes de luz o arranque hasta `cmd/maquina reiniciar` de origen `web`
   (PIN validado por la web, CU-06). Sobrevive a reinicios (`paro.json`).
3. Ningún resultado del modelo arranca la máquina (el core solo ordena `parar`).
4. Si Ollama falla, agota el timeout (45 s) o la probabilidad < umbral → luz amarilla y revisión manual.
5. 2 s sin lectura válida de un sensor → paro retenido `mpu6050_fallo` / `ds18b20_fallo` (D13).
6. El simulador (`/simulador`, `sim/ajustar`, `sim/inyectar`) solo existe en modo sim; fuera de él la
   web responde 404 y `andon-sensores` no se suscribe (D11, D15).
7. La web no acepta umbrales que dejen el paro sin efecto: vibración ≤ 4 g (rango del MPU-6050
   configurado), temperatura ≤ 125 °C. El PIN se bloquea 30 s tras 5 intentos fallidos.

Tabla 9 (solo con probabilidad ≥ umbral): operacion_normal → verde · falla_mecanica y falla_electrica →
roja, se detiene, aviso a mantenimiento · problema_calidad → amarilla, aviso a calidad ·
material_faltante → amarilla, aviso a supervisión.

## 6. Cómo trabajar

**Pruebas en la PC.** Docker con `compose.yaml` como antes, o sin Docker con podman:
```bash
podman run --rm -v "$PWD":/work:ro,Z -w /work/app -e PYTHONPATH=/work/app/src -e PYTHONDONTWRITEBYTECODE=1 \
  docker.io/library/python:3.12-slim sh -c "pip install -q flask paho-mqtt smbus2 pytest && python -m pytest -p no:cacheprovider -q tests/unit"
```
- Con Docker, **siempre `--no-deps`** con `run`/`up`: `compose.yaml` fija Ollama 0.40.13 y, si el
  contenedor local es otro, Compose intenta bajar ≈ 8 GB (`docs/entorno.md`, punto 9).
- Las pruebas de integración usan un Mosquitto real y se omiten sin broker. Detener los servicios de
  compose antes de correr `pytest`; si no, chocan en el broker.
- En la red del TEC, los contenedores no llegan al puerto 80: `simulador-pc.sh` usa `apt` por HTTPS.

**Herramientas (`app/tools/`, instaladas en `/opt/andon/` de la imagen):**

| Herramienta | Para qué |
|---|---|
| `probar_sin_hardware.py` | En la placa, como root: modo real sin sensores y CU-01 a CU-07 con el modelo real; restaura todo al terminar. `--dejar-sim` deja el panel activo |
| `modo.sh sim\|real` | Cambia la placa entre sensores simulados y reales (drop-ins de `andon-sensores` y `andon-web`) |
| `calibrar.py` | Con hardware: registra lecturas y propone umbrales |
| `inyector.py`, `enviar_reporte.py` | Fallas temporales y reportes por MQTT, sin navegador |
| `fake_ollama.py` | Ollama falso y determinista (ignora las lecturas al clasificar) |
| `probar_hal.py`, `probar_calentamiento.py`, `copiar_a_sd.sh` | Periféricos, latencia del modelo, copiar la app a la SD |

**La placa.** Imagen: `KAS_CONTAINER_ENGINE=podman kas-container build andon.yml` desde el repo, con
`DL_DIR` y `SSTATE_DIR` apuntando a `../andon-yocto/build/` para no recompilar todo (≈ 5 min si solo
cambió la app). Grabar con `bmaptool` (`docs/pruebas-placa.md`).
- Con cable directo no hay DHCP: acceso por IPv6 link-local, `ssh root@fe80::<dirección>%<interfaz>`
  (se descubre con `ping -6 -I <interfaz> ff02::1`; la MAC de la Pi empieza con `d8:3a:dd`). `scp`
  necesita corchetes: `root@[fe80::...%<interfaz>]:/ruta`.
- **En la PC, NetworkManager corta esa conexión cada 5 min** porque reintenta DHCP en el cable.
  Antes de trabajar: `nmcli device set <interfaz> managed no` (vuelve a la normalidad al reiniciar).
- Para abrir la web de la placa en el navegador: `ssh -N -L 127.0.0.1:5050:127.0.0.1:5000 root@...`
  y `http://127.0.0.1:5050`.
- Para probar un cambio de `app/` sin regrabar: `tar -C app/src --exclude=__pycache__ -cf - andon |
  ssh root@... 'rm -rf /opt/andon/andon && tar -C /opt/andon -xof -'` y reiniciar los servicios.
- BusyBox: sin `head -N`. El reloj de la placa no es fiable (H2). Hallazgos H1–H3 en
  `docs/yocto-requisitos.md`.

**Git:** ramas cortas `app/<tema>` desde `app/dev`; se fusionan a `app/dev` con `--no-ff` solo con
las pruebas en verde. `main` no recibe nada hasta que la app esté 100 % probada en la RPi 4 (decisión
del usuario). Commits `tipo(ámbito): descripción [REQ-xxx]`. Añadir archivos con rutas explícitas
(no `git add docs`: las bitácoras individuales viven en `docs/`).

**Configuración:** `app/config/andon.conf` (→ `/etc/andon/andon.conf`, del usuario `andon`, 0640 por el
PIN). Se recarga sin reiniciar con `cmd/recargar` (D7); la web lo publica al guardar umbrales.
Rutas instaladas: `/opt/andon`, `/etc/andon/andon.conf`, `/var/lib/andon` (`paro.json`, `andon.db`).

## 7. Mapa de documentos

| Documento | Para qué |
|---|---|
| `docs/plan.md` | Fases, decisiones, niveles de prueba, avance |
| `docs/pruebas.md` | Procedimientos y resultados por CU, tabla simulación/hardware |
| `docs/decisiones/` | D4 (Ollama), D7 (configuración), D11 (simulación), D12 (`salidas`), D13 (falla de sensor), D14 (`evento`), D15 (simulador), D16 (probabilidades) |
| `docs/evidencias/` | Salidas reales de las pruebas (F3, 3b, F4, y las de la placa del 9 nov) |
| `docs/yocto-requisitos.md` | Lo que la app necesita de la imagen (v1 a v1.4) y hallazgos H1–H3 |
| `docs/guia-hardware.md` | Pasos para cuando llegue el material |
| `docs/hardware.md` | Mapa de pines, reglas de 3,3 V |
| `docs/entorno.md` | Estado del entorno de desarrollo y sus trampas |
| `docs/pruebas-placa.md` | Grabar la SD y verificar la imagen en la RPi 4 |
| `docs/registro-trabajo-diego.md` | Bitácora de Diego (imagen, integración, pruebas en placa) |
