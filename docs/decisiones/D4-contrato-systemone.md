# D4 · Contrato con /v1/systemone

- **Estado:** cerrada en formato; timeout y umbral de confianza **provisionales**
  hasta medir en la RPi 4 (F2) y con más reportes (F4/F7).
- **Fecha:** 2026-11-04
- **Entorno de medición:** Docker `dev` en la PC (x86, 8 hilos), Ollama 0.40.14,
  `tev1:0.8b` (Q8_0, 772 M parámetros, capacidad `decision`).

## Formato observado

`POST {url}/v1/systemone`, JSON. El esquema se descubrió probando la API (los PDF
no lo describen):

```json
{
  "model": "tev1:0.8b",
  "state": "Reporte del operario: ... Lecturas de sensores: vibración 0.90 g RMS, temperatura 42.0 °C.",
  "questions": {
    "categoria": {
      "instructions": "Clasifica el reporte del operario de una estación de producción",
      "type": "choice",
      "criteria": { "operacion_normal": "descripción", "falla_mecanica": "...", "...": "..." }
    }
  }
}
```

Respuesta 200:

```json
{
  "model": "tev1:0.8b",
  "answers": { "categoria": {
    "type": "choice", "choice": "falla_mecanica",
    "probabilities": { "operacion_normal": 0.001, "falla_mecanica": 0.997, "...": 0.0 },
    "confidence": 0.997 } },
  "usage": { "input_tokens": 235, "output_tokens": 0 }
}
```

Reglas del servidor (mensajes de error 400 observados):
- `model` obligatorio; modelo inexistente → 404 `model 'x' not found`.
- `questions`: 1–64 campos; cada uno exige `instructions`, `type` y `criteria`.
- `type` ∈ `choice` | `score` | `noul`. `choice` usa `criteria` como objeto
  opción → descripción. `score` exige `criteria` como arreglo de 2–10 niveles (no usado).
- `state` obligatorio; acepta texto o un objeto JSON (se usa **texto**: con objeto la
  respuesta fue peor en la única prueba hecha).
- `GET` → 405 (solo `POST`).

## Decisiones

| Aspecto | Decisión |
|---|---|
| Pregunta | Una sola, `categoria`, tipo `choice`, con las 5 categorías de REQ-F05 |
| Estado (REQ-F04) | Texto: reporte del operario + lecturas (`vib_rms_g`, `temp_c`) en español |
| Probabilidad usada | `probabilities[choice]` (REQ-F08: «probabilidad de la categoría elegida»). `confidence` se guarda pero no decide |
| Cualquier fallo | Conexión, timeout, HTTP ≠ 200, JSON inválido o categoría desconocida → `ErrorOllama` → luz amarilla y revisión manual |
| Timeout (provisional) | **15 s** en la configuración. Es una guarda contra bloqueos, no la meta de 3 s (REQ-N05). Reajustar con la latencia medida en la RPi 4 |
| Umbral de confianza (provisional) | **0,92**. Ver resultados |
| Descripciones de criterios | Largas (en `core/ollama.py`). Las cortas no redujeron la latencia de forma clara y separaron peor las probabilidades |

Implementación: `app/src/andon/core/ollama.py`.
Prueba de contrato: `app/tests/contract/` (19 reportes en `reportes.json`).

## Resultados (PC x86, 19 reportes)

| Métrica | Valor |
|---|---|
| Exactitud en los 16 reportes claros | 16/16 (100 %) |
| Probabilidad de los claros | mín 0,90 · el resto ≥ 0,96 |
| Probabilidad de los 3 ambiguos | 0,83 · 0,86 · 0,90 (todos clasificados como `falla_mecanica`) |
| Latencia | mín 4,06 s · mediana 4,16 s · máx 4,42 s |

## Hallazgos y riesgos

1. **Latencia sobre la meta.** ≈ 4,1 s en la PC contra 3 s de REQ-N05, y la RPi 4 será
   más lenta. La latencia crece con el tamaño del prompt (criterios de 5 palabras:
   ≈ 2,2 s; descripciones largas: ≈ 3,4–4,2 s). Es un compromiso con la exactitud.
   REQ-N05 es una «meta de diseño»: se mide y se reporta. Palancas si hace falta:
   acortar descripciones, reducir el texto del estado, `num_ctx` menor.
2. **Los ambiguos no salen con probabilidad baja.** El modelo les asigna 0,83–0,90, no
   un valor cercano a 0,5. Un umbral de 0,92 los envía a revisión manual (CU-05), pero
   también manda a amarillo un reporte claro (el id 16, con 0,90): se acepta porque
   amarillo es el lado seguro. El conjunto es pequeño y fácil: **recalibrar** en F4/F7
   con más reportes, incluyendo casos difíciles y mal escritos.
3. **La exactitud del 100 % no es representativa.** Los 16 reportes claros son frases
   típicas escritas para esta prueba. La propuesta cita 63,5 % para el modelo de 0,8B.
