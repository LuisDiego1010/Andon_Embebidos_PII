# Plan de ejecución — app de la Estación Andon

Última actualización: 2026-11-06

El trabajo se organiza en **fases**, no en días. Varias fases pueden avanzar en
una misma sesión. Una fase se da por cerrada cuando cumple su criterio de salida.

## Restricciones y fechas fijas
- **Placa (préstamo):** solo disponible entre semana. Las tareas marcadas
  🔌 requieren la RPi 4 y deben agendarse en días hábiles.
- **F0 a F6 terminadas antes del lunes 9.** Del lunes 9 al jueves 12 solo pruebas (F7).
- Tareas 🔌 de F2 y F3: jueves 5 o viernes 6. Si se atrasan, pasan al lunes 9
  y consumen tiempo de pruebas.
- **Lunes 9:** bitácoras individuales (PDF) y repositorio público (H5).
- **Miércoles 11, mediodía:** fecha límite para que la imagen Yocto arranque la app
  en la RPi 4 (ver Contingencia).
- **Demo:** semana del 9 de noviembre, fecha pendiente de confirmar con el profesor.
- **Hardware (sensores, torre, zumbador, ventilador):** sin fecha de llegada (6 nov). El
  desarrollo continúa en simulación (D11); las tareas 🔌 pasan al «Bloque hardware».
- Plataforma asumida: Yocto Scarthgap, Python 3.12 (pendiente de confirmación de Diego).

## Decisiones

| ID | Tema | Decisión | Estado / fase |
|---|---|---|---|
| D1 | Dueño del hardware | `andon-sensores` maneja todo el hardware; core envía órdenes | Cerrada |
| D2 | Comunicación entre servicios | MQTT local | Cerrada |
| D3 | `andon-web` | Proceso separado, comunica por MQTT (respaldo: Flask dentro de core) | Cerrada |
| D4 | Contrato con /v1/systemone | Formato fijado; timeout 45 s (medido en la RPi 4); calentamiento al arrancar; umbral 0,92 provisional; REQ-N05 no se cumple y se reporta (ver `decisiones/D4-contrato-systemone.md`); error → amarillo | Cerrada (umbral a reconfirmar en F4/F7) |
| D5 | OLED | Controlador propio sobre smbus2 (respaldo: sin OLED) | F2 |
| D6 | Simulación | Muestras crudas inyectables; Ollama real en Docker, falso en QEMU | Cerrada |
| D7 | Configuración y recarga | Archivo + aviso `cmd/recargar` | F4 |
| D8 | Acceso supervisor/admin | PIN en la configuración | F5 |
| D9 | Hora sin Internet | Hora del navegador enviada por el formulario | F5 |
| D10 | Tablero | MQTT + página `/tablero` | F5 |
| D11 | Estrategia sin hardware | App completa en simulación (rebanada completa primero); la RPi en modo sim (nivel 3b); QEMU de respaldo; modo sim seguro; tabla simulación/hardware (`decisiones/D11-estrategia-simulacion.md`) | Cerrada |
| D12 | Tópico `salidas` | Estado real de las salidas (retenido, sensores → web), en sim y en la placa (`decisiones/D12-topico-salidas.md`) | Cerrada |
| D13 | Falla de sensor | 2 s sin lectura válida → paro retenido, `sensor: "*_fallo"` (`decisiones/D13-falla-de-sensor.md`) | Cerrada |

## Niveles de prueba

| Nivel | Entorno | Sensores | Ollama | Valida |
|---|---|---|---|---|
| 1 | Docker `dev` (x86) | Sim | Real (contenedor) | Lógica, contrato, exactitud |
| 2 | Docker `--platform linux/arm64` | Sim | Falso | Compatibilidad aarch64 |
| 3 | QEMU (Debian arm64); respaldo sin placa, fines de semana | Sim | Falso | systemd, instalador, flujo completo |
| 3b | RPi 4 con la imagen Yocto, `ANDON_MODO=sim` (drop-in de prueba) | Sim | Real | systemd, REQ-N06, latencia real, contención de CPU (paro < 1 s con Ollama calculando) |
| 4 | RPi 4 real | Reales | Real | Latencia, umbrales, periféricos, demo |

## Entregables de la app

| Entregable | Archivo | Fase |
|---|---|---|
| Reporte del entorno de desarrollo | `docs/entorno.md` | F0 |
| Requisitos para la imagen Yocto (v1 y v2) | `docs/yocto-requisitos.md` | F1 y F6 |
| Guía de ejecución de pruebas, con tabla de resultados | `docs/pruebas.md` | Se escribe en F2–F6, se cierra en F6 |
| Registro de decisiones | `docs/decisiones/` | Al cerrar cada decisión |
| Bitácora de trabajo | `docs/` (plantilla propia) | Cada sesión |
| Código, configuración e instalador | `app/`, `docker/` | F1–F6 |
| Evidencias de pruebas | `docs/evidencias/` | F7 |

## Fases

### F0 · Entorno de desarrollo
Revisar las dependencias de la PC (Ubuntu), detectar faltantes o versiones
incompatibles e instalarlas. Claude Code no ejecuta `sudo`: revisa en modo
lectura y entrega los comandos de instalación; el usuario los ejecuta.

- [x] Sistema: versión de Ubuntu, arquitectura, núcleos, RAM, espacio libre (≥ 20 GB)
- [x] git
- [x] Docker Engine (≥ 24), plugin Compose v2, Buildx; usuario en el grupo `docker`
- [x] Emulación arm64 para contenedores (binfmt): `docker run --rm --platform linux/arm64 alpine uname -m` → `aarch64`
- [x] QEMU: `qemu-system-aarch64` (≥ 8.2), `qemu-utils`, `qemu-efi-aarch64` (firmware UEFI para arrancar la imagen Debian)
- [x] `cloud-image-utils` (`cloud-localds`, para configurar la imagen Debian de QEMU)
- [x] `mosquitto-clients`, `curl`, `make`, cliente SSH
- [x] Para la placa: herramienta para grabar la SD (`rpi-imager` o `bmaptool`)
- [x] Descarga de imágenes base: `python:3.12-slim`, `ollama/ollama`, `eclipse-mosquitto`

**Criterio de salida:** todo verificado y documentado en `docs/entorno.md`
(versión encontrada, versión requerida, estado).

### F1 · Base y contrato con el modelo
- [x] Estructura de carpetas de `app/`, `docker/` y `docs/`
- [x] `docker/Dockerfile.dev` (Python 3.12) y `docker/compose.yaml` (dev, ollama, mosquitto)
- [x] Descargar `tev1:0.8b` en el contenedor de Ollama
- [x] Prueba de contrato contra `/v1/systemone` con 15–20 reportes de ejemplo → **cierra D4**
- [x] `docs/yocto-requisitos.md` **v1**: configuración, paquetes, Ollama, QEMU, permisos y preguntas para Diego

**Criterio de salida:** `docker compose up` levanta los tres servicios; una
solicitud desde Python devuelve categoría y probabilidad; requisitos v1 entregados a Diego.

### F2 · Capa de hardware
- [x] `hal/base.py` (interfaz) y `hal/sim.py` (muestras a 100 Hz, inyección de fallas)
- [ ] 🔌 Raspberry Pi OS Lite 64 bits, I2C y 1-Wire habilitados, cableado
      (sustituido por la imagen Yocto de Diego: I2C y 1-Wire ya habilitados; falta cablear)
- [ ] 🔌 Pruebas rápidas: `i2cdetect` (0x68, 0x3C), DS18B20 en `/sys/bus/w1`, `gpioset` en MOSFET y LEDs
      (`probar_hal.py` ejecutado en la placa el 6 nov: GPIO e I2C abren, sensores ausentes; falta el hardware)
- [ ] 🔌 Ollama arm64 + `tev1:0.8b` en la placa: latencia de 20 solicitudes (REQ-N05)
      (Diego 5 nov: mediana 16,8 s; 6 nov: calentamiento 37 s y 16,9 s en caliente, sin diferencia entre `performance` y `ondemand`; ver D4)
- [x] `hal/rpi.py` (MPU-6050, DS18B20, MOSFET, LEDs, zumbador) — escrito y probado con dobles; validación 🔌 pendiente
- [ ] 🔌 Controlador SSD1306 → **cierra D5** (después de F3, tercero en el orden de recortes)
- [ ] 🔌 Registrar valores normales y en falla para calibrar
- [x] Sección de `docs/pruebas.md`: verificación de periféricos (procedimiento; resultados 🔌 pendientes)
- [x] `common/config.py` + `app/config/andon.conf`, `common/topicos.py`, `docs/hardware.md` (mapa de pines)

**Criterio de salida:** la simulación y la placa pasan las mismas pruebas de la interfaz.

### F3 · andon-sensores (lazo de seguridad)
- [x] `common/mqtt.py`: envoltorio de paho (1.x y 2.x), JSON, retenidos, reconexión
- [x] `sensores/rms.py`: RMS de la componente dinámica, ventana deslizante de 1 s evaluada cada 100 ms
- [x] `sensores/seguridad.py`: umbrales, paro retenido, falla de sensor → paro (D13), paro guardado en disco
- [x] Lazo de 100 Hz con reloj monotónico, DS18B20 en hilo aparte, publicación de `lecturas`
- [x] Recepción de `cmd/maquina`, `cmd/senal`, `cmd/recargar`, `sim/inyectar` (solo modo sim)
- [x] Publicación de `seguridad` y `salidas` (D12)
- [x] `__main__.py`, inyector de fallas (`tools/inyector.py`) y servicio `sensores` en `compose.yaml`
- [x] Paro medido < 1 s en simulación (≈ 200 ms desde la inyección; prueba en tiempo real)
- [x] Sección de `docs/pruebas.md`: CU-01 y CU-02 (simulación)
- [x] 3b: servicio en la RPi 4 en modo sim, con y sin Ollama calculando — paro 272–363 ms, 0 retrasos (6 nov; `docs/evidencias/f3-3b-rpi-sim.txt`)

**Criterio de salida:** CU-02 en simulación (Docker) ✅. La verificación en hardware pasa al Bloque hardware; 3b ✅ (6 nov).

### F4 · andon-core
- [ ] `tools/fake_ollama.py` (adelantado de F6: pruebas deterministas del core)
- [ ] Máquina de estados con pruebas por transición
- [ ] Cliente de Ollama (urllib) con timeout; error → amarillo; calentamiento al arrancar (D4)
- [ ] `__main__.py` de `andon.core`
- [ ] Umbral de confianza y Tabla 9
- [ ] Registro SQLite; publicación de `evento` y `estado`
- [ ] Configuración y recarga → **cierra D7**
- [ ] Nivel 2 (arm64) en verde
- [ ] Sección de `docs/pruebas.md`: CU-03, CU-04, CU-05

**Criterio de salida:** CU-03, CU-04 y CU-05 en Docker con el modelo real y con `fake_ollama`.

### F5 · andon-web
- [ ] Formulario (≤ 280 caracteres), resultado en pantalla, hora del navegador → **cierra D9**
- [ ] PIN; CU-06 y CU-07 → **cierra D8**
- [ ] `/tablero` con torre virtual → **cierra D10**
- [ ] `__main__.py` de `andon.web`
- [ ] Sección de `docs/pruebas.md`: CU-06, CU-07

**Criterio de salida:** CU-01 a CU-07 se ejecutan desde el navegador en simulación.

### F6 · Empaquetado y QEMU
- [ ] Instalador (`make install DESTDIR=...`)
- [ ] Unidades systemd; configuración de Mosquitto, hostapd y dnsmasq
- [ ] `config/andon-qemu.conf`
- [ ] 3b: la RPi 4 con la imagen de Diego en modo sim (drop-in de prueba); medir el paro < 1 s con Ollama calculando
- [ ] QEMU con Debian arm64: los servicios arrancan solos (REQ-N06); CU-01 a CU-07 en sim
- [ ] Pruebas `oeqa` para el `testimage` de Diego
- [ ] `docs/yocto-requisitos.md` **v2**: rutas, instalador, unidades, pruebas
- [ ] `docs/pruebas.md` **cerrada**: requisitos previos, procedimiento por nivel y por CU, tabla de resultados
- [ ] Etiqueta `v0.9-sim` en `app/dev`; entrega a Diego

**Criterio de salida:** niveles 3 y 3b en verde (3b si hay placa) y guía de pruebas lista para usar en la placa, con la tabla simulación/hardware.

### Bloque hardware (sin fecha: depende de la llegada del material)
Lo que solo se cierra con sensores y actuadores reales (D11). Se hacen en este orden.
- [ ] 🔌 Cableado y comprobación con herramientas del sistema (`i2cdetect`, `/sys/bus/w1`, `gpioset`)
- [ ] 🔌 `probar_hal.py` y `--salidas` con todo conectado; estado seguro del MOSFET (matar el proceso → ventilador detenido)
- [ ] 🔌 Registrar valores normales y en falla; calibrar umbrales (`tools/calibrar.py`)
- [ ] 🔌 CU-02 en hardware: aspa desbalanceada, paro medido < 1 s (REQ-N04)
- [ ] 🔌 Confirmar con Diego el mapa de pines (`docs/hardware.md`)
- [ ] 🔌 Controlador SSD1306 → cierra D5 (opcional)

### F7 · Pruebas (lunes 9 a jueves 12)
Se ejecuta siguiendo `docs/pruebas.md`. Sin desarrollo nuevo: solo correcciones,
cada una con su etiqueta `v1.0-rcN`.

- [ ] 🔌 App completa en la RPi 4 con Raspberry Pi OS; calibración de umbrales
- [ ] 🔌 CU-01 a CU-07 en hardware con evidencia (video y registro)
- [ ] 🔌 Latencia (REQ-N05) y exactitud del modelo con el conjunto de reportes
- [ ] 🔌 Imagen Yocto de Diego en la RPi 4: misma batería de pruebas
- [ ] 🔌 Regresión y ensayo de la demo

**Criterio de salida:** tabla de resultados completa, con todos los requerimientos verificados.

### F8 · Cierre
- [ ] Criterio de "100 % probada" cumplido (ver abajo)
- [ ] Fusión de `app/dev` a `main` (decisión del usuario)
- [ ] Bitácora completa en `docs/`; documentación final
- [ ] Etiqueta `demo`

## Criterio para fusionar a `main`
La app está "100 % probada" cuando cumple lo solicitado por el proyecto:
RG-1 a RG-5 del instructivo y los requerimientos de la propuesta, verificados en
la RPi 4 según la tabla de resultados de `docs/pruebas.md`. Hasta entonces, `main`
no recibe cambios. Riesgo aceptado: en la entrega de H5 (lunes 9) el trabajo
está en las ramas, no en `main`.

## Orden de recortes si no alcanza el tiempo
1. Ajuste de hora (D9)
2. Página `/tablero` → `mosquitto_sub`
3. OLED
4. Recarga en caliente → `systemctl restart`
5. Punto de acceso propio → router o hotspot de celular

No se recorta el núcleo mínimo: CU-02, CU-03 y CU-05 con registro.

## Contingencia Yocto
Si el miércoles 11 a mediodía la imagen Yocto no arranca la app en la RPi 4:
demo sobre Raspberry Pi OS, y la imagen Yocto se muestra por separado
(arrancando en QEMU o en la placa). En ese caso RG-3 no queda cumplido y la
fusión a `main` la decide el Director.
