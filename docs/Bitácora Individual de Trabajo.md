# Bitácora Individual de Trabajo

**Nombre:** José Eduardo Tencio Solano  
**Proyecto:** II Proyecto - Sistemas Inteligentes de Borde (EdgeAI)  
**Rol:** [Director de Proyecto / Líder Técnico / Investigador / Auditor de Calidad]  



---

## Registro de Actividades

- **José Eduardo Tencio Solano:**

| Fecha | Actividades | Modalidad |
| :---: | :--- | :---: |
| 16/10/2026 | Investigación sobre Ollama y modelos JEV (`/v1/systemone`), análisis comparativo y evaluación de propuestas de aplicación (Smart Agriculture vs. Triaje e-Health) para la demostración presencial. | Virtual |
| 04/11/2026 | Fase 1 de la app (Estación Andon): estructura del repositorio; entorno Docker con Mosquitto, Ollama 0.40.14 y `tev1:0.8b`; descubrimiento del formato real de `/v1/systemone` por sondeo de la API; cliente en Python (`urllib`) con manejo de errores; pruebas unitarias y de contrato con 19 reportes de ejemplo; decisión D4 y requisitos v1 para la imagen Yocto. | Virtual |

---

## Productos Obtenidos

* Documento de análisis comparativo y evaluación técnica entre la **Propuesta 2 (Estación Agrícola Autónoma)** y la **Propuesta 4 (Módulo de Triaje Médico e-Health)**.
* Definición de la estructura de datos JSON y preguntas tipadas (`noul`, `score`, `choice`) para el modelo de decisión `tev1:0.8b` de Ollama.
* Repositorio base de la app (`app/`, `docker/`, `docs/`) y entorno `docker compose` con tres servicios (dev, Ollama, Mosquitto).
* Cliente de `/v1/systemone` (`app/src/andon/core/ollama.py`) con 17 pruebas en verde (14 unitarias, 3 de contrato).
* Documento de decisión D4 (`docs/decisiones/D4-contrato-systemone.md`): esquema de solicitud y respuesta, timeout y umbral de confianza provisionales, y resultados medidos.
* `docs/yocto-requisitos.md` v1, con paquetes, dispositivos, rutas y preguntas abiertas para el encargado de la imagen Yocto.

---

## Problemas Encontrados

* Necesidad de adaptar las propuestas conceptuales a las limitaciones de hardware de la Raspberry Pi 5 y a los requerimientos de la demostración presencial en el laboratorio.
* **Solución:** Se definieron periféricos de interfaz simples (pantalla OLED, botones, potenciómetros, relés y LEDs) y se seleccionó el modelo ligero `tev1:0.8b` para garantizar latencias inferiores a 200 ms sin requerir agua/fluidos complejos en la mesa de prueba.
* La documentación no describe el formato de `/v1/systemone`. **Solución:** se sondeó el endpoint leyendo los mensajes de error 400 hasta obtener el esquema (`state`, `questions` con `instructions`, `type` y `criteria`).
* El modelo `tev1:0.8b` requiere Ollama ≥ 0.40.4, no 0.35 como indicaba la propuesta. **Solución:** se registró la versión mínima en los requisitos para Yocto.
* La latencia de clasificación fue de ≈ 4,1 s en la PC, sobre la meta de 3 s (REQ-N05), y crece con el tamaño del prompt. **Solución:** pendiente; se medirá en la Raspberry Pi 4 y se evaluará acortar el prompt.
* Los reportes ambiguos obtuvieron probabilidades de 0,83–0,90, no bajas. **Solución:** umbral de confianza provisional de 0,92, a recalibrar con más reportes.
* El constructor de Docker en contenedor no resolvía DNS. **Solución:** construir con el constructor `default` (`BUILDX_BUILDER=default`).

---

## Referencias Consultadas

* Instructivo del II Proyecto: *Sistemas Inteligentes de Borde - EdgeAI*, Tecnológico de Costa Rica (IIS2026).
* Documentación oficial de Ollama v0.35+ y especificación de la API JEV (`/v1/systemone`).
* Propuesta de diseño del proyecto: Estación Andon Inteligente de Borde (requerimientos REQ-F04, REQ-F05, REQ-F08, REQ-N05).
* Documentación de Docker Compose y de la API local de Ollama (`/api/version`, `/v1/systemone`).
