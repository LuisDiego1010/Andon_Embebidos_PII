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
| 06/11/2026 | Diagnóstico de la latencia en la Raspberry Pi 4 (≈ 17 s por consulta; `tev1:4b` descartado; calentamiento del modelo al arrancar); capa de hardware (interfaz, simulador de muestras a 100 Hz y controlador de la RPi con libgpiod v2) probada con dobles y en la placa; decisiones D7 y D11–D14 (simulación primero, tópico `salidas`, falla de sensor, `evento` con `id` y `error`); `andon-sensores` con lazo de seguridad de 100 Hz, paro retenido y falla de sensor, medido en la RPi 4 con Ollama calculando (paro de 272–363 ms); `andon-core` con máquina de estados, Tabla 9, registro SQLite y recarga de configuración; CU-01 a CU-06 en simulación y CU-03, CU-04 y CU-05 con el modelo real; guía de continuación (`docs/traspaso.md`). | Virtual y presencial (laboratorio) |
| 10/11/2026 | Revisión y fusión a `app/dev` de la rama de Luis Diego (`andon-web`, OLED y servicios en la imagen); guía de uso de la app simulada (`docs/guia de uso.md`); decisión D17 (se recorta QEMU) y plan de cierre: fase A sin placa y fase F7 de aceptación en la placa (B0–B8); correcciones del flujo del operador en la web (reporte durante el calentamiento del modelo, texto conservado, errores en español, resultado recuperable, reinicio verificado por el supervisor); estación completa en la laptop con el modelo real y acceso desde el celular; configuración del punto de acceso Wi-Fi `Andon-E1`; guiones de aceptación del operador y de la demostración; tabla RG-1 a RG-5; requisitos v2 para la imagen. | Virtual |
| 11/11/2026 | Ejecución del guion de aceptación como operador, supervisor y administrador (celular y Firefox, modelo real): 33 pasos; revisión cruzada con el registro de los servicios y la base SQLite; corrección de dos fallos (texto vacío sin aviso y umbrales con avisos del navegador en inglés y coma decimal mal interpretada) y repetición en verde (28 ✅, 0 ❌, 5 ⚠️); medición de la confianza del modelo según la redacción de las frases; push de `app/dev` y etiqueta `v0.9-sim` (fin del desarrollo en modo simulado, base de la imagen final). | Virtual |

---

## Productos Obtenidos

* Documento de análisis comparativo y evaluación técnica entre la **Propuesta 2 (Estación Agrícola Autónoma)** y la **Propuesta 4 (Módulo de Triaje Médico e-Health)**.
* Definición de la estructura de datos JSON y preguntas tipadas (`noul`, `score`, `choice`) para el modelo de decisión `tev1:0.8b` de Ollama.
* Repositorio base de la app (`app/`, `docker/`, `docs/`) y entorno `docker compose` con tres servicios (dev, Ollama, Mosquitto).
* Cliente de `/v1/systemone` (`app/src/andon/core/ollama.py`) con 17 pruebas en verde (14 unitarias, 3 de contrato).
* Documento de decisión D4 (`docs/decisiones/D4-contrato-systemone.md`): esquema de solicitud y respuesta, timeout y umbral de confianza provisionales, y resultados medidos.
* `docs/yocto-requisitos.md` v1, con paquetes, dispositivos, rutas y preguntas abiertas para el encargado de la imagen Yocto.
* Capa de hardware (`app/src/andon/hal/`): interfaz común, simulador y controlador de la RPi 4; mapa de pines en `docs/hardware.md`.
* Servicio `andon-sensores` (lazo de seguridad de 100 Hz, paro retenido que sobrevive a reinicios, falla de sensor → paro) y herramientas de prueba (`inyector.py`, `probar_hal.py`).
* Servicio `andon-core` (máquina de estados, Tabla 9 y umbral de confianza, registro SQLite, publicación de `evento` y `estado`, recarga de configuración) y herramientas `fake_ollama.py` y `enviar_reporte.py`.
* Decisiones D7 (configuración y recarga), D11 (estrategia de simulación), D12 (tópico `salidas`), D13 (falla de sensor) y D14 (`evento` con `id` y `error`).
* Pruebas: 277 unitarias y de integración en verde en x86 y aarch64 (emuladas); evidencias en `docs/evidencias/` (CU-01 a CU-06 en simulación, nivel 3b en la RPi 4, CU-03/04/05 con el modelo real).
* `docs/traspaso.md`: estado, pendientes, contrato MQTT, invariantes y forma de trabajar, para que el equipo continúe la app.
* `docs/guia de uso.md`: uso de la app simulada, qué corre en la laptop y qué en la placa, y cómo la simulación de los sensores reproduce el comportamiento real.
* Decisión D17 (`docs/decisiones/D17-sin-qemu.md`) y plan actualizado con las fases A (sin placa) y F7 (aceptación en la placa).
* `scripts/simulador-pc.sh` con Docker, modelo real (`--ollama-real`) y acceso desde el celular (`--lan`).
* Configuración del punto de acceso Wi-Fi propio (`app/deploy/red/`: hostapd, dnsmasq y systemd-networkd) y requisitos v2 para la imagen Yocto.
* `docs/aceptacion.md` (guion del operador, 33 pasos, con resultados y revisión de la laptop) y `docs/demo.md` (guion de la demostración de ≈ 20 min con el flujo Yocto y plan B).
* Evidencia `docs/evidencias/f6-aceptacion-laptop-20261111.txt`: 20 reportes escritos a mano y la confianza del modelo por frase.
* Pruebas: 357 unitarias y de integración en verde (x86).
* Etiqueta `v0.9-sim` en `app/dev`, publicada en GitHub.

---

## Problemas Encontrados

* Necesidad de adaptar las propuestas conceptuales a las limitaciones de hardware de la Raspberry Pi 5 y a los requerimientos de la demostración presencial en el laboratorio.
* **Solución:** Se definieron periféricos de interfaz simples (pantalla OLED, botones, potenciómetros, relés y LEDs) y se seleccionó el modelo ligero `tev1:0.8b` para garantizar latencias inferiores a 200 ms sin requerir agua/fluidos complejos en la mesa de prueba.
* La documentación no describe el formato de `/v1/systemone`. **Solución:** se sondeó el endpoint leyendo los mensajes de error 400 hasta obtener el esquema (`state`, `questions` con `instructions`, `type` y `criteria`).
* El modelo `tev1:0.8b` requiere Ollama ≥ 0.40.4, no 0.35 como indicaba la propuesta. **Solución:** se registró la versión mínima en los requisitos para Yocto.
* La latencia de clasificación fue de ≈ 4,1 s en la PC, sobre la meta de 3 s (REQ-N05), y crece con el tamaño del prompt. **Solución:** pendiente; se medirá en la Raspberry Pi 4 y se evaluará acortar el prompt.
* Los reportes ambiguos obtuvieron probabilidades de 0,83–0,90, no bajas. **Solución:** umbral de confianza provisional de 0,92, a recalibrar con más reportes.
* El constructor de Docker en contenedor no resolvía DNS. **Solución:** construir con el constructor `default` (`BUILDX_BUILDER=default`).
* La latencia en la RPi 4 es ≈ 17 s por reporte (≈ 4 s en la PC), y no mejora con la CPU en modo `performance`. **Solución:** el tiempo es casi todo lectura del prompt (≈ 11,6 ms por token de entrada); no se alcanza la meta de 3 s (REQ-N05) y se reporta. Se mitiga con el calentamiento al arrancar, luz amarilla «Analizando…» durante la consulta y un paro de seguridad independiente del modelo.
* La placa no tiene sensores ni actuadores todavía. **Solución:** estrategia de simulación primero (D11): el simulador entrega muestras crudas, de modo que el cálculo del RMS y los umbrales son el mismo código que en la placa; la RPi corre en modo sim (nivel 3b) y la verificación con hardware queda en un «Bloque hardware» sin fecha.
* El cable directo a la placa no entrega DHCP. **Solución:** acceso por SSH con dirección IPv6 de enlace local.
* Con el modelo real, un reporte del CU-03 dio probabilidad 0,886 (bajo el umbral de 0,92) y fue a revisión manual. **Solución:** la confianza depende de la redacción (D4); la demostración usa una frase que el modelo clasifica con 0,987. Se recalibrará el umbral con más reportes.
* `docker compose run` intentaba recrear Ollama por una diferencia de versión entre el pin y el contenedor (≈ 8 GB). **Solución:** usar `--no-deps` y recrearlo cuando haya buena red.
* Una prueba de integración fallaba de forma intermitente por una carrera entre mensajes MQTT (la máquina se detiene antes que se publique la luz roja). **Solución:** esperar el estado completo en la prueba; 8 corridas seguidas en verde.
* QEMU no aportaba pruebas que Docker arm64 y la placa no cubrieran. **Solución:** se recortó del plan (D17).
* La app se había probado en la placa con páginas automáticas, pero nadie la había usado como operador. **Solución:** guion de aceptación manual por rol; al revisar el código se corrigieron siete defectos de uso, entre ellos que un reporte enviado mientras cargaba el modelo terminaba en «tardó demasiado».
* `simulador-pc.sh` exigía podman y fallaba si Ollama acababa de arrancar. **Solución:** usar Docker cuando no hay podman y esperar hasta 30 s a que Ollama responda.
* En la aceptación, un texto de solo espacios no mostraba aviso y los umbrales mostraban avisos del navegador en inglés; además, un umbral escrito con coma decimal se guardó con otro valor (0,50 g en lugar de 0,05 g). **Solución:** la página y el servidor validan en español, y los umbrales aceptan coma decimal; los cuatro pasos se repitieron en verde.
* Las frases cortas de la propuesta («olor a quemado cerca del motor») obtuvieron 45–70 % de confianza y fueron a revisión manual, igual que el reporte ambiguo del CU-05. **Solución:** se mantiene el umbral de 0,92 (bajarlo rompería el CU-05); el guion y la demostración usan frases concretas, que superan el 95 %.

---

## Referencias Consultadas

* Instructivo del II Proyecto: *Sistemas Inteligentes de Borde - EdgeAI*, Tecnológico de Costa Rica (IIS2026).
* Documentación oficial de Ollama v0.35+ y especificación de la API JEV (`/v1/systemone`).
* Propuesta de diseño del proyecto: Estación Andon Inteligente de Borde (requerimientos REQ-F04, REQ-F05, REQ-F08, REQ-N05).
* Documentación de Docker Compose y de la API local de Ollama (`/api/version`, `/v1/systemone`).
* Documentación de hostapd, dnsmasq y systemd-networkd (punto de acceso Wi-Fi).
* MDN Web Docs: validación de formularios HTML (`novalidate`, `input type="number"`).
