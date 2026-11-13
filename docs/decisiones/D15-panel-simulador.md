# D15 · Panel del simulador y tópico `sim/ajustar`

- **Estado:** cerrada.
- **Fecha:** 2026-11-09

## Decisión
Sin hardware disponible, la página `/simulador` de `andon-web` reemplaza a los sensores. Sus controles
publican `andon/e1/sim/ajustar` (retenido) con el estado completo: `vib_g`, `ruido_g`, `temp_c`
(`null` = modelo térmico automático), `mpu_ok` y `ds18b20_ok`. `hal/sim.py` los aplica hasta que se
vuelvan a mover, y un sensor «desconectado» lanza `ErrorHardware` como `hal/rpi.py`.

Las perillas alimentan el mismo camino que el hardware real: muestras crudas, RMS, umbrales, paro, MQTT.

## Seguridad
- `andon-sensores` se suscribe a `sim/ajustar` solo en modo sim.
- `/simulador` y `/api/sim/ajustar` responden 404 fuera de modo sim.
- El modo sim se activa con drop-ins (`tools/modo.sh`), nunca desde la receta (D11).

## Límites
Valida el comportamiento del sistema, no los chips ni el cableado (`docs/guia-hardware.md`).
