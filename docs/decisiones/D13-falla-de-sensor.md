# D13 · Falla de un sensor = paro retenido

- **Estado:** cerrada (aprobada por el usuario)
- **Fecha:** 2026-11-06

## Contexto
Un lazo de seguridad que sigue con la máquina girando sin poder medir es peor que uno
que la detiene. En la placa sin sensores conectados (6 nov) `HalRpi` ya reporta
`ErrorHardware` (MPU-6050 sin responder: errno 121; DS18B20 ausente).

## Decisión
Si el MPU-6050 o el DS18B20 no entregan una lectura válida durante **2 s seguidos**
(`ErrorHardware` consecutivos), `andon-sensores`:
1. detiene la máquina y enciende la luz roja y el zumbador, sin MQTT ni modelo;
2. publica `seguridad` retenido con `activo: true` y `sensor: "mpu6050_fallo"` o
   `"ds18b20_fallo"` (el campo `sensor` ya es texto libre: **no cambia el contrato**);
3. queda **retenido** como cualquier paro por umbral: solo `reiniciar` con PIN válido
   (origen `web`) lo libera (CU-06), y si el sensor sigue fallando se vuelve a detener.

Se agrega como invariante 5 en `CLAUDE.md`.

## Consecuencias
- Sin sensores conectados, el servicio detiene la máquina: esperado, aún no hay máquina.
  En pruebas con hardware parcial se usa el modo sim.
- Una lectura aislada fallida no detiene: se tolera hasta 2 s.
- El valor de 2 s es configurable (`[sensores] tolerancia_fallo_s`, F3).
- La lectura del DS18B20 tarda ~750 ms: 2 s equivalen a ~2–3 intentos fallidos.

## Implementado en F3 (REQ-N04)
Ventana de RMS deslizante de 1 s evaluada cada 100 ms (`sensores/rms.py`), para detectar una
falla brusca en menos de 1 s sin esperar a que se complete la ventana. Si se evaluara una vez
por segundo, el paro podría tardar hasta 2 s desde el inicio de la falla.

Se detecta un sensor colgado (no solo uno que lanza error) con un vigilante: la última lectura
válida de cada sensor no puede tener más de 2 s. El paro se guarda en `paro_ruta`
(`/var/lib/andon/paro.json`) y sobrevive a reinicios del servicio y de la estación.

Medido en simulación (PC): ≈ 200 ms desde que empieza la falla hasta la máquina detenida;
0,7–1,1 ms desde la muestra que cruza el umbral (el umbral de 1,0 g se cruza ≈ 0,2 s después
del inicio de una falla de 2 g).
