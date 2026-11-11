# Guía de uso — Estación Andon con sensores simulados

Estado al **10 nov 2026**, con `app/dev` en el commit de fusión de `app/imagen-servicios` (trabajo de Diego, 9 nov).
Fuentes: `docs/plan.md`, `docs/traspaso.md`, `docs/pruebas.md`, `docs/decisiones/` (D11, D13, D15, D16) y el código de `app/`.

Contenido:
1. Cambios al plan
2. Qué corre en la laptop y qué corre en el embebido
3. Guía de uso de la aplicación simulada
4. Por qué la simulación se comporta como el sensor real
5. Lo que la simulación no demuestra

---

## 1. Cambios al plan

El plan original (`docs/plan.md`) suponía sensores reales, fases F0 a F6 antes del lunes 9 y pruebas (F7) del 9 al 12.

| # | Cambio | Cuándo / dónde | Efecto |
|---|---|---|---|
| 1 | **Plazo extendido hasta el viernes 13 nov.** Las fechas originales quedan como historia. | 9 nov, `plan.md` | Más margen para F6 y F7. |
| 2 | **La defensa se hace sin sensores físicos.** El panel `/simulador` reemplaza al MPU-6050 y al DS18B20 con el mismo código de producción. | 9 nov, decisión del equipo (D15) | El bloque hardware pasa a **opcional**. **Falta confirmarlo con el profesor**: el instructivo pide sensores y actuadores. |
| 3 | **Estrategia de simulación (D11):** app completa en simulación, nivel de prueba 3b (la RPi 4 en modo sim con el Ollama real), QEMU como respaldo, tabla simulación/hardware en `pruebas.md`. | 6 nov | La app se desarrolló sin esperar el hardware; las pruebas distinguen lo simulado de lo medido. |
| 4 | **F5 `andon-web` la terminó Diego** (rama `app/imagen-servicios`), con dos páginas extra: `/simulador` y `/defensa`. | 9 nov | F5 ✅. Fusionado a `app/dev` el 10 nov. |
| 5 | **Contrato MQTT ampliado:** D14 (`evento` con `id` y `error`), D15 (tópico `sim/ajustar`), D16 (`evento` con `probs`, `umbral`, `entrada`). `evento.ts` ahora es la hora del navegador más la latencia (D9). | 6 y 9 nov | Ratificado por el usuario al fusionar. La fuente de verdad es `common/topicos.py`. |
| 6 | **Imagen Yocto con la app activa:** los tres servicios habilitados, Mosquitto sin esperar la red (H1 resuelto con `bbappend` que quita `2895.patch`). Arranca todo a los 8,6 s sin DHCP. | 9 nov | REQ-N06 ✅ (falta probar un corte de corriente). |
| 7 | **OLED (D5):** controlador `hal/ssd1306.py` en hilo aparte, escrito y probado con dobles, sin pantalla real. | 9 nov | Una OLED ausente no afecta al paro de seguridad. |
| 8 | **REQ-N05 no se cumple:** ≈ 17 s por reporte en la RPi 4 frente a la meta de 3 s. Está reportado (D4). | 5–9 nov | Mitigación: flujo asíncrono con luz amarilla «Analizando…» mientras el modelo responde. |
| 9 | **F6 a medias:** quedan red para la demo (punto de acceso o hotspot), arranque tras corte de corriente y `yocto-requisitos` v2. | 10 nov | Ver el siguiente paso al final de este documento. |
| 10 | **Se recorta QEMU (nivel 3)** (D17): la imagen Yocto real ya corre en la RPi 4. Docker arm64 (nivel 2) se mantiene; `make install` y `oeqa` pasan a opcionales. | 10 nov | Respaldo sin placa: `simulador-pc.sh` y Docker. |

**Antes de la entrega:** cambiar el PIN `1234`, quitar `debug-tweaks` de la imagen (root sin contraseña) y ajustar REQ-N05 en la propuesta.

---

## 2. Qué corre en la laptop y qué corre en el embebido

### Idea central

El embebido (Raspberry Pi 4 con la imagen Yocto) es **el producto**: ahí viven los tres servicios, el broker y el modelo.
La laptop es el **puesto de trabajo**: compila, prueba, controla y mira. Solo en el modo «sin placa» la laptop también ejecuta una copia completa de la estación.

```
        LAPTOP (Ubuntu x86_64)                         EMBEBIDO (RPi 4, aarch64, Yocto)
 ┌──────────────────────────────┐              ┌──────────────────────────────────────────┐
 │ Navegador                    │   HTTP :5000 │  andon-web      (Flask, :5000)           │
 │  /defensa /simulador /tablero│◄────────────►│     │ MQTT                               │
 │  (por túnel SSH o por la red)│              │  Mosquitto 127.0.0.1:1883                │
 │                              │              │     │ MQTT          │ MQTT               │
 │ ssh / scp                    │     SSH      │  andon-sensores   andon-core             │
 │ kas-container (compila imagen)│────────────►│  (lazo 100 Hz,    (estados, Tabla 9,     │
 │ bmaptool (graba la SD)       │              │   paro, salidas)   SQLite, cliente HTTP) │
 │ pytest en Docker/podman      │              │     │                  │ HTTP local      │
 │ simulador-pc.sh (copia sim)  │              │  hal/sim.py o       Ollama + tev1:0.8b   │
 └──────────────────────────────┘              │  hal/rpi.py        (modelo real, local)  │
                                               └──────────────────────────────────────────┘
```

### En el embebido (lo que importa del proyecto)

| Componente | Qué hace | Notas |
|---|---|---|
| `andon-sensores` | **Único dueño del hardware.** Lazo de 100 Hz, RMS de 1 s, umbrales, paro retenido, falla de sensor (D13), torre, zumbador, OLED. | El paro se decide aquí, sin MQTT ni modelo, en < 1 s (REQ-N04). |
| `andon-core` | Máquina de estados, Tabla 9, cliente de Ollama, registro SQLite (`/var/lib/andon/andon.db`). | Si el modelo falla o duda → luz amarilla y revisión manual. Nunca arranca la máquina. |
| `andon-web` | Formulario, `/tablero`, `/supervisor` (PIN), `/simulador` y `/defensa` (solo modo sim). | Escucha en `0.0.0.0:5000`. |
| Mosquitto | Broker local. Los servicios hablan **solo** por MQTT. | Los servicios lo usan en `127.0.0.1:1883`. |
| Ollama + `tev1:0.8b` | Clasifica el reporte (`/v1/systemone`). | Preinstalado en la imagen; ≈ 17 s por reporte; ≈ 38 s de carga en frío. |
| systemd | Arranque automático de todo (REQ-N06). | `modo.sh sim` agrega un *drop-in* de prueba; la receta nunca activa el modo sim. |
| Herramientas en `/opt/andon/` | `modo.sh`, `probar_sin_hardware.py`, `probar_hal.py`, `calibrar.py`, `inyector.py`, `enviar_reporte.py`. | Se ejecutan como root en la placa. |

Esto solo se valida en la placa: **latencia real del modelo, paro < 1 s con la CPU ocupada por Ollama, arranque automático, permisos y persistencia**. La laptop no puede demostrarlo.

### En la laptop

| Qué | Para qué | Cómo |
|---|---|---|
| Desarrollo y pruebas unitarias | 347 pruebas | `docker compose -f docker/compose.yaml run --rm --no-deps dev pytest app/tests/unit` |
| Copia completa de la estación | Probar la interfaz sin placa | `./scripts/simulador-pc.sh` (podman o docker; Mosquitto + los tres servicios en un contenedor, con Ollama falso o el real del compose) |
| Navegador | Operar `/defensa` y `/simulador` en la placa | Túnel SSH o la red de la demo |
| Compilar la imagen | Yocto con `kas` | `KAS_CONTAINER_ENGINE=podman kas-container build andon.yml` (≈ 5 min si solo cambió la app) |
| Grabar la SD | Instalar la imagen | `bmaptool` (`docs/pruebas-placa.md`) |
| Acceso a la placa | SSH y copia de archivos | Cable directo con IPv6 link-local (ver §3.2) |

La copia de la laptop **no mide** la latencia ni el comportamiento del modelo real: usa `tools/fake_ollama.py`, que clasifica por palabras clave.

---

## 3. Guía de uso de la aplicación simulada

### 3.1 Sin placa: en la laptop

```bash
./scripts/simulador-pc.sh                       # Ollama falso: rápido y determinista
docker compose -f docker/compose.yaml up -d --no-deps ollama
./scripts/simulador-pc.sh --ollama-real --lan   # modelo real; accesible desde el celular
```

Usa `podman` si está instalado; si no, `docker`. Instala dependencias dentro del contenedor (la primera vez
tarda), levanta todo y avisa cuando está listo. Abrir **http://127.0.0.1:5000/simulador** con PIN `1234`.
Con `--lan`, el script imprime la dirección para el celular (misma red Wi-Fi que la laptop).
`Ctrl+C` detiene y borra el contenedor. El repositorio se monta en solo lectura: no se modifica nada.

Con el Ollama falso sirve para probar la interfaz y la lógica. Con `--ollama-real` también la clasificación
real, pero no la latencia de la placa: en la laptop el modelo responde en ≈ 4 s; en la RPi 4, en ≈ 17 s.
Es el entorno para ejecutar el guion de aceptación del operador (`docs/aceptacion.md`) sin placa.

### 3.2 Con la placa (la demo)

**Acceso** (hoy no hay red para público; ver F6):
1. Conectar la laptop a la RPi 4 con cable. Sin DHCP, el acceso es por IPv6 link-local:
   `ping -6 -I <interfaz> ff02::1` para descubrirla (la MAC empieza con `d8:3a:dd`) y luego `ssh root@fe80::<dirección>%<interfaz>`.
2. En la laptop, NetworkManager corta esa conexión cada 5 min: ejecutar antes `nmcli device set <interfaz> managed no`.
3. Túnel para el navegador: `ssh -N -L 127.0.0.1:5050:127.0.0.1:5000 root@...` y abrir `http://127.0.0.1:5050`.

**Activar el modo simulado** (en la placa, como root):
```sh
sh /opt/andon/modo.sh sim
```
Agrega los *drop-ins* de `andon-sensores` y `andon-web`, borra el paro retenido guardado, deja los controles en valores normales y reinicia los servicios.

**Defensa automática:**
1. Abrir `http://<placa>:5000/defensa`, ingresar el PIN y pulsar **Ejecutar todos** (≈ 1,5 min con el modelo real).
2. Muestra la salud del sistema, 10 casos con *esperado frente a obtenido*, la torre en vivo y las probabilidades del modelo en barras.
3. **Exportar resultados** descarga un CSV.

**Parte libre:** `http://<placa>:5000/simulador` (ver 3.3).

**Al terminar:**
```sh
sh /opt/andon/modo.sh real
```
Sin sensores conectados la máquina se detiene a los 2 s (D13): es lo esperado.

**Prueba completa en consola** (opcional, como root en la placa): `python3 /opt/andon/probar_sin_hardware.py` ejecuta CU-01 a CU-07 con el modelo real y restaura todo al final. `--dejar-sim` deja el panel activo.

### 3.3 Las páginas

| Ruta | Quién la usa | Qué hay |
|---|---|---|
| `/` | Operario | Formulario de reporte (≤ 280 caracteres). Envía la hora del navegador (D9). |
| `/tablero` | Todos | Torre virtual, lecturas, estado y **Últimos eventos**. |
| `/supervisor` | Supervisor | Con PIN: **Reiniciar** tras un paro (CU-06) y editar umbrales de vibración, temperatura y confianza mínima (CU-07, sin reiniciar). |
| `/simulador` | Solo modo sim | Perillas de sensores, escenarios, reportes, supervisor, torre y diagnóstico en una página. En producción responde 404. |
| `/defensa` | Demostración | Los 10 casos ejecutables con barras de probabilidad (D16) y exportación a CSV. |

**Controles de `/simulador`** (publican `sim/ajustar`, retenido; los valores persisten hasta que se muevan):

| Control | Rango | Efecto |
|---|---|---|
| Vibración (`vib_g`) | 0 a 3 g | RMS nominal de la señal generada. |
| Ruido (`ruido_g`) | 0 a 0,5 g | Ruido gaussiano de cada muestra. |
| Temperatura manual | 0 a 120 °C | Si no se marca, rige el modelo térmico. |
| MPU-6050 / DS18B20 conectado | sí / no | Desconectar lanza el mismo error que el hardware real. |

Botones de escenario: *Aspa desbalanceada* (2 g), *Sobrecalentamiento* (85 °C), *Desconectar MPU-6050*, *Desconectar DS18B20*, y reportes de ejemplo para CU-03, CU-04, CU-05 y falta de material. **Todo a normal y reiniciar** restablece todo.

### 3.4 Recetas por caso de uso

| Caso | Qué hacer | Esperado |
|---|---|---|
| CU-01 operación normal | No tocar nada. | Luz verde, lecturas ≈ 0,10 g y ≈ 33 °C. |
| CU-02 paro por vibración | *Aspa desbalanceada* (2 g > umbral 1 g). | Paro en < 1 s, luz roja, zumbador. **Queda retenido** aunque la vibración vuelva a normal. |
| CU-02 paro por temperatura | *Sobrecalentamiento* (85 °C > 60 °C). | Igual que el anterior. |
| Falla de sensor (D13) | *Desconectar MPU-6050* o *DS18B20*. | Paro retenido a los ≈ 2 s con `sensor: "mpu6050_fallo"` / `"ds18b20_fallo"`. |
| CU-03 falla que los sensores no ven | Reporte «Huele a quemado…». | Falla eléctrica (≈ 98 %) → roja, máquina detenida, aviso a mantenimiento. ≈ 17 s en la placa. |
| CU-04 calidad | Reporte «Las piezas salen rayadas…». | Amarilla, la máquina sigue, aviso a calidad. |
| CU-05 reporte ambiguo | Reporte «Algo raro pasa…». | Probabilidad < 0,92 → amarilla y **revisión manual**. |
| CU-06 reinicio | Tras un paro, PIN y **Reiniciar**. | PIN incorrecto: 403. Con 5 fallos, bloqueo de 30 s. PIN correcto: vuelve a verde. |
| CU-07 umbrales sin reiniciar | En `/supervisor` o `/simulador`, bajar el umbral de vibración y guardar. | Se aplica en ≈ 1 s por `cmd/recargar`. La web rechaza vibración > 4 g y temperatura > 125 °C. |

### 3.5 Problemas frecuentes

- **No abre la web de la placa:** revisar el túnel SSH y que el servicio esté activo (`systemctl status andon-web`).
- **La conexión SSH se cae cada 5 min:** falta `nmcli device set <interfaz> managed no`.
- **La máquina quedó detenida al salir del modo sim:** esperado en modo real sin sensores.
- **La primera consulta al modelo tarda ≈ 38 s:** carga en frío. El core calienta el modelo al arrancar (estado «calentando»); los reportes se atienden igual.
- **`/simulador` da 404:** la placa está en modo real; ejecutar `sh /opt/andon/modo.sh sim`.
- **BusyBox:** en la placa no existe `head -N`. El reloj no es fiable (H2), por eso se usa la hora del navegador.

---

## 4. Por qué la simulación se comporta como el sensor real

La simulación **no** inventa el resultado: genera lo que el sensor entregaría y deja que el código de producción lo procese.

### 4.1 Se simula lo mínimo: el chip, no el resultado

`andon-sensores` habla con una interfaz `HAL`. Solo cambia la implementación:

| Capa | Sim (`hal/sim.py`) | Real (`hal/rpi.py`) | ¿Mismo código? |
|---|---|---|---|
| Entrada | Muestras crudas `(ax, ay, az)` en g | Lectura I2C del MPU-6050, convertida a g | Interfaz idéntica |
| Lazo de 100 Hz con reloj monotónico | `sensores/servicio.py` | `sensores/servicio.py` | **Sí** |
| RMS de la componente dinámica, ventana de 1 s cada 100 ms | `sensores/rms.py` | `sensores/rms.py` | **Sí** |
| Umbrales, paro retenido, falla de sensor | `sensores/seguridad.py` | `sensores/seguridad.py` | **Sí** |
| Publicación MQTT (`lecturas`, `seguridad`, `salidas`) | igual | igual | **Sí** |
| Salidas (máquina, torre, zumbador, OLED) | Se registran y se publican | GPIO por libgpiod y OLED por I2C | Misma interfaz |

El simulador entrega **muestras crudas**, no el RMS ya calculado (D6). Por eso un error en el cálculo del RMS, en la ventana o en el umbral aparecería igual en simulación que en la placa.

### 4.2 El modelo físico imita al sensor

- **Aceleración:** vibración nominal repartida en los tres ejes como senoides de 25 Hz (ciclo entero por ventana de 1 s), más **gravedad de +1 g en z**, un **desvío de montaje** (0,02 g en x, −0,01 g en y) y **ruido gaussiano** en cada muestra.
- **RMS dinámico:** `rms.py` resta la media de cada eje en la ventana, como haría con el MPU-6050 real. Así la gravedad y el desvío de montaje no cuentan como vibración. Con la perilla en 0,10 g, el RMS medido sale ≈ 0,10 g (`test_rms_nominal`).
- **Máquina apagada:** solo queda ruido. La vibración inyectada existe mientras la máquina gira y desaparece con el paro, como un aspa desbalanceada que se detiene.
- **Temperatura:** modelo de primer orden hacia ambiente (apagada) o ambiente + calentamiento (encendida), **cuantizada a 0,0625 °C** como el DS18B20 de 12 bits. Sube gradualmente, no a saltos.
- **Lecturas inválidas:** un sensor «desconectado» lanza `ErrorHardware`, igual que `hal/rpi.py` ante un error de I2C, un CRC inválido o el valor de arranque de 85 °C. Eso activa la misma lógica de D13: 2 s sin lectura válida → paro retenido (medido: 2,1 s).

### 4.3 Las mismas pruebas para ambos

- `test_hal_interfaz.py` corre **las mismas pruebas** sobre `HalSim` y `HalRpi` (criterio de salida de F2): estado inicial, máquina, luz, zumbador, OLED, 1 g en reposo, temperatura plausible, cierre en reposo.
- `HalRpi` se prueba con dobles de `gpiod` y `smbus2` (`dobles_hw.py`).
- `test_hal_sim.py` verifica el modelo: RMS nominal, gravedad, máquina apagada, inyección, temperatura de primer orden, determinismo por semilla y sensor desconectado.
- `test_sensores_tiempo_real.py` mide el paro con hilos y reloj real.

### 4.4 El simulador corre sobre la plataforma real

El nivel 3b ejecuta el modo sim **en la RPi 4**, con systemd, Mosquitto y el Ollama real calculando. Así se mide lo que un PC no puede:

- La **contención de CPU:** con el modelo analizando (≈ 17 s con los 4 núcleos), el lazo de 100 Hz debe seguir deteniendo la máquina en < 1 s.
- Resultado: paro en **272–375 ms** (6 y 9 nov), 340 ms visto desde el navegador, 0 retrasos del lazo. La verificación posterior a la corrección del reintento del MPU-6050 (3 min) también reportó 0 retrasos.
- Lazo medido a 100,0 Hz sin atrasos en la PC.

### 4.5 La simulación no puede llegar a producción

- El modo por defecto es `rpi`. La receta nunca activa el modo sim (D11); solo lo hace `modo.sh sim` con un *drop-in* de prueba.
- Fuera del modo sim, `sim/inyectar` y `sim/ajustar` se ignoran, `/simulador` y `/api/sim/ajustar` responden 404, y `andon-sensores` ni siquiera se suscribe a esos tópicos (D11, D15).
- Cada perilla alimenta el mismo camino: muestras → RMS → umbrales → paro → MQTT.

---

## 5. Lo que la simulación no demuestra

Para no dar por probado lo que solo se simuló, `docs/pruebas.md` lleva dos columnas por requisito (simulación y hardware). Está **pendiente de hardware**:

| Pendiente | Por qué la simulación no lo cubre |
|---|---|
| **Umbrales reales** (hoy 1,0 g y 60 °C, provisionales) | Solo se calibran con el ventilador real (`calibrar.py`, `docs/guia-hardware.md`). |
| **Jitter y ruido reales del I2C** | El sim tiene ruido gaussiano ideal; el bus real tiene su propia latencia y errores. |
| **Espectro real de la vibración** | El sim usa una senoide de 25 Hz. El ventilador real tiene otro contenido en frecuencia, y el MPU-6050 aplica un filtro de 44 Hz que el sim no modela. |
| **Fallas con forma física** | La perilla de vibración fija el RMS directamente; no calcula el desbalance de un aspa. Con temperatura manual, el valor salta de golpe, sin la inercia térmica del modelo automático. |
| **Clones del MPU-6050** | La app rechaza a propósito un `WHO_AM_I` distinto de 0x68. |
| **REQ-N07, pines, cableado y estado seguro del MOSFET** | Es eléctrico (`docs/hardware.md`). |
| **OLED real** | El controlador solo se probó con dobles (D5). |
| **Modelo con lecturas reales** | Se validó el texto de los reportes, no la influencia de lecturas reales. |

Estado de REQ-N04 y REQ-F07: ✅ en simulación y 🟡 en hardware, porque falta el paro medido sobre sensores reales.
**La simulación valida la lógica, la plataforma y la latencia del software; no valida los chips ni el cableado.** Conviene decirlo abiertamente al profesor al pedirle que acepte sensores simulados.

---

## 6. Siguiente paso

F6: red para la demo (punto de acceso con hostapd/dnsmasq o hotspot de celular) y prueba de corte de corriente (REQ-N06). Opcionales: `make install` y `oeqa` contra la placa. QEMU se recortó (D17). Antes de la entrega: cambiar el PIN y quitar `debug-tweaks`.
