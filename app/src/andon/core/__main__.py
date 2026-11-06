"""Punto de entrada de andon-core: `python3 -m andon.core`."""
import logging
import signal
import sqlite3
import sys

from andon.common.config import ErrorConfig, cargar
from andon.common.log import configurar
from andon.common.mqtt import ClienteMqtt
from andon.core.registro import Registro
from andon.core.servicio import Core

log = logging.getLogger("andon.core")


def main():
    configurar()
    try:
        cfg = cargar()
    except ErrorConfig as e:
        log.critical("configuración inválida: %s", e)
        return 2
    try:
        registro = Registro(cfg.db_ruta)
    except (OSError, sqlite3.Error) as e:   # sin registro no hay REQ-F10: que systemd reintente
        log.critical("no se pudo abrir el registro %s: %s", cfg.db_ruta, e)
        return 1
    mqtt = ClienteMqtt(cfg.mqtt.host, cfg.mqtt.puerto, "andon-core")
    servicio = Core(cfg, mqtt, registro)
    for senal in (signal.SIGTERM, signal.SIGINT):
        signal.signal(senal, lambda *_: servicio.solicitar_fin())
    servicio.iniciar()
    servicio.esperar()
    servicio.detener()
    return 0


if __name__ == "__main__":
    sys.exit(main())
