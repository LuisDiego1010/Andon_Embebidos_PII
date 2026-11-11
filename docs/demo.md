# Guion de la demostración final

Demostración presencial (instructivo: «una demostración de la aplicación, así como el flujo de síntesis
del sistema operativo y descripción de la aplicación y las recetas generadas»; propuesta, hito H6:
«Casos de uso en vivo y explicación del flujo Yocto»).

Duración objetivo: **≈ 20 min** más preguntas. Los tiempos se ajustan en el ensayo (paso B7 del plan).

## Antes de entrar (en la placa, 15 min antes)

1. Encender la placa. El modelo tarda ≈ 38 s en cargarse; los servicios arrancan solos.
2. `sh /opt/andon/modo.sh sim`.
3. Celular del «operario» conectado a `Andon-E1` → `http://192.168.4.1:5000`.
4. Laptop: `/tablero` y `/simulador` abiertos; en otra pestaña, `/defensa`.
5. Un reporte de prueba para confirmar que el modelo ya está cargado.
6. Tener a mano: la frase de cada CU (§3), el PIN y este guion.

## 1. Problema y arquitectura (3 min)

- La estación Andon junto a una máquina: combina sensores (vibración y temperatura) con lo que el operario
  escribe, y señaliza, escala o detiene la máquina. Todo local, sin Internet.
- Diagrama de la propuesta: tres servicios que solo hablan por MQTT.
  - `andon-sensores`: único dueño del hardware y del lazo de seguridad.
  - `andon-core`: Ollama `tev1:0.8b` en `/v1/systemone`, Tabla 9 y registro SQLite.
  - `andon-web`: formulario y tablero.
- **Regla de diseño:** el paro de seguridad no depende del modelo (REQ-F07, REQ-N04).

## 2. Flujo Yocto y recetas (5 min)

Mostrar `andon.yml` y `meta-andon/` en la laptop.

| Pieza | Qué mostrar |
|---|---|
| `andon.yml` (kas) | Scarthgap; capas `poky`, `meta-openembedded` (oe, python, networking), `meta-raspberrypi`, `meta-andon`; `MACHINE = raspberrypi4-64`; systemd |
| `recipes-core/images/andon-image.bb` | La imagen: Python 3.12, Flask, paho-mqtt, smbus2, libgpiod, Mosquitto, Ollama, hostapd, dnsmasq |
| `recipes-ai/ollama/ollama-bin_0.40.13.bb` | Binario oficial arm64, solo el backend de CPU (se descartan ~2,2 GB de CUDA) |
| `recipes-ai/ollama/ollama-model-tev1_0.8b.bb` | El modelo preinstalado: sin descargas en la placa (REQ-N03) |
| `recipes-andon/andon-app/andon-app.bb` | La app desde este mismo repo, usuario `andon`, tres unidades systemd habilitadas (REQ-N06) |
| `recipes-connectivity/mosquitto/mosquitto_%.bbappend` | Hallazgo H1: Mosquitto ya no espera a la red, y todo arranca en 8,6 s |

- Comando: `KAS_CONTAINER_ENGINE=podman kas-container build andon.yml`; se graba con `bmaptool` (`README.md`).
- Si preguntan por la placa: la propuesta decía RPi 5 y se usó la RPi 4. El código es el mismo; solo cambia `MACHINE`.

## 3. Casos de uso en vivo (8 min)

El operario usa **su celular**; el público mira `/tablero` en la laptop o el proyector.

| CU | Quién y qué | Qué señalar |
|---|---|---|
| CU-01 | Nada: estación en verde | Lecturas en vivo; luz verde |
| CU-03 | Operario: «Huele a quemado y salió una chispa del cable de alimentación» | El contador del celular; ≈ 17 s; falla eléctrica → máquina detenida, aviso a mantenimiento |
| CU-06 | Supervisor: `/supervisor`, PIN, Reiniciar | Pide confirmación; «La máquina volvió a operar» |
| CU-04 | Operario: «Las piezas salen rayadas y fuera de especificación» | Amarilla, aviso a calidad, **la máquina sigue** |
| CU-05 | Operario: «Algo raro pasa, no sé qué es» | Confianza < 92 % → revisión manual, sin parar |
| CU-02 | `/simulador`: «Aspa desbalanceada» **mientras el modelo analiza otro reporte** | Paro en < 1 s aunque el modelo esté ocupado; queda retenido al normalizar |
| CU-06 | Supervisor reinicia **sin corregir la causa** y después corrigiéndola | «Se detuvo de nuevo» y luego «volvió a operar» |
| CU-07 | Administrador: bajar el umbral de vibración a 0,05 g | Se aplica en ≈ 1 s sin reiniciar; restaurar a 1 g |

Las frases son las verificadas en la placa (`docs/aceptacion.md`). Si el público propone una frase, usarla:
el resultado puede ser revisión manual, y eso muestra REQ-F08 funcionando.

## 4. Verificación automática (2 min)

`/defensa` → **Ejecutar todos** (≈ 1,5 min): 10 casos con esperado frente a obtenido y las barras de
probabilidad de las cinco categorías. Exportar el CSV.

## 5. Resultados y límites (2 min)

- Paro de seguridad: 340–375 ms con el modelo calculando (REQ-N04 ✅).
- **REQ-N05 no se cumple:** ≈ 17 s por reporte en la RPi 4 frente a la meta de 3 s. Mitigaciones:
  - flujo asíncrono (luz amarilla «Analizando…», la web no se bloquea);
  - modelo cargado al arrancar;
  - la seguridad no depende del modelo.
- Sensores simulados: el panel alimenta el **mismo código** que el hardware (muestras crudas a 100 Hz, RMS y
  umbrales). Queda listo para conectar sensores y LEDs (`docs/guia-hardware.md`).
- Registro de cada evento en SQLite (REQ-F10):
  `python3 -c "import sqlite3; [print(f) for f in sqlite3.connect('/var/lib/andon/andon.db').execute('select * from eventos order by id desc limit 3')]"`.

## Plan B

| Si… | Entonces |
|---|---|
| El Wi-Fi de la placa falla | Cable directo y túnel SSH (`docs/guia de uso.md` §3.2); el operario usa la laptop |
| El modelo no responde | Mostrar la revisión manual (REQ-F08) y la evidencia de `docs/evidencias/f7-defensa-placa-20261109.*` |
| La placa no arranca | `scripts/simulador-pc.sh --ollama-real` en la laptop, aclarando que es la misma app en un contenedor |
