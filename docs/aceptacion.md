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

**Frases:** usar las de la propuesta (Tabla 5) y además escribir frases propias. El modelo `tev1:0.8b`
no reconoce igual todas las redacciones. Por ejemplo, en la laptop (10 nov) «Las piezas salen con rebaba»
dio *falla mecánica* al 60 % y terminó en revisión manual, en lugar de *problema de calidad*.
Anotar la categoría y la confianza obtenidas, aunque el resultado no sea el esperado: sirve para elegir las frases
de la demo y para recalibrar el umbral de confianza (0,92).

---

## 1. Operario (celular, página «Reporte»)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| O1 | Abrir la página recién arrancada la estación | Aviso amarillo «cargando el modelo» mientras dura el calentamiento; desaparece solo | | |
| O2 | Durante O1, enviar «Huele a quemado cerca del motor». En la laptop el calentamiento dura ~10 s: enviarlo apenas arranque; en la placa dura ~38 s | Contador «Analizando… N s» con el aviso de carga. Tarda más, pero **se clasifica**: no termina en «El modelo tardó demasiado» | | |
| O3 | CU-01: con todo normal, «La máquina funciona bien, sin novedades» | Verde o amarilla con revisión manual; la máquina sigue. Anotar categoría y % | | |
| O4 | CU-03: «olor a quemado cerca del motor» (frase de la propuesta) | Falla eléctrica → **Máquina detenida**, aviso a Mantenimiento, luz roja en el tablero. Anotar % y tiempo | | |
| O5 | CU-03 con frase propia (p. ej. «salen chispas del cable») | Igual que O4. Anotar resultado | | |
| O6 | CU-04: «las piezas salen con rebaba» (propuesta) y una frase propia de calidad | Calidad → luz amarilla, aviso a Calidad, la máquina sigue. Anotar % de cada una | | |
| O7 | Material faltante: «se acabaron los tornillos en la línea» | Amarilla, aviso a Supervisión, la máquina sigue | | |
| O8 | CU-05: «algo raro pasa, no sé qué es» | Revisión manual y «La máquina sigue en marcha; un supervisor revisará el reporte» | | |
| O9 | Enviar un reporte y **recargar la página** mientras dice «Analizando…» | Tras recargar vuelve a «Analizando…» con el mismo texto y muestra el resultado al final | | |
| O10 | Enviar un reporte y **apagar el Wi-Fi del celular** antes de que responda; reactivarlo a los 10 s | Mientras no hay red, sigue esperando. Al volver, muestra el resultado. Ningún mensaje en inglés | | |
| O11 | Con el Wi-Fi apagado, pulsar «Enviar reporte» | «No hay conexión con la estación. Revise el Wi-Fi.»; el texto **no se borra** | | |
| O12 | Escribir 280 caracteres con tildes y ñ | El contador llega a 280, no deja escribir más y el reporte se acepta | | |
| O13 | Texto con un emoji (p. ej. «la banda hace ruido 🔧») | Se acepta. El contador puede marcar 2 por emoji: es esperado | | |
| O14 | Solo espacios | «Escriba qué está pasando.» | | |
| O15 | Con paro de seguridad activo (ver S1), abrir «Reporte» | Aviso rojo con el motivo («vibración excesiva: …»). El reporte se puede enviar y responde «Paro de seguridad activo: no se actuó» | | |
| O16 | Enviar 3 reportes seguidos desde 2 dispositivos | Todos reciben resultado, en orden. Ninguno se pierde | | |
| O17 | Legibilidad en el celular | Sin desplazamiento horizontal; botones fáciles de pulsar; porcentajes con coma decimal | | |

## 2. Sistema (panel `/simulador`, hace de máquina y sensores)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| S1 | CU-02: botón «Aspa desbalanceada» (2 g) | Paro en < 1 s: luz roja, zumbador. El tablero dice «PARO DE SEGURIDAD: vibración excesiva: 1,15 g (límite 1,00 g)». El valor es el primero que cruzó el límite, por eso es menor que 2 | | |
| S2 | Volver la vibración a 0,1 g | **El paro sigue retenido** (rojo) hasta que lo libere el supervisor | | |
| S3 | «Sobrecalentamiento» (85 °C) | Paro por temperatura con su motivo en °C | | |
| S4 | «Desconectar MPU-6050» | Paro a los ~2 s: «MPU-6050 sin señal» | | |

## 3. Supervisor (página «Supervisor», laptop o tablet)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| U1 | Con el paro de S1 activo, abrir la página | Estado «PARO DE SEGURIDAD» (no «paro_seguridad»), causa con valor y límite, lecturas y último reporte | | |
| U2 | CU-06: PIN incorrecto y «Reiniciar» | Pide confirmación. Luego «PIN incorrecto.» y la máquina sigue detenida | | |
| U3 | 5 PIN incorrectos seguidos | Al sexto intento: «Demasiados intentos. Espere 30 s.» | | |
| U4 | **Con la causa todavía presente** (vibración en 2 g), PIN correcto y «Reiniciar» | «Verificando…» y luego «La máquina se detuvo de nuevo: vibración excesiva…». No dice «volvió a operar» | | |
| U5 | Normalizar la causa (0,1 g) y reiniciar con el PIN correcto | «La máquina volvió a operar.»; la torre pasa a verde | | |
| U6 | Después de O4 (máquina detenida por el modelo), reiniciar | Causa «falla reportada por el operario». Tras reiniciar, vuelve a operar | | |
| U7 | En `/tablero`, revisar los eventos de baja confianza (O8) | Cada evento muestra hora, texto, categoría con %, acción, área y tiempo de respuesta | | |
| U8 | Con la estación caída (detener el contenedor o `systemctl stop andon-web`), mirar `/tablero` | «Sin comunicación con la estación»; la torre se apaga, no queda congelada | | |

## 4. Administrador (página «Supervisor», sección Umbrales)

| # | Acción | Esperado | Laptop | Placa |
|---|---|---|---|---|
| A1 | CU-07: vibración = 9 | «Vibración RMS máxima: debe ser mayor que 0 y como máximo 4.» El archivo no cambia | | |
| A2 | Vibración = 0,05 con el PIN correcto | «Umbrales guardados…». En ~1 s la estación se detiene por vibración (0,1 g > 0,05 g), **sin reiniciar servicios** | | |
| A3 | Restaurar vibración = 1 y reiniciar la máquina | Vuelve a verde | | |
| A4 | Confianza mínima = 0,5 y repetir O8 | Ahora puede clasificar sin revisión manual. Restaurar 0,92 al terminar | | |

---

## Resultados

| Ejecución | Fecha | Quién | Dispositivos | ✅ | ❌ | ⚠️ | Notas |
|---|---|---|---|---|---|---|---|
| Laptop | | | | | | | |
| Placa | | | | | | | |
