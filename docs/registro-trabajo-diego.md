# Registro de trabajo · Imagen Yocto e integración

**Proyecto:** II Proyecto EdgeAI · Estación Andon Inteligente de Borde · EL5841 Taller de Sistemas Embebidos, ITCR
**Autor:** Luis Diego García Rojas · roles: líder técnico (arquitecto de sistemas) e investigador
**Equipo:** Eduardo Tencio (director de proyecto · auditor de calidad)
**Periodo:** 23 de octubre – 12 de noviembre de 2026

Este documento reúne lo trabajado en la propuesta, la imagen Yocto, la integración con la
app y las primeras pruebas en la placa. Sirve de base para las bitácoras por rol
(fecha, actividades, productos, problemas y referencias).

---

## 1. Resumen del estado

| Área | Estado |
| --- | --- |
| Propuesta de diseño (10 secciones de la rúbrica) | ✅ Entregada (26 oct) |
| Selección del modelo | ✅ `tev1:0.8b` para Raspberry Pi 4 de 8 GB |
| Capa `meta-andon` + configuración kas | ✅ Lista |
| Imagen Yocto compilada | ✅ 7410 tareas, 895 MB |
| Imagen arrancando en la placa | ✅ `verificar-imagen.sh`: 34 OK · 0 fallos · 3 avisos |
| Integración con la app (receta `andon-app`) | ✅ Tres servicios habilitados al arrancar; Mosquitto sin esperar la red (H1) |
| App completa en la placa, modelo real | ✅ `probar_sin_hardware.py` 69/70 (fallo corregido) · `/defensa` 10 de 10 (9 nov) |
| Latencia del modelo en la placa | ⚠️ ~15–17 s por clasificación (meta de la propuesta: ≤ 3 s) |
| Exactitud del modelo en la placa | ✅ 16/16 reportes claros |
| Aplicación (sensores, núcleo, web) | ✅ F0–F5 (Eduardo F0–F4; F5, simulador y defensa el 9 nov) |
| Hardware (sensores y actuadores) | ⏳ Opcional: la defensa se hará con sensores simulados (decisión del 9 nov) |

---

## 2. Registro por fecha

### 23 oct · Análisis del instructivo y elección de la aplicación

**Actividades**
- Análisis del instructivo del II Proyecto y de la rúbrica de la propuesta.
- Investigación de Ollama 0.35+ y del endpoint `/v1/systemone` (API Jev de TypeSafe):
  modelos de decisión que responden preguntas tipadas (`choice`, `noul`, `score`) con
  probabilidades.
- Revisión de las propuestas iniciales (agricultura y e-Health). Se descartaron por:
  - **Agricultura:** la decisión principal (riego) es numérica y la resuelve un `if`; el
    diagnóstico de plantas es visual, no textual.
  - **e-Health:** errores en el formato JSON de la API, escala ESI invertida y latencia
    sin respaldo.
- Elección de la **Estación Andon industrial**: el modelo interpreta texto libre del
  operario, que es justo lo que una regla no puede hacer.

**Inconsistencias detectadas en el instructivo**
- Menciona "JETSON NANO" en el objetivo 3, pero el resto habla de Raspberry Pi.
- Pide equipos de 3 personas y define 4 roles; el auditor no aparece en la tabla de
  responsabilidades.

### 24–26 oct · Propuesta de diseño

**Productos**
- Propuesta formal en LaTeX (`propuesta_andon.tex`, 15 páginas): justificación con 16
  referencias, problema, requerimientos (RG → REQ, 11 funcionales y 7 no funcionales),
  ConOps, 7 casos de uso, diagrama de secuencia, vista funcional (F1–F6), arquitectura,
  árbol de dependencias Yocto, estrategia de integración en 5 etapas (E1–E5), Gantt y
  conclusiones.
- Presentación Beamer para explicar la propuesta al profesor.
- Infografía de una página.

**Decisiones de arquitectura**
- **Dos lazos independientes:**
  - *Seguridad:* reglas fijas sobre vibración y temperatura, paro en < 1 s, nunca
    consulta al modelo.
  - *Diagnóstico:* reporte del operario + lecturas → `tev1` → categoría con probabilidad.
- **Umbral de confianza:** si la probabilidad es baja, luz amarilla y revisión humana.
- El modelo nunca puede impedir un paro ni reactivar una máquina detenida.

### 27 oct · Selección del modelo y cambio de placa

- La placa disponible es una **Raspberry Pi 4 de 8 GB** (no Pi 5). Se actualizaron la
  propuesta y la presentación: `MACHINE = "raspberrypi4-64"`, sin referencias al chip
  RP1 de la Pi 5.
- Análisis de los modelos de decisión de Ollama:

| Modelo | Base | Descarga | Exactitud media publicada | En una Pi 4 de 8 GB |
| --- | --- | --- | --- | --- |
| `nimble:9b` | Qwen3.5-9B | 9,3–9,5 GB | 75,7 % | No cabe: supera la RAM total |
| `tev1:4b` | Qwen3.5-4B | 4,4–4,6 GB | 73,3 % | Cabe, pero ocupa más de la mitad |
| **`tev1:0.8b`** | Qwen3.5-0.8B | 0,8–1,5 GB | 63,5 % | **Seleccionado:** margen amplio |

Criterios en orden: memoria, latencia en CPU, exactitud y entrenamiento para preguntas
`choice`. Se usa **un único modelo en ejecución**.

### 30 oct · Capa `meta-andon` y configuración kas

**Productos**
- `andon.yml` (kas): poky, meta-openembedded (meta-oe, meta-python, meta-networking) y
  meta-raspberrypi, todos en **scarthgap** con commits fijos. Configura systemd, I2C,
  1-Wire (GPIO4), UART, licencia del firmware Wi-Fi, `debug-tweaks` (solo desarrollo),
  salida `wic.bz2` + `wic.bmap` y `rm_work`.
- `ollama-bin_0.40.13.bb`: empaqueta el **binario oficial arm64** de Ollama.
  - Se revisó el contenido del paquete oficial: ~65 MB de backend de CPU y ~2,2 GB de
    bibliotecas CUDA. La receta **descarta CUDA** (la Pi no la usa).
  - Ollama elige solo la variante `libggml-cpu-armv8.0`, adecuada para el Cortex-A72.
  - Servicio systemd con usuario `ollama`, escucha solo en `127.0.0.1:11434`,
    `OLLAMA_KEEP_ALIVE=-1`.
- `ollama-model-tev1_0.8b.bb`: mete el modelo dentro de la imagen
  (`/var/lib/ollama/models`), sin descargas al arrancar.
- `andon-image.bb`: `core-image-base` + Ollama, modelo, i2c-tools, libgpiod, Python
  (flask, paho-mqtt, smbus2, gpiod), sqlite3, mosquitto, hostapd, dnsmasq.
- `scripts/empacar-modelo.sh`: descarga `tev1:0.8b` en la PC con una copia temporal de
  Ollama y lo empaqueta (no instala nada en el sistema).
- `scripts/probar-ollama.sh`: consulta JEV de prueba en la placa.

**Verificación:** `bitbake -n andon-image` (simulación sin ejecutar): 7410 tareas
planificadas sin errores de dependencias.

**Decisión:** no existe capa oficial de Ollama para Yocto; compilarlo implica Go más
llama.cpp con CMake. Empaquetar el binario oficial es más rápido y menos riesgoso.

### 2–3 nov · Reparación del sistema de desarrollo (Ubuntu)

Antes de compilar se encontró la PC de desarrollo con una **actualización de Ubuntu
24.04 → 26.04 interrumpida a la mitad**.

| Problema | Causa | Solución |
| --- | --- | --- |
| `apt` no instalaba nada ("dependencias incumplidas") | Fuentes en 26.04 y paquetes base en 24.04 (libc6 2.39, perl 5.38) | Terminar la actualización (`dpkg --configure -a`, `apt --fix-broken install`, `apt full-upgrade`) |
| `trying to overwrite '/usr/lib/x86_64-linux-gnu/libmpi.so.40'` | `libopenmpi40` (26.04) choca con `libopenmpi3t64` (24.04) | `dpkg -i --force-overwrite` solo de ese paquete |
| `sudo: No existe el archivo o el directorio` | En 26.04 `sudo` pasa a **sudo-rs**; el enlace `/usr/bin/sudo` se crea en la configuración que se cortó | Usar `/usr/bin/sudo.ws` para terminar de configurar |
| `trying to overwrite '/usr/lib/linux-tools/7.0.0-29-generic'` | `linux-tools` y `linux-cloud-tools` de 24.04 y 26.04 comparten carpeta | `dpkg -i --force-overwrite` de ambos paquetes juntos |
| La PC no arranca: `ALERT! UUID=… does not exist` en `(initramfs)` | Los archivos de arranque (initramfs) quedaron sin el driver NVMe | Arrancar desde USB con Ubuntu 26.04.1 (Rufus: GPT/UEFI, modo DD), `chroot` al disco, terminar la actualización, `update-initramfs -u -k all` y `update-grub` |

**Verificación:** arranque con kernel 7.0.0-42, Ubuntu 26.04.1 LTS, `sudo-rs` funcionando,
0 servicios fallidos, `nvme.ko` presente en los initramfs. Sin pérdida de datos.

**Lección:** Ubuntu 26.04 no está validado para scarthgap (probado hasta 24.04). Se
decidió compilar **dentro de un contenedor** (`kas-container` con podman), así la versión
de la PC no afecta a Yocto.

### 3 nov · Herramientas de compilación

- Instalados: kas 5.1 (incluye `kas-container`), podman 5.7.0.
- **Problema:** `Error: statfs …/Proyectos/Proyecto: no such file or directory`.
  **Causa:** la carpeta `Proyecto II` tenía un espacio; kas-container y Yocto no aceptan
  espacios en la ruta. **Solución:** renombrarla a `Proyecto_II`.

### 4 nov · Primera compilación de la imagen

```bash
KAS_CONTAINER_ENGINE=podman kas-container build andon.yml 2>&1 | tee compilacion.log
```

- Resultado: **7410 tareas, todas exitosas**. 6 avisos (pendientes de revisar).
- Imagen: `andon-image-raspberrypi4-64.rootfs.wic.bz2`, **895 MB** comprimida.
- Primer commit de la capa en el repositorio.

### 5 nov · Revisión de la app e integración

**Revisión de la rama `app-dev` (Eduardo)**
- Cliente de Ollama (`andon/core/ollama.py`) terminado: arma la consulta JEV, mide
  latencia y convierte cualquier falla en luz amarilla. Pruebas unitarias: 14 pasan,
  3 omitidas (contrato, requieren Ollama).
- Prueba de contrato en su PC (x86): 16/16 reportes claros, ~4,1 s por consulta,
  umbral de confianza subido a 0,92.

**Integración en un solo repositorio (`Andon_Embebidos_PII`)**
- Receta **`andon-app`**: toma el código de `app/` del mismo repo (`externalsrc`); usa
  `make install DESTDIR=…` cuando la app lo provea; crea el usuario `andon` y los grupos
  `i2c` y `gpio`; instala en `/opt/andon`, `/etc/andon` y `/var/lib/andon`; tres
  servicios systemd (`andon-sensores`, `andon-core`, `andon-web`), desactivados hasta
  que existan los módulos.
- Imagen: agregados `andon-app`, `mosquitto-clients` y `avahi-daemon`
  (`ssh root@raspberrypi4-64.local`).
- kas: I2C a **400 kHz** (`dtparam=i2c_arm_baudrate=400000`).
- Docker de desarrollo: Ollama fijado en **0.40.13**, igual que la imagen.
- Nuevos scripts para la placa:
  - `scripts/verificar-imagen.sh`: comprueba todo lo que la app pide a la imagen.
  - `scripts/medir-latencia.py`: latencia y exactitud con los mismos 19 reportes del
    contrato de Eduardo; guarda CSV.
- Documentos: `docs/pruebas-placa.md` (guía) y `docs/yocto-respuestas.md` (respuestas
  a las 6 preguntas de `docs/yocto-requisitos.md`).
- **Verificación:** `bitbake -n andon-image` con la receta nueva: 7427 tareas sin errores
  de dependencias; simulación del `do_install` de `andon-app` correcta.

**Primeras pruebas en la Raspberry Pi 4**
- Grabación con `bmaptool` en microSD de 29,8 GB (`/dev/sda`).
- Acceso: consola local (usuario `root`, sin contraseña) y SSH por red del laboratorio.

---

### 9 nov · App completa en la placa, simulador y defensa

**Actividades**
- Compilación de la imagen desde el repositorio (ya no desde `../andon-yocto`), reutilizando sus
  descargas y su caché: ≈ 500 tareas en vez de 7400.
- Receta `andon-app`: los tres servicios habilitados, `/etc/andon` del usuario `andon` (la web guarda
  los umbrales) y herramientas de prueba en `/opt/andon`.
- **H1 resuelto.** La espera de Mosquitto la introduce `2895.patch` de meta-openembedded; un drop-in
  no sirve porque systemd no permite quitar dependencias desde uno (`man systemd.unit`). Se quitó el
  parche con `mosquitto_%.bbappend`.
- F5 `andon-web` (formulario, tablero, supervisor con PIN), panel `/simulador` (D15), página
  `/defensa` con 10 casos ejecutables y evento con las probabilidades del modelo (D16).
- Controlador de la OLED SSD1306 y cerrojo del bus I2C compartido con el MPU-6050.
- Pruebas en la RPi 4 (cable directo, sin DHCP) y evidencias en `docs/evidencias/f7-*`.

**Decisiones**
- La defensa se hará sin sensores físicos: el simulador alimenta el mismo código de producción.
  Pendiente de confirmar con el profesor.

**Problemas y soluciones**

| Problema | Causa | Solución |
| --- | --- | --- |
| La conexión SSH con la placa se cortaba cada ~5 min | NetworkManager reintentaba DHCP en el cable y quitaba la dirección de la interfaz | `nmcli device set <interfaz> managed no` mientras se trabaja con la placa |
| El lazo de seguridad se retrasaba 1 s cada 10–25 s, solo sin MPU-6050 | Se intentaba iniciar el sensor 100 veces por segundo; en un bus I2C vacío ~1 de cada 1000 intentos espera el timeout del kernel (1 s) | Reintento cada 0,5 s; 0 retrasos en 3 min |
| `apt` no descargaba dentro de los contenedores | La red del TEC no deja pasar el puerto 80 desde ellos | `apt` por HTTPS |
| `localhost:5000` no respondía | `localhost` resolvía primero a IPv6 y la web escucha en IPv4 | Usar `127.0.0.1` |

### 12 nov · Aceptación en la placa y hardware real (trabajo en conjunto con Eduardo)

Sesión presencial en el laboratorio, Diego y Eduardo juntos, con la imagen final de la rama `app/imagen-final`
(punto de acceso `Andon-E1`, root con contraseña y sin `debug-tweaks`, modo híbrido D18).

**Actividades**
- Grabación de la microSD con `bmaptool` (3 min 27 s, verificada contra el `.bmap`) y arranque con
  acceso por SSH en enlace local IPv6.
- Fase 1: los 8 servicios activos y `verificar-imagen.sh` con 34 OK, 0 fallos (3 avisos por los sensores ausentes).
- B1: `probar_sin_hardware.py` 70/70 con el modelo real.
- B2: el celular se conectó a `Andon-E1` y recibió `192.168.4.14`.
- B3: guion de aceptación (`docs/aceptacion.md`, 33 pasos) automatizado con Playwright por un túnel SSH,
  con un celular emulado de 390 px y una pantalla de supervisor; U8 por SSH. Resultado: 31 ✅, 0 ❌, 2 ⚠️.
- B4: `/defensa` 10/10, con CSV y captura.
- B8: cableado de 3 LEDs, zumbador (2N2222 a 5 V) y pantalla. Prueba de cada salida por separado con
  `gpioset`. La pantalla resultó ser una LCD 16×2 con adaptador PCF8574 en 0x27; se escribió
  `hal/lcd1602.py` (opción `[i2c] pantalla`), con 9 pruebas nuevas (382 en verde). Secuencia de demo en
  modo híbrido confirmada en físico: paro → rojo y zumbador; reinicio → verde; calidad → amarillo;
  falla eléctrica → rojo, con los textos correctos en la LCD.
- B6: sin ruta por defecto ni conexiones salientes.
- B5: corte de corriente con paro retenido y un reporte en análisis: todo arrancó solo, el paro siguió
  retenido y `andon.db` quedó íntegra.
- Recompilación de la imagen con el driver de la LCD; commits y push de `app/imagen-final`.

**Decisiones**
- PIN `1234` y clave Wi-Fi `andon-e1-demo` se mantienen para la demo (coinciden con los guiones).
- La demo usa el modo híbrido: sensores del panel `/simulador`, salidas reales. No se compra el MPU-6050.
- El DHT11 queda fuera de esta entrega (requiere un overlay nuevo y cambia el rango de temperatura).

**Problemas y soluciones**

| Problema | Causa | Solución |
| --- | --- | --- |
| La primera pasada automática marcó 5 ❌ | El script leía el resultado anterior, que sigue en pantalla las décimas de segundo antes de «Analizando…» | Se confirmó cada respuesta en la tabla `eventos` de `andon.db`, se corrigió la espera y se repitieron los casos: todos ✅ |
| `i2cdetect` mostraba 0x27 y no 0x3C | La pantalla es una LCD de caracteres con PCF8574, no una OLED SSD1306 | Identificación por la luz de fondo y un texto de prueba; driver `lcd1602` |
| El reporte en análisis durante el corte se perdió | Estaba en memoria, en el modelo | Aceptado: el operario ve «No llegó respuesta a tiempo» con su texto y lo reenvía |
| `rpcbind` escucha en el puerto 111 de todas las interfaces | Viene en la imagen y la app no lo usa | Sin efecto en REQ-N01; quitarlo de la imagen |
| ⚠️ O5 y O7 terminan en revisión manual | Frases cortas (≈ 51 %) y «se acabaron los tornillos» (89–91 %, justo bajo 0,92) | Comportamiento seguro (REQ-F08); la demo usa frases concretas |

Evidencias: `docs/evidencias/b1-*`, `b3-aceptacion-placa-20261112/`, `b4-*`, `b5-*`, `b6-*`, `b8-*`.

## 3. Resultados en la placa

### 3.1 `verificar-imagen.sh` (E1, E2, E3)

**34 OK · 0 fallos · 3 avisos** (los avisos son sensores sin conectar).

| Comprobación | Resultado |
| --- | --- |
| Sistema | Poky 5.0.21 (scarthgap), kernel 6.6.63-v8, aarch64, 0 servicios fallidos |
| Memoria | 7808 MB totales, 7623 MB disponibles |
| Disco raíz | 1,7 GB libres de 2,9 GB |
| Python | 3.12; flask, paho-mqtt, smbus2, gpiod 2.1.3 (API v2), sqlite3, json, urllib |
| Ollama | 0.40.13 activo, API en 127.0.0.1:11434, modelo `tev1:0.8b` instalado |
| MQTT | mosquitto activo, publicar/suscribir correcto |
| Buses | `/dev/i2c-1` (grupo i2c), I2C a 400 kHz, overlay w1-gpio, bus 1-Wire activo, `gpiochip0` (grupo gpio) |
| App | usuario `andon` en `i2c` y `gpio`, código en `/opt/andon`, `import andon.core.ollama` correcto |
| Red | eth0 172.21.213.54/24, avahi activo |

Fallo menor del script corregido: BusyBox no acepta `head -1` → `head -n 1`.

### 3.2 `medir-latencia.py` (REQ-N05)

19 reportes del contrato, 1 ronda, CPU en modo `ondemand`.

| Medida | Valor |
| --- | --- |
| Carga del modelo + primera consulta | 38,1 s (solo al arrancar) |
| Latencia mínima / mediana / p90 / máxima | 16 418 / 16 804 / 17 440 / 17 472 ms |
| REQ-N05 (meta ≤ 3000 ms) | **No cumple** |
| Exactitud en reportes claros | **16/16 (100 %)** |
| Claros que irían a amarillo con umbral 0,92 | 1/16 (#16, probabilidad 0,91) |
| Ambiguos que irían a amarillo con umbral 0,92 | 3/3 (0,86–0,89) → CU-05 correcto |

Evidencia: `latencia-20261105-193340.csv`.

### 3.3 Diagnóstico de la latencia

| Prueba | Resultado |
| --- | --- |
| Temperatura de la CPU | 47,7 °C (sin estrangulamiento térmico) |
| Hilos de Ollama | 4 (todos los núcleos) |
| Modo de CPU por defecto | `ondemand` (600 MHz en reposo) |
| Con `performance` fijo a 1,5 GHz | **~15,2 s** por consulta (≈ 10 % mejor) |
| Descripciones de categorías cortas (una palabra) | **11,2 s** (≈ 27 % mejor), pero **clasificó mal**: `falla_mecanica` 0,85 para "olor a quemado cerca del motor" (con descripciones largas: `falla_electrica`) |

**Interpretación:** la latencia es casi constante entre reportes, así que depende del
trabajo fijo de cada consulta (largo de la pregunta y número de categorías), no del texto
del operario. Es coherente con los ~4,1 s en la PC de Eduardo (la Pi 4 es ~4 veces más
lenta en CPU).

**Hallazgo:** con la frase corta *"olor a quemado cerca del motor"* y sin lecturas de
sensores, la probabilidad bajó a **0,80** (iría a amarillo con umbral 0,92). Con la
redacción del reporte del contrato fue 0,98. Para la demo de CU-03 hay que usar una frase
que el modelo clasifique con seguridad, o revisar el umbral.

---

## 4. Impacto en la app y decisiones pendientes

| Tema | Acción |
| --- | --- |
| Timeout del cliente de Ollama (15 s) | **Subirlo a 30–45 s**: en la placa cada consulta tarda más de 15 s |
| Modo de CPU | Fijar `performance` al arrancar (receta o servicio) |
| Largo de la pregunta | Probar descripciones cortas y medir latencia y exactitud |
| Meta REQ-N05 | Ajustarla con lo medido (~20 s), argumentando: el paro de seguridad es independiente (< 1 s), el diagnóstico es a escala humana y la interfaz muestra "Analizando…" en amarillo |
| Frase de la demo CU-03 | Elegir una redacción con probabilidad > 0,92 |
| Disco raíz (2,9 GB) | Suficiente para pruebas; ampliar si crecen logs o la base de datos |
| 6 avisos de la compilación | Revisar con `grep WARNING compilacion.log` |

---

## 5. Pendientes

- [x] Prueba de descripciones de una palabra: más rápida (11,2 s) pero se equivoca.
- [ ] Probar descripciones de largo medio (una frase con las pistas clave) con los 19 reportes.
- [x] Pasar resultados y cambios a Eduardo (timeout, umbral, frase de CU-03): `docs/traspaso.md`.
- [x] Revisar los avisos de la compilación: las del 9 nov dan 1 solo, «Host distribution debian-13 has not
      been validated» (el contenedor de kas); no afecta a la imagen.
- [x] Hardware de la demo (12 nov): LEDs, zumbador y LCD reales en modo híbrido. Sin MPU-6050,
      DS18B20 ni ventilador: los sensores salen del panel /simulador (D18).
- [x] Recibir de la app: `__main__.py` de cada servicio (9 nov). `make install` y la configuración
      de hostapd y dnsmasq siguen pendientes.
- [x] Activar los servicios en la receta (`SYSTEMD_AUTO_ENABLE = "enable"`) y recompilar.
- [x] Pruebas CU-01 a CU-07 sobre la imagen Yocto (en modo sim, con el modelo real).
- [x] Red para la defensa: punto de acceso propio `Andon-E1` (12 nov).
- [x] Probar un corte de corriente con la app en marcha (REQ-N06): B5, 12 nov.
- [x] Quitar `debug-tweaks` (imagen final). El PIN de ejemplo se mantiene para la demo (decisión del 12 nov).
- [ ] Bitácoras por rol (líder técnico e investigador) y repositorio público final.

---

## 6. Referencias

- Ollama, biblioteca de modelos: [tev1](https://ollama.com/library/tev1) y
  [nimble](https://ollama.com/library/nimble).
- ModelSystem.One, *Ollama adds a local /v1/systemone endpoint and three Jev-style
  decision models* (2026): <https://modelsystem.one/news/ollama-systemone-decision-models/>
- Ollama, versión 0.40.13 (binario `ollama-linux-arm64.tar.zst`):
  <https://github.com/ollama/ollama/releases/tag/v0.40.13>
- meta-raspberrypi (BSP de Raspberry Pi para Yocto):
  <https://github.com/agherzan/meta-raspberrypi>
- Documentación de Yocto Project 5.0 (scarthgap): <https://docs.yoctoproject.org/5.0/>
- Documentación de kas: <https://kas.readthedocs.io/>
