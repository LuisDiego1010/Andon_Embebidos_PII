# D16 · `evento` con probabilidades, umbral y entrada del modelo

- **Estado:** cerrada.
- **Fecha:** 2026-11-09

## Decisión
`andon/e1/evento` agrega tres campos, sin cambiar los anteriores (D14):

| Campo | Contenido |
|---|---|
| `probs` | Probabilidad de cada una de las 5 categorías (`null` si el modelo falló) |
| `umbral` | Umbral de confianza vigente al decidir |
| `entrada` | Texto exacto enviado a `/v1/systemone`: reporte del operario y lecturas |

## Por qué
Para la defensa y para auditar decisiones: muestra que el modelo sopesa las 5 opciones y con qué
información decidió. La página `/defensa` los usa para dibujar las barras de probabilidad.

## Límites
No se guardan en SQLite: el registro (REQ-F10) conserva la categoría elegida y su probabilidad.
