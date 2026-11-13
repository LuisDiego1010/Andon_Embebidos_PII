# D7 · Configuración y recarga

- **Estado:** cerrada (F4).
- **Fecha:** 2026-11-06

## Decisión
La configuración vive en un archivo INI (`/etc/andon/andon.conf`, ruta en `ANDON_CONF`) que lee
`common/config.py`; unas pocas variables de entorno lo sobrescriben (`ANDON_MODO`,
`ANDON_MQTT_HOST/PUERTO`, `ANDON_OLLAMA_URL`, `ANDON_PARO_RUTA`, `ANDON_DB_RUTA`). Un archivo
ausente no es error (valores por defecto). **Cambiar la configuración sin reiniciar** se hace
editando el archivo y publicando `andon/e1/cmd/recargar` (CU-07); cada servicio relee el archivo:

| Servicio | Qué recarga |
|---|---|
| andon-sensores | umbrales de vibración y temperatura, tolerancia de falla de sensor |
| andon-core | umbral de confianza, URL, modelo y timeout de Ollama (si cambian URL o modelo, vuelve a calentar) |
| andon-web | PIN y textos (F5) |

Si el archivo recargado es inválido, **se conserva la configuración vigente** y se registra un
error: una edición mala nunca deja la estación sin umbrales.

## Alternativas descartadas
- *Reiniciar el servicio al cambiar la configuración:* un reinicio de `andon-sensores` abre una
  ventana sin lazo de seguridad y vacía la ventana de RMS.
- *Configuración por MQTT (payload en `cmd/recargar`):* obligaría a validar y persistir valores
  que llegan por el bus; el archivo es la única fuente de verdad y queda auditable.

## Límites
- Lo que se lee al arrancar y no se recarga: modo (`sim`/`rpi`), broker MQTT, rutas, GPIO e I2C.
- La recarga de la web no valida el PIN todavía (F5 define quién puede publicar `cmd/recargar`).
