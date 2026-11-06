"""Configuración mínima de logging. En systemd la salida va a journald."""
import logging
import os


def configurar(nivel=None):
    nivel = (nivel or os.environ.get("ANDON_LOG", "INFO")).upper()
    logging.basicConfig(level=getattr(logging, nivel, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
