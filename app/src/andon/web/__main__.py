"""Punto de entrada de andon-web: `python3 -m andon.web`."""
import logging
import sys

from andon.common.config import ErrorConfig, cargar
from andon.common.log import configurar
from andon.common.mqtt import ClienteMqtt
from andon.web.app import crear_app
from andon.web.servicio import ServicioWeb

log = logging.getLogger("andon.web")


def main():
    configurar()
    try:
        cfg = cargar()
    except ErrorConfig as e:
        log.critical("configuración inválida: %s", e)
        return 2
    servicio = ServicioWeb(cfg, ClienteMqtt(cfg.mqtt.host, cfg.mqtt.puerto, "andon-web"))
    servicio.preparar()
    try:
        crear_app(servicio).run(host=cfg.web.host, port=cfg.web.puerto, threaded=True)
    except OSError as e:
        log.critical("no se pudo abrir el puerto %s: %s", cfg.web.puerto, e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
