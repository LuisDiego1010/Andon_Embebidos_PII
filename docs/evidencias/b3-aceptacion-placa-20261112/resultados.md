# B3 · Guion de aceptación en la placa (12 nov 2026)

RPi 4 con la imagen final (`app/imagen-final`, compilada el 11 nov a las 19:58), en modo sim y con el
modelo real `tev1:0.8b`. Lo ejecutó un navegador real sin pantalla (Playwright, Chromium 1.48): un celular
emulado de 390 px para el operario y una pantalla de 1366 px para el supervisor. La conexión fue por
Ethernet con un túnel SSH a la web (`127.0.0.1:5050` → placa `:5000`). Script: `aceptacion.py`.

Antes de empezar se reiniciaron `ollama` y `andon-core` para observar el calentamiento (O1, O2).

**Resultado: 31 ✅ · 0 ❌ · 2 ⚠️** (33 casillas, las mismas que en la laptop). Además, `/defensa` dio 10 de 10
(`../b4-defensa-placa-20261112.csv` y `.png`).

## Nota sobre la primera pasada
La primera ejecución marcó 5 ❌ (O4, O6, O7, U4, U5) y 1 ⚠️ (U6). Todos eran un error del script: después de
pulsar «Enviar» leía el resultado anterior, que sigue en pantalla durante las décimas de segundo que tarda en
aparecer «Analizando…». La tabla `eventos` de `andon.db` en la placa confirmó la respuesta de cada frase.
Se corrigió la espera (se oculta el resultado antes de enviar) y se repitieron O4, U6, U4, U5 y A4: todos ✅.
A4 tampoco era una falla: en la primera pasada el reporte salió antes de que la estación aplicara el umbral nuevo.

## Resultados

| # | Resultado | Nota |
|---|---|---|
| O1 | ✅ | Aviso «La estación está cargando el modelo…» visible al abrir |
| O2 | ✅ | «Huele a quemado cerca del motor», enviado durante el calentamiento: falla eléctrica 50,2 % → revisión manual en 37,6 s. Se clasificó, sin «tardó demasiado» |
| O3 | ✅ | Operación normal 100 %, sin acción |
| O4 | ✅ | Falla eléctrica 98,6–98,7 % → máquina detenida, aviso a Mantenimiento, 17,2 s |
| O5 | ⚠️ | «Salen chispas del cable»: falla eléctrica 50–51,5 % → revisión manual (frase corta, igual que en la laptop) |
| O6 | ✅ | «…con rebaba y fuera de medida» calidad 99,7 %; «…rayadas y fuera de especificación» calidad 99,9 %; aviso a Calidad, la máquina sigue |
| O7 | ⚠️ | «Se acabaron los tornillos en la línea»: material faltante 89–91,5 %, justo bajo 0,92 → revisión manual, aviso a Supervisión. La máquina sigue |
| O8 | ✅ | Falla mecánica 67–69 % → revisión manual, «un supervisor revisará el reporte» |
| O9 | ✅ | Tras recargar vuelve a «Analizando…» con el mismo texto y muestra el resultado (falla mecánica 87,2 %) |
| O10 | ✅ | 10 s sin red: sigue «Analizando…»; al volver muestra el resultado (falla mecánica 95,9 %, detenida) |
| O11 | ✅ | «No hay conexión con la estación. Revise el Wi-Fi.»; el texto se conserva |
| O12 | ✅ | 300 caracteres con tildes y ñ: el campo y el contador quedan en 280; reporte aceptado (91,7 %) |
| O13 | ✅ | «la banda hace ruido 🔧» aceptado (falla mecánica 70,9 %, revisión manual) |
| O14 | ✅ | «Escriba qué está pasando.» |
| O15 | ✅ | Aviso rojo con el motivo; el reporte responde «Paro de seguridad activo: no se actuó» |
| O16 | ✅ | 3 reportes desde 3 pestañas móviles: todos con resultado, en orden (17,6 s, 33,8 s y 50,5 s: cola de uno en uno) |
| O17 | ✅ | Sin desplazamiento horizontal a 390 px en `/`, `/tablero`, `/supervisor` y `/simulador` |
| S1 | ✅ | Aspa desbalanceada: la web ve el paro a los 0,36 s (incluye MQTT y el sondeo de 0,05 s); luz roja y zumbador. Tablero: «vibración excesiva: 1,08 g (límite 1,00 g)» |
| S2 | ✅ | Con la vibración en 0,016 g el paro sigue retenido |
| S3 | ✅ | Sobrecalentamiento: paro por temperatura en 0,54 s (85,0 °C, límite 60) |
| S4 | ✅ | MPU-6050 desconectado: paro a los 2,12 s, «MPU-6050 sin señal» |
| U1 | ✅ | Estado «PARO DE SEGURIDAD», causa con valor y límite, lecturas |
| U2 | ✅ | «PIN incorrecto.»; sigue detenida |
| U3 | ✅ | 6.º intento: «Demasiados intentos. Espere 30 s.» |
| U4 | ✅ | Causa presente (2 g): «La máquina se detuvo de nuevo: vibración excesiva: 2,00 g (límite 1,00 g)…» |
| U5 | ✅ | Causa corregida: «La máquina volvió a operar.», luz verde |
| U6 | ✅ | Tras O4: causa «falla reportada por el operario» → «La máquina volvió a operar.» |
| U7 | ✅ | 19 eventos en `/tablero`, con hora, texto, categoría y %, acción, área y tiempo de respuesta |
| U8 | ✅ | `systemctl stop andon-web` con el tablero abierto: «Sin comunicación con la estación», torre apagada |
| A1 | ✅ | Vibración = 9: «…debe ser mayor que 0 y como máximo 4.»; el archivo no cambia |
| A2 | ✅ | Vibración = 0,05: «Umbrales guardados…» y paro por vibración sin reiniciar servicios |
| A3 | ✅ | Vibración = 1 y reinicio: vuelve a verde |
| A4 | ✅ | Confianza 0,5: «Algo raro pasa» (68,3 %) ya no va a revisión manual (máquina detenida). Restaurada a 0,92 |
