# Estación Andon Inteligente de Borde con Yocto Project y Ollama

**Institución:** Instituto Tecnológico de Costa Rica, Escuela de Ingeniería Electrónica
**Curso:** EL5841 Taller de Sistemas Embebidos · II Proyecto: Sistemas Inteligentes de Borde (EdgeAI)
**Profesor:** Dr. Ing. Johan Carvajal Godínez
**Integrantes:**
* José Eduardo Tencio Solano · Director de proyecto y auditor de calidad (aplicación)
* Luis Diego García Rojas · Líder técnico (arquitecto) e investigador (imagen Yocto)

## 1. Visión general del proyecto

La estación Andon es un nodo embebido que se instala junto a una máquina de producción (en el prototipo, un
ventilador DC). Combina lo que miden los sensores (vibración y temperatura) con los reportes de texto libre
que escribe el operario desde su celular, clasifica la falla con un modelo de decisión local y actúa:
enciende la torre de luces, avisa al área responsable o detiene la máquina. **Todo funciona sin Internet.**

- **Placa:** Raspberry Pi 4 (aarch64) con una imagen de Linux a la medida sintetizada con Yocto Project.
- **Modelo:** `tev1:0.8b` en Ollama, consultado por la API JEV (`/v1/systemone`), preinstalado en la imagen.
- **Red propia:** la placa crea el punto de acceso Wi-Fi `Andon-E1`; el operario abre la página en su celular.
- **Seguridad primero:** el paro por vibración o temperatura excesiva se decide localmente en menos de 1 s,
  sin depender del modelo. El modelo puede detener la máquina, pero nunca arrancarla.

| Pieza | Versión |
|---|---|
| Placa | Raspberry Pi 4, `MACHINE = raspberrypi4-64` |
| Yocto Project | 5.0 **Scarthgap** (LTS), Python 3.12, systemd |
| Ollama | 0.40.13 (binario oficial arm64, solo CPU) |
| Modelo | `tev1:0.8b` (772 M parámetros, Q8_0) |

## 2. Arquitectura

```
 Celular / laptop                       Raspberry Pi 4 (imagen Yocto)
 ┌───────────────────┐  Wi-Fi Andon-E1  ┌───────────────────────────────────────────────────────┐
 │ Reporte, Tablero, │ ◄── HTTP/JSON ──►│ andon-web (Flask :5000)                                │
 │ Supervisor        │  192.168.4.1     │     │                                                  │
 └───────────────────┘                  │ Mosquitto (127.0.0.1:1883) ◄──► andon-core ──► Ollama  │
                                        │     │                          (SQLite)     tev1:0.8b  │
                                        │ andon-sensores ── GPIO / I2C / 1-Wire                  │
                                        └───────────────────────────────────────────────────────┘
```

Tres servicios de Python, cada uno una unidad de systemd que arranca sola. **Solo se comunican por MQTT**:

| Servicio | Responsabilidad |
|---|---|
| `andon-sensores` | Único proceso que toca hardware. Lee la vibración a 100 Hz y la temperatura a 1 Hz, calcula el RMS de 1 s y **decide el paro de seguridad**, que queda retenido hasta un reinicio con PIN. Maneja luces, zumbador y pantalla |
| `andon-core` | Máquina de estados. Envía el reporte y las lecturas al modelo, aplica la tabla de decisión, guarda cada evento en SQLite y lo publica |
| `andon-web` | Formulario del operario, tablero, página del supervisor (reinicio y umbrales con PIN) y panel del simulador |

Decisión según la categoría que elige el modelo, **solo si su probabilidad es ≥ 0,92** (si no, o si el modelo
falla: luz amarilla y revisión manual, sin detener la máquina):

| Categoría | Luz | Máquina | Aviso a |
|---|---|---|---|
| `operacion_normal` | verde | sigue | — |
| `falla_mecanica` | roja | se detiene | mantenimiento |
| `falla_electrica` | roja | se detiene | mantenimiento |
| `problema_calidad` | amarilla | sigue | calidad |
| `material_faltante` | amarilla | sigue | supervisión |

Tópicos MQTT (prefijo `andon/e1/`, JSON): `lecturas`, `seguridad`, `salidas`, `estado` y `evento` publican el
estado de la estación; `reporte`, `cmd/maquina`, `cmd/senal` y `cmd/recargar` transportan órdenes;
`sim/ajustar` y `sim/inyectar` solo existen en los modos con sensores simulados.

## 3. Requisitos

### PC para generar la imagen
* Linux x86_64 (probado en Ubuntu 26.04). Ruta del repositorio **sin espacios ni tildes**.
* 4+ núcleos, 8–16 GB de RAM y **~150 GB libres**.
* `git`, `curl`, `zstd`, `bmap-tools`, `podman` y `kas` (incluye `kas-container`):

```bash
sudo apt install -y git curl zstd bmap-tools podman kas
```

Se compila **dentro de un contenedor** (`kas-container`), así que la versión de Ubuntu de la PC no afecta a Yocto.

### Placa
* Raspberry Pi 4 (probada con 8 GB) y microSD de 16 GB o más.
* Hardware de salida de la demostración (opcional; ver §6.4): 3 LEDs, zumbador y pantalla LCD 16x2 con
  adaptador I2C (o una OLED SSD1306).

### PC de desarrollo (opcional)
* Docker o Podman, para las pruebas y para correr la estación completa sin placa (§7).

## 4. Estructura del repositorio

```
andon.yml                Configuración de kas: capas, versiones fijas y local.conf
meta-andon/              Capa Yocto propia
  recipes-core/images/andon-image.bb         La imagen completa (y la contraseña de root)
  recipes-ai/ollama/                         Ollama, el modelo precargado y su servicio
  recipes-andon/andon-app/                   La app (toma el código de app/) y sus servicios systemd
  recipes-connectivity/                      Mosquitto, hostapd y dnsmasq (punto de acceso)
app/
  src/andon/
    common/              Configuración, tópicos MQTT y cliente MQTT
    hal/                 Capa de hardware: rpi.py (real), sim.py (simulado), hibrido.py, pantallas
    sensores/            Lazo de 100 Hz, RMS y paro de seguridad
    core/                Máquina de estados, cliente de Ollama, decisión y registro SQLite
    web/                 Flask y las páginas
  config/andon.conf      Configuración instalada en /etc/andon/andon.conf
  deploy/red/            Punto de acceso: hostapd.conf, dnsmasq.conf, 10-wlan0.network
  tools/                 Herramientas para la placa (pruebas, cambio de modo, calibración)
  tests/                 Pruebas unitarias y de contrato con el modelo
docker/                  Entorno de desarrollo (Python 3.12, Mosquitto y Ollama)
scripts/
  empacar-modelo.sh      Descarga tev1:0.8b y lo empaqueta para la imagen
  verificar-imagen.sh    En la placa: comprueba que la imagen tiene lo que la app necesita
  simulador-pc.sh        La estación completa en la PC, sin placa
docs/
  decisiones/            Registro de decisiones de diseño
  evidencias/            Resultados de las pruebas en la PC y en la placa
```

## 5. Generar e instalar la imagen

### 5.1 Compilar

```bash
git clone https://github.com/LuisDiego1010/Andon_Embebidos_PII.git
cd Andon_Embebidos_PII

# 1. Modelo (una sola vez, ~1 GB; no se sube a git)
./scripts/empacar-modelo.sh

# 2. Compilar (la primera vez tarda horas; después, minutos)
KAS_CONTAINER_ENGINE=podman kas-container build andon.yml 2>&1 | tee compilacion.log
```

Resultado: `build/tmp/deploy/images/raspberrypi4-64/andon-image-raspberrypi4-64.rootfs.wic.bz2`

### 5.2 Grabar la microSD

```bash
lsblk                                   # identificar la tarjeta (¡no el disco del sistema!)
sudo umount /dev/sdX*
cd build/tmp/deploy/images/raspberrypi4-64/
sudo bmaptool copy andon-image-raspberrypi4-64.rootfs.wic.bz2 /dev/sdX
```

### 5.3 Primer arranque

1. Insertar la microSD y encender la placa. Los servicios arrancan solos; el modelo tarda ≈ 40 s en cargarse.
2. Conectarse a la red Wi-Fi **`Andon-E1`** (clave inicial `andon-e1-demo`).
3. Entrar por SSH: `ssh root@192.168.4.1`. Por cable Ethernet directo también sirve
   `ssh root@raspberrypi4-64.local`. La contraseña de root la entrega el equipo.
4. **Cambiar las credenciales de fábrica**, porque este repositorio es público:

```bash
passwd                                                   # contraseña de root
vi /etc/hostapd.conf      && systemctl restart hostapd   # wpa_passphrase: clave de la red Wi-Fi
vi /etc/andon/andon.conf  && systemctl restart andon-web # [web] pin: PIN del supervisor (inicial 1234)
```

5. Verificar la imagen y la aplicación (no necesitan sensores):

```bash
scp scripts/verificar-imagen.sh root@192.168.4.1:/root/   # desde la PC
sh /root/verificar-imagen.sh                              # en la placa: Python, bibliotecas, servicios, modelo
python3 /opt/andon/probar_sin_hardware.py                 # en la placa: servicios, permisos y CU-01 a CU-07
```

La placa no tiene salida a Internet: solo atiende a los equipos conectados a `Andon-E1`.

## 6. Guía de uso

### 6.1 Páginas (desde el celular o la laptop conectados a `Andon-E1`)

| Página | Quién | Para qué |
|---|---|---|
| `http://192.168.4.1:5000/` (o `http://andon.lan:5000/`) | Operario | Escribir qué pasa en la máquina (máx. 280 caracteres) y ver la decisión |
| `/tablero` | Todos | Lecturas, torre de luces, causa del paro y últimos eventos |
| `/supervisor` | Supervisor | Reiniciar la máquina tras un paro y cambiar umbrales, con PIN |
| `/simulador` | Pruebas | Mover los sensores simulados (solo en modo `sim` e `hibrido`) |
| `/defensa` | Pruebas | Ejecuta automáticamente los casos de uso y muestra esperado frente a obtenido (solo `sim` e `hibrido`) |

El modelo responde mejor a reportes **concretos**, que dicen qué se ve, oye o huele y dónde. Por ejemplo,
«Huele a quemado y salió una chispa del cable de alimentación» se clasifica como falla eléctrica con 98 %.

### 6.2 Modos de operación

```bash
sh /opt/andon/modo.sh real      # sensores y salidas reales (modo por defecto de la imagen)
sh /opt/andon/modo.sh hibrido   # sensores simulados desde /simulador; LEDs, zumbador y pantalla reales
sh /opt/andon/modo.sh sim       # todo simulado; la torre se ve en /tablero
```

El modo se guarda como un *drop-in* de systemd de prueba; la imagen siempre arranca en modo `real` salvo que
se active otro. En modo `real` sin sensores conectados, la estación entra en paro a los 2 s: es el
comportamiento esperado ante un sensor sin señal.

En los modos simulados no se inventa el resultado: se generan **muestras crudas** de aceleración a 100 Hz
(vibración de 25 Hz, gravedad, ruido) y temperatura con inercia térmica y la resolución del DS18B20. El cálculo
del RMS, los umbrales y el paro son el mismo código que con sensores reales.

### 6.3 Casos de uso

| CU | Cómo se prueba |
|---|---|
| CU-01 Operación normal | Estación en verde; un reporte normal no cambia nada |
| CU-02 Paro por umbral | `/simulador` → «Aspa desbalanceada» o «Sobrecalentamiento»: paro en < 1 s, luz roja y zumbador; queda retenido |
| CU-03 Falla que los sensores no ven | Reporte de olor a quemado o chispas: falla eléctrica → máquina detenida |
| CU-04 Problema de calidad | Reporte de piezas rayadas o fuera de medida: luz amarilla, aviso a calidad, la máquina sigue |
| CU-05 Reporte ambiguo | «Algo raro pasa, no sé qué es»: confianza baja → revisión manual |
| CU-06 Reinicio | `/supervisor` → PIN → Reiniciar. Si la causa sigue, la estación se vuelve a detener |
| CU-07 Umbrales | `/supervisor` → cambiar umbral con PIN: se aplica en ≈ 1 s sin reiniciar servicios |

### 6.4 Conexión del hardware

Numeración BCM. Conectar siempre con la placa apagada. **Ningún GPIO puede recibir más de 3,3 V.**

| Señal | GPIO | Pin | Conexión |
|---|---|---|---|
| LED verde | 22 | 15 | GPIO → resistencia 330 Ω → LED → GND |
| LED amarillo | 27 | 13 | igual |
| LED rojo | 23 | 16 | igual |
| Zumbador (5 V) | 24 | 18 | GPIO → 1 kΩ → base de un 2N2222; emisor a GND; colector al (−) del zumbador; (+) a 5 V (pin 2) |
| Pantalla I2C | SDA 2, SCL 3 | 3, 5 | VCC a **3,3 V** (pin 1). LCD 16x2 con PCF8574 en `0x27` (`pantalla = lcd1602`) u OLED SSD1306 en `0x3C` (`pantalla = ssd1306`), en `[i2c]` de `andon.conf` |
| MPU-6050 (vibración) | SDA 2, SCL 3 | 3, 5 | I2C en `0x68`, a 3,3 V |
| DS18B20 (temperatura) | 4 | 7 | 1-Wire, resistencia de 4,7 kΩ entre datos y 3,3 V |
| MOSFET del ventilador | 17 | 11 | Activo en alto, resistencia de 10 kΩ de la compuerta a GND |

La demostración usa el **modo híbrido**: LEDs, zumbador y pantalla reales, con los sensores simulados.

## 7. Desarrollo y pruebas sin placa

```bash
# Pruebas unitarias (Python 3.12 en Docker)
docker compose -f docker/compose.yaml build dev
docker compose -f docker/compose.yaml run --rm --no-deps dev pytest app/tests/unit

# La estación completa en la PC, con un modelo falso
./scripts/simulador-pc.sh                      # abrir http://127.0.0.1:5000/simulador (PIN 1234)

# Con el modelo real y acceso desde el celular en la misma red
docker compose -f docker/compose.yaml up -d --no-deps ollama
./scripts/simulador-pc.sh --ollama-real --lan
```

## 8. Resultados principales

| Requisito | Resultado en la Raspberry Pi 4 |
|---|---|
| Paro por umbral < 1 s (REQ-N04) | Decisión en < 1 ms desde la lectura; visible en la web en ≈ 0,36 s, también con el modelo calculando |
| Clasificación en ≤ 3 s (REQ-N05) | **No se cumple:** ≈ 17 s por reporte (≈ 4 s en una PC x86). Se mitiga con flujo asíncrono, modelo cargado al arrancar y seguridad independiente del modelo |
| Arranque automático (REQ-N06) | Todos los servicios arrancan solos; tras un corte de corriente el paro retenido se conserva y la base de datos queda íntegra |
| Sin Internet (REQ-N01) | Sin ruta por defecto ni conexiones salientes |
| Casos de uso | `/defensa` 10 de 10; guion de aceptación manual 31 ✅ 0 ❌ en la placa |
| Pruebas automáticas | 382 pruebas en verde |

Detalle y registros en [`docs/evidencias/`](docs/evidencias/); decisiones de diseño en
[`docs/decisiones/`](docs/decisiones/).

**Decisiones de la imagen:**
* **Ollama precompilado.** No existe capa oficial de Ollama para Yocto: se empaqueta el binario oficial y se
  descartan las bibliotecas CUDA (~2,2 GB) que la placa no usa.
* **Modelo dentro de la imagen.** La estación funciona sin Internet desde el primer arranque (REQ-N03).
* **Ollama y Mosquitto solo en `127.0.0.1`.** Desde la red solo se alcanza la web.
* **Mosquitto no espera a la red.** Todos los servicios arrancan en ≈ 9 s.
* **App desde el mismo repositorio.** La receta `andon-app` toma `app/` con `externalsrc`.
* **Sin `debug-tweaks`.** Root entra con contraseña.

## 9. Declaración de uso de Inteligencia Artificial

De acuerdo con la normativa del curso, se declara el uso de herramientas de Inteligencia Artificial
Generativa durante el desarrollo del proyecto:

* **Modelo empleado:** Claude (Anthropic), mediante Claude Code.
* **Alcance de la asistencia:**
  * Descubrimiento del formato de la API JEV (`/v1/systemone`) a partir de sus mensajes de error y diseño del
    cliente de Ollama con manejo de fallos.
  * Diseño de la arquitectura de tres servicios comunicados por MQTT y de los invariantes de seguridad.
  * Desarrollo del lazo de seguridad de 100 Hz (`andon-sensores`): cálculo del RMS, paro retenido y detección
    de sensores sin señal.
  * Desarrollo de la capa de hardware: controlador con libgpiod v2, simulador de sensores con muestras crudas,
    modo híbrido y controladores de las pantallas OLED y LCD.
  * Desarrollo de `andon-core` (máquina de estados, tabla de decisión, registro SQLite) y de `andon-web`
    (formulario, tablero, supervisor, simulador y página de verificación).
  * Estructuración de la capa `meta-andon`: recetas de Ollama, del modelo y de la aplicación, servicios
    systemd, punto de acceso Wi-Fi y ajustes de arranque.
  * Elaboración de pruebas unitarias, de contrato y de aceptación, y de los scripts de verificación en la placa.
  * Diagnóstico de la latencia del modelo en la Raspberry Pi 4 e interpretación de las mediciones.
  * Apoyo en la redacción y estructuración de la documentación técnica.
