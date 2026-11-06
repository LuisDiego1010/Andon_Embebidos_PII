# D4 · Contrato con /v1/systemone

- **Estado:** cerrada en formato. Timeout (45 s) fijado con datos de la RPi 4; umbral de
  confianza (0,92) **provisional** hasta tener más reportes (F4/F7).
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
| Timeout | **45 s** (`TIMEOUT_S` en `core/ollama.py`; el valor real vendrá de `andon.conf`). La mediana en la RPi 4 es 16,8 s y la carga en frío 38 s. Es una guarda contra bloqueos, no la meta de REQ-N05 |
| Calentamiento | Al arrancar, `andon-core` llama a `ollama.calentar()` (consulta mínima, nunca lanza): el primer reporte del operario no paga la carga de ~38 s |
| CPU de la placa | Modo `performance` fijo (lo configura la imagen): ≈ 10 % menos de latencia |
| Umbral de confianza (provisional) | **0,92**. Los datos de la RPi 4 lo respaldan (ver resultados) |
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

## Resultados en la RPi 4 (imagen Yocto, Ollama 0.40.13)

Medidos por Diego con `scripts/medir-latencia.py` (mismo cliente y mismos 19 reportes);
evidencia en `docs/evidencias/latencia-20261105-193340.csv`. CPU en `ondemand`.

| Métrica | RPi 4 | PC |
|---|---|---|
| Latencia mín. / mediana / máx. | 16,4 s / **16,8 s** / 17,5 s | 4,1 s / 4,2 s / 4,4 s |
| Carga del modelo + primera consulta | 38,1 s | — |
| Exactitud en los 16 claros | 16/16 | 16/16 |
| Claros que irían a amarillo con 0,92 | 1/16 (id 16, 0,91) | 1/16 (id 16, 0,90) |
| Ambiguos que irían a amarillo con 0,92 | 3/3 (0,86–0,89) | 3/3 (0,83–0,90) |

Con la CPU fija en `performance` (1,5 GHz) la mediana baja a ≈ 15,2 s.

## Diagnóstico de la latencia (REQ-N05)

Mediciones en la PC (6 nov). El modelo no genera texto (`output_tokens = 0`): el tiempo
es casi todo lectura del prompt.

| Variante | Tokens de entrada | Latencia | Resultado |
|---|---|---|---|
| Actual: 5 descripciones largas | 316 | 3,66 s | eléctrica 0,98 |
| 5 descripciones = solo el nombre | 241 | 2,79 s | eléctrica 0,88 |
| 3 categorías largas | 242 | 2,80 s | — |
| 2 categorías largas | 197 | 2,28 s | — |
| Estado corto («chispa en el cable») | 278 | 3,21 s | eléctrica 0,57 |
| Estado ×3 | 406 | 4,76 s | eléctrica 0,98 |
| Instrucción corta | 306 | 3,54 s | sin cambio |
| Mínimo de la API: 2 opciones de 1 letra | 101 | 1,22 s | — |
| Mínimo de la API: 5 opciones de 1 letra | 155 | 1,92 s | — |

- La latencia es de ≈ 11,6 ms por token de entrada en la PC, y la RPi 4 es ≈ 4 veces más lenta.
- No hay caché de prompt: repetir la misma consulta tarda lo mismo.
- La estructura de 5 opciones aporta un piso de ≈ 155 tokens (≈ 18 por opción): en la
  RPi 4 son **≈ 7–8 s antes de escribir texto propio**.
- Acortar descripciones o el estado baja la latencia, pero baja también la probabilidad
  (0,98 → 0,88 / 0,57) y manda más reportes a amarillo.

**Conclusión:** con `tev1:0.8b`, 5 categorías y RPi 4, la meta de 3 s **no es alcanzable**
ajustando el prompt. Descartado `tev1:4b`: tiene 5 veces más parámetros, así que se
estima en ≈ 80–90 s por reporte, ocuparía ≈ 4,5 GB de RAM y no cabe en la partición
raíz de la imagen (1,7 GB libres). No se prueba.

**REQ-N05: no se cumple y se reporta** (≈ 15 s en la placa), como permite la propuesta
(«se medirá y reportará»). Mitigaciones adoptadas:
1. Calentamiento al arrancar (elimina los 38 s del primer reporte).
2. CPU en `performance`.
3. Flujo asíncrono en F4/F5: la web responde al instante «Analizando…» (amarillo) y
   publica el resultado después. El paro de seguridad (REQ-F07, < 1 s) no depende del modelo.
4. Pendiente: descripciones de largo medio (Diego), a medir con los 19 reportes.

## Hallazgos y riesgos

1. **Latencia sobre la meta.** ≈ 4,1 s en la PC y ≈ 16,8 s en la RPi 4 contra 3 s de
   REQ-N05 (ver diagnóstico arriba). La latencia crece con el tamaño del prompt (criterios de 5 palabras:
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
4. **Reportes cortos bajan la confianza** (hallazgo de Diego en la placa): «olor a quemado
   cerca del motor», sin lecturas, dio 0,80 (iría a amarillo); con la redacción del
   contrato, 0,98. Para la demo de CU-03 hay que usar una frase que el modelo clasifique
   con seguridad. Se probará con reportes más exigentes en F4.
