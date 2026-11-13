# D14 · `evento` lleva `id` y `error`

- **Estado:** cerrada (aprobada por Eduardo el 6 nov, F4).
- **Cambio de contrato MQTT:** sí. Reflejado en `common/topicos.py`, en `CLAUDE.md` y en el
  contrato de `docs/traspaso.md`.

## Problema
`evento` (core → público) no traía el `id` del reporte, así que `andon-web` no podía saber
qué resultado correspondía a qué reporte cuando el operario envía varios (la consulta tarda
≈ 17 s en la RPi 4). Tampoco distinguía «el modelo dudó» de «Ollama falló».

## Decisión
`evento` agrega dos campos:

| Campo | Valor |
|---|---|
| `id` | el `id` que trajo el `reporte` (texto) o `null` |
| `error` | `null` si el modelo respondió; si no, un código corto: `timeout`, `conexion`, `respuesta` (HTTP ≠ 200, JSON o categoría inválidos) o `cola_llena` (reporte descartado) |

El detalle completo del error (clase y mensaje) queda en el registro SQLite (columna `error`),
no en el bus. `estado.ultimo_evento` lleva el mismo objeto.

La web decide qué mostrar con `accion` y `error`: `revision_manual` + `error: null` = el modelo
no estuvo seguro; `revision_manual` + `error: "timeout"` = Ollama no respondió a tiempo.

## Compatibilidad
Solo agrega campos: un consumidor que ignore claves desconocidas no se rompe. No hay otros
consumidores todavía (la web llega en F5).
