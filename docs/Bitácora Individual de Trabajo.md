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

---

## Productos Obtenidos

* Documento de análisis comparativo y evaluación técnica entre la **Propuesta 2 (Estación Agrícola Autónoma)** y la **Propuesta 4 (Módulo de Triaje Médico e-Health)**.
* Definición de la estructura de datos JSON y preguntas tipadas (`noul`, `score`, `choice`) para el modelo de decisión `tev1:0.8b` de Ollama.

---

## Problemas Encontrados

* Necesidad de adaptar las propuestas conceptuales a las limitaciones de hardware de la Raspberry Pi 5 y a los requerimientos de la demostración presencial en el laboratorio.
* **Solución:** Se definieron periféricos de interfaz simples (pantalla OLED, botones, potenciómetros, relés y LEDs) y se seleccionó el modelo ligero `tev1:0.8b` para garantizar latencias inferiores a 200 ms sin requerir agua/fluidos complejos en la mesa de prueba.

---

## Referencias Consultadas

* Instructivo del II Proyecto: *Sistemas Inteligentes de Borde - EdgeAI*, Tecnológico de Costa Rica (IIS2026).
* Documentación oficial de Ollama v0.35+ y especificación de la API JEV (`/v1/systemone`).
