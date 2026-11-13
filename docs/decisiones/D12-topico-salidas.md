# D12 · Tópico `andon/e1/salidas` en el contrato MQTT

- **Estado:** cerrada (cambio de contrato aprobado por el usuario)
- **Fecha:** 2026-11-06

## Contexto
`CLAUDE.md` dice que en modo sim «las salidas (luces, zumbador, OLED) se publican y
`/tablero` dibuja una torre virtual», pero el contrato no tenía un tópico para el estado
de las salidas: `cmd/senal` es una *orden* (core → sensores), no el estado real.

## Decisión
Se agrega al contrato:

| Tópico | De → a | Campos |
|---|---|---|
| `salidas` (retenido) | sensores → web | ts, maquina (bool), luz (`verde`\|`amarilla`\|`roja`\|`null`), zumbador (bool), oled (lista de líneas) |

- Lo publica `andon-sensores` **cada vez que cambia una salida** (observador de `HAL.suscribir`)
  y al arrancar; es retenido para que `/tablero` lo tenga al conectarse.
- Se publica **en modo sim y en la placa**: refleja lo realmente ordenado al hardware,
  no la intención del core. Así el tablero muestra la verdad también con la torre física.
- Sin cambios en los demás tópicos.

## Implementación
`app/src/andon/common/topicos.py` (`SALIDAS`, incluido en `RETENIDOS`) y la tabla de
contrato de `CLAUDE.md`.
