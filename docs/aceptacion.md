# Guion de aceptación del operador

Pruebas manuales, hechas por una persona como lo haría cada usuario del producto final: operario,
supervisor y administrador. Complementan a `/defensa` y `probar_sin_hardware.py`, que llaman a las APIs
desde código y no prueban la experiencia de uso.

El mismo guion se ejecuta **dos veces**:
- **Laptop:** estación completa en Docker con el modelo real (sin placa).
- **Placa:** RPi 4 con la imagen final, el celular conectado al punto de acceso `Andon-E1` (paso B3 del plan).

Anote en cada casilla ✅, ❌ o ⚠️ con una nota breve. Un ❌ se corrige antes de la demo.

## Preparación

**Laptop**
```bash
docker compose -f docker/compose.yaml up -d --no-deps ollama   # Ollama real con tev1:0.8b
./scripts/simulador-pc.sh --ollama-real --lan
```
- PC: `http://127.0.0.1:5000`.
- Celular: misma red Wi-Fi que la laptop, `http://<IP de la laptop>:5000`. El script imprime la dirección.
- Ctrl+C detiene todo; al volver a lanzarlo, la estación arranca limpia.

**Placa**
- `sh /opt/andon/modo.sh sim` en la placa.
- Celular conectado a `Andon-E1`: `http://andon.lan:5000` o `http://192.168.4.1:5000`.

**Dispositivos:** celular para el **operario**; laptop o tablet para el **supervisor**, con `/supervisor` y `/tablero`
abiertos al lado. El panel `/simulador` hace de máquina y sensores.

**Frases:** el modelo `tev1:0.8b` solo supera el umbral de confianza (0,92) con frases **concretas**, que digan
qué se ve, oye o huele **y dónde**. Las frases cortas, como las de la Tabla 5 de la propuesta, quedan entre 45 y 70 % y
terminan en revisión manual: es el comportamiento seguro (REQ-F08), pero no muestra el paro ni el aviso esperados.
Medido en la laptop el 11 nov (ver «Revisión» al final):

| Frase | Resultado |
|---|---|
| «Huele a quemado y salió una chispa del cable de alimentación» | Falla eléctrica 98,6 % → máquina detenida |
| «Olor a quemado cerca del motor, sale humo del cable de alimentación» | Falla eléctrica 95,5 % → máquina detenida |
| «Las piezas salen rayadas y fuera de especificación» | Calidad 99,9 % → aviso a Calidad |
| «Las piezas salen con rebaba y fuera de medida» | Calidad 99,8 % → aviso a Calidad |
| «Olor a quemado cerca del motor» (propuesta) | Falla eléctrica 68–70 % → revisión manual |
| «Las piezas salen con rebaba» (propuesta) | Falla mecánica 58 % → revisión manual |
| «Algo raro pasa, no sé qué es» | Falla mecánica 67–70 % → revisión manual (CU-05 correcto) |

Bajar el umbral no lo arregla: «olor a quemado cerca del motor» (70 %) y el reporte ambiguo de CU-05 (70 %) quedan
con la misma confianza. Anotar siempre la categoría y la confianza obtenidas.

---

## 1. Operario (celular, página «Reporte»)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| O1 | Abrir la página recién arrancada la estación | Aviso amarillo «cargando el modelo» mientras dura el calentamiento; desaparece solo |⚠️ no lo ví. asumo a que cargó rapido | ✅ aviso visible |
| O2 | Durante O1, enviar «Huele a quemado cerca del motor». En la laptop el calentamiento dura ~10 s: enviarlo apenas arranque; en la placa dura ~38 s | Contador «Analizando… N s» con el aviso de carga. Tarda más, pero **se clasifica**: no termina en «El modelo tardó demasiado» | ✅| ✅ 50,2 %, revisión manual en 37,6 s |
| O3 | CU-01: con todo normal, «La máquina funciona bien, sin novedades» | Verde o amarilla con revisión manual; la máquina sigue. Anotar categoría y % | ✅ Verde: Operación normal (100%) Sin acción Tiempo de respuesta: 4,2 s| ✅ Operación normal 100 % |
| O4 | CU-03: «Huele a quemado y salió una chispa del cable de alimentación». En la laptop se probó «olor a quemado cerca del motor» (propuesta) | Falla eléctrica → **Máquina detenida**, aviso a Mantenimiento, luz roja en el tablero. Anotar % y tiempo | ✅ Confianza 70,1 %. Luz amarilla. Tiempo 4 s| ✅ Falla eléctrica 98,7 %, detenida, 17,2 s |
| O5 | CU-03 con frase propia (p. ej. «salen chispas del cable») | Igual que O4. Anotar resultado | Falla eléctrica (45%), revisión manual, supervisor revisará, amarillo, 4 s| ⚠️ 50–51,5 %, revisión manual |
| O6 | CU-04: «Las piezas salen con rebaba y fuera de medida» y una frase propia de calidad. En la laptop se probó «las piezas salen con rebaba» (propuesta) | Calidad → luz amarilla, aviso a Calidad, la máquina sigue. Anotar % de cada una | Falla mecánica (58, 3%), revisión manual, máquina en marcha con revisión de supervisor, 4 s| ✅ 99,7 % y 99,9 %, aviso a Calidad |
| O7 | Material faltante: «se acabaron los tornillos en la línea» | Amarilla, aviso a Supervisión, la máquina sigue | ✅| ⚠️ 89–91,5 %, bajo 0,92: revisión manual |
| O8 | CU-05: «algo raro pasa, no sé qué es» | Revisión manual y «La máquina sigue en marcha; un supervisor revisará el reporte» |✅ | ✅ 67–69 %, revisión manual |
| O9 | Enviar un reporte y **recargar la página** mientras dice «Analizando…» | Tras recargar vuelve a «Analizando…» con el mismo texto y muestra el resultado al final | ✅| ✅ |
| O10 | Enviar un reporte y **apagar el Wi-Fi del celular** antes de que responda; reactivarlo a los 10 s | Mientras no hay red, sigue esperando. Al volver, muestra el resultado. Ningún mensaje en inglés | ✅| ✅ |
| O11 | Con el Wi-Fi apagado, pulsar «Enviar reporte» | «No hay conexión con la estación. Revise el Wi-Fi.»; el texto **no se borra** | ✅| ✅ |
| O12 | Escribir 280 caracteres con tildes y ñ | El contador llega a 280, no deja escribir más y el reporte se acepta | ✅ envié emojis al azar y los aceptó: operación normal (confianza 50%)| ✅ 280, aceptado |
| O13 | Texto con un emoji (p. ej. «la banda hace ruido 🔧») | Se acepta. El contador puede marcar 2 por emoji: es esperado |✅ | ✅ |
| O14 | Solo espacios | «Escriba qué está pasando.» | ✅| ✅ |
| O15 | Con paro de seguridad activo (ver S1), abrir «Reporte» | Aviso rojo con el motivo («vibración excesiva: …»). El reporte se puede enviar y responde «Paro de seguridad activo: no se actuó» | ✅| ✅ |
| O16 | Enviar 3 reportes seguidos desde 2 dispositivos | Todos reciben resultado, en orden. Ninguno se pierde | ✅| ✅ en orden (cola) |
| O17 | Legibilidad en el celular | Sin desplazamiento horizontal; botones fáciles de pulsar; porcentajes con coma decimal |✅ | ✅ 390 px |

## 2. Sistema (panel `/simulador`, hace de máquina y sensores)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| S1 | CU-02: botón «Aspa desbalanceada» (2 g) | Paro en < 1 s: luz roja, zumbador. El tablero dice «PARO DE SEGURIDAD: vibración excesiva: 1,15 g (límite 1,00 g)». El valor es el primero que cruzó el límite, por eso es menor que 2 | ✅| ✅ 0,36 s visto por la web |
| S2 | Volver la vibración a 0,1 g | **El paro sigue retenido** (rojo) hasta que lo libere el supervisor |✅ | ✅ |
| S3 | «Sobrecalentamiento» (85 °C) | Paro por temperatura con su motivo en °C | ✅| ✅ 0,54 s |
| S4 | «Desconectar MPU-6050» | Paro a los ~2 s: «MPU-6050 sin señal» |✅ | ✅ 2,12 s |

## 3. Supervisor (página «Supervisor», laptop o tablet)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| U1 | Con el paro de S1 activo, abrir la página | Estado «PARO DE SEGURIDAD» (no «paro_seguridad»), causa con valor y límite, lecturas y último reporte | ✅| ✅ |
| U2 | CU-06: PIN incorrecto y «Reiniciar» | Pide confirmación. Luego «PIN incorrecto.» y la máquina sigue detenida | ✅| ✅ |
| U3 | 5 PIN incorrectos seguidos | Al sexto intento: «Demasiados intentos. Espere 30 s.» |✅ | ✅ |
| U4 | **Con la causa todavía presente** (vibración en 2 g), PIN correcto y «Reiniciar» | «Verificando…» y luego «La máquina se detuvo de nuevo: vibración excesiva…». No dice «volvió a operar» |✅ | ✅ |
| U5 | Normalizar la causa (0,1 g) y reiniciar con el PIN correcto | «La máquina volvió a operar.»; la torre pasa a verde | ✅| ✅ |
| U6 | Después de O4 (máquina detenida por el modelo), reiniciar | Causa «falla reportada por el operario». Tras reiniciar, vuelve a operar | El modelo no la detuvo. Envió a revisión del supervisor con porcentaje de 68%| ✅ |
| U7 | En `/tablero`, revisar los eventos de baja confianza (O8) | Cada evento muestra hora, texto, categoría con %, acción, área y tiempo de respuesta | ✅| ✅ |
| U8 | Con la estación caída (detener el contenedor o `systemctl stop andon-web`), mirar `/tablero` | «Sin comunicación con la estación»; la torre se apaga, no queda congelada | ✅| ✅ |

## 4. Administrador (página «Supervisor», sección Umbrales)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| A1 | CU-07: vibración = 9 | «Vibración RMS máxima: debe ser mayor que 0 y como máximo 4.» El archivo no cambia |✅ | ✅ |
| A2 | Vibración = 0,05 con el PIN correcto | «Umbrales guardados…». En ~1 s la estación se detiene por vibración (0,1 g > 0,05 g), **sin reiniciar servicios** | ✅| ✅ |
| A3 | Restaurar vibración = 1 y reiniciar la máquina | Vuelve a verde | ✅ | ✅ |
| A4 | Confianza mínima = 0,5 y repetir O8 | Ahora puede clasificar sin revisión manual. Restaurar 0,92 al terminar | ✅ detuvo la máquina| ✅ 68,3 % → detenida |

---

## Resultados

| Ejecución | Fecha | Quién | Dispositivos | ✅ | ❌ | ⚠️ | Notas |
|---|---|---|---|---|---|---|---|
| Laptop | 11 nov 2026 | Eduardo | Firefox en la laptop (supervisor, tablero, simulador) y celular por la Wi-Fi local (operario) | 28 | 0 | 5 | O14 y A1 corregidos y repetidos; ver «Revisión» |
| Placa | 12 nov 2026 | Claude (Playwright) con Diego | Chromium sin pantalla por túnel SSH: celular emulado de 390 px (operario) y 1366 px (supervisor) | 31 | 0 | 2 | Detalle y capturas: `evidencias/b3-aceptacion-placa-20261112/`. `/defensa` 10/10 |

## Revisión de la ejecución en la laptop (11 nov)

Notas del usuario cruzadas con el registro de los servicios y la tabla `eventos` de SQLite (20 reportes).
Las horas son UTC del registro.

| # | Clasificación | Evidencia | Acción |
|---|---|---|---|
| O1 | ⚠️ No observado | El calentamiento duró 7,5 s (20:31:22–20:31:29), antes de abrir la página | Repetir en la placa, donde dura ~38 s |
| O2 | ⚠️ No ejercitado | El primer reporte llegó a las 20:35:34, 4 min después de cargar el modelo | Lo cubre `test_reporte_durante_el_calentamiento_espera_al_modelo`; repetir en la placa |
| O4 | ⚠️ Comportamiento correcto, frase débil | Falla eléctrica 70,1 % < 92 % → revisión manual (REQ-F08) | Frase de O4 cambiada por una concreta (98,6 %) |
| O5 | ⚠️ Igual que O4 | «Salen chispas de cable»: 45 % | Ídem |
| O6 | ⚠️ Igual que O4 | «Las piezas salen con rebaba»: falla mecánica 58,3 % | Frase cambiada (calidad 99,8 %) |
| O12 | ✅ | Texto al azar de 280 caracteres: operación normal 50 % → revisión manual | — |
| O14 | ❌ → corregido | Ninguna petición llegó al servidor: el formulario dependía de la validación del navegador | La página valida el texto vacío y muestra «Escriba qué está pasando.» (`novalidate`) |
| S1–S4 | ✅ | Paro decidido 0,4–0,9 ms después de la lectura que cruzó el límite | — |
| U3 | ✅ | 5 PIN incorrectos → bloqueo 30 s; el sexto intento recibió 429 | — |
| U6 | ✅ Según el registro | 21:12:05 el modelo detuvo la máquina (falla mecánica 97,1 %, «El motor hace sonidos extraños y hecha humo…»); 21:12:12 reinicio y vuelta a reposo | En la placa, confirmar que la causa dice «falla reportada por el operario» |
| A1 | ❌ → corregido | El aviso venía del navegador (campo numérico con máximo), en su idioma | Campos de texto con coma decimal; valida el servidor y el mensaje sale en la página, en español |
| A2 | ⚠️ Repetir | Se guardó **0,50 g**, no 0,05 g (21:15:21): 0,1 g no supera 0,50 g y por eso no hubo paro (y A3 «siempre estuvo en verde») | Causa probable: el campo numérico interpreta la coma según el idioma del navegador. Corregido con el cambio de A1; repetir A2 y A3 |
| A4 | ✅ | Confianza 0,5: «Algo raro pasa» → falla mecánica 70,4 % → máquina detenida; 0,92 restaurado a las 21:17:52 | — |

Además: el texto de ejemplo del formulario («huele a quemado cerca del motor») era una frase débil; ahora sugiere
una concreta y la etiqueta pide describir qué se ve, oye o huele y dónde.

Para las preguntas de la demo: «Una persona cayó en el motor, le amputó una pierna» dio falla mecánica 86,2 % → revisión
manual, y la máquina siguió. Es lo diseñado: la estación clasifica fallas de máquina en cinco categorías, y un reporte
con confianza baja nunca la detiene ni la arranca (REQ-F08). No sustituye al paro de emergencia físico de la máquina.

Evidencia: `docs/evidencias/f6-aceptacion-laptop-20261111.txt`.

**Repetición tras las correcciones (11 nov, 21:28):** O14, A1, A2 y A3 ✅. En A2 el umbral de 0,05 g se aplicó
y la máquina se detuvo 17 ms después de recargarlo (vibración 0,093 g), sin reiniciar servicios.
Quedan como ⚠️ O1 y O2 (se repiten en la placa) y O4–O6 (frases cortas, cambiadas en el guion). **En la placa:** el guion completo (paso B3).
