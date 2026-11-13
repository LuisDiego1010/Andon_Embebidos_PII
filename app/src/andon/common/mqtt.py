"""Envoltorio de paho-mqtt (compatible con 1.x y 2.x). Payload siempre JSON.

- Reconexión automática; al reconectar se vuelven a suscribir los tópicos y se avisa a
  quien se registró con `al_conectar` (p. ej. para republicar un estado retenido).
- `publicar` nunca lanza: devuelve False si no pudo (el lazo de seguridad no depende de MQTT).
- Un mensaje con JSON inválido se ignora y se deja en el log; nunca mata el hilo de red.
"""

import json
import logging
import threading

from andon.common.topicos import LECTURAS, RETENIDOS

log = logging.getLogger(__name__)
COLA_MAXIMA = 200  # mensajes en cola mientras no hay conexión


def _crear_paho(paho, id_cliente):
    try:  # paho 2.x
        return paho.Client(paho.CallbackAPIVersion.VERSION2, client_id=id_cliente)
    except AttributeError:  # paho 1.x
        return paho.Client(client_id=id_cliente)


def _fallo(rc):
    return rc.is_failure if hasattr(rc, "is_failure") else rc != 0


class ClienteMqtt:
    def __init__(self, host="127.0.0.1", puerto=1883, id_cliente="andon", paho=None, cliente=None):
        self._host, self._puerto = host, puerto
        self._paho = paho or __import__("paho.mqtt.client", fromlist=["Client"])
        self._c = cliente or _crear_paho(self._paho, id_cliente)
        self._subs = []          # [(filtro, callback)]
        self._avisos = []        # callbacks tras (re)conectar
        self._conectado = threading.Event()
        self._cerrando = False
        self._c.on_connect = self._on_connect
        self._c.on_disconnect = self._on_disconnect
        self._c.on_message = self._on_message
        self._c.reconnect_delay_set(min_delay=1, max_delay=10)
        self._c.max_queued_messages_set(COLA_MAXIMA)

    @property
    def conectado(self):
        return self._conectado.is_set()

    def suscribir(self, filtro, callback):
        """callback(topico, dict). Se suscribe en cada (re)conexión."""
        self._subs.append((filtro, callback))
        if self.conectado:
            self._c.subscribe(filtro, qos=1)

    def al_conectar(self, callback):
        self._avisos.append(callback)

    def conectar(self):
        self._c.connect_async(self._host, self._puerto, keepalive=30)
        self._c.loop_start()

    def esperar_conexion(self, timeout):
        return self._conectado.wait(timeout)

    def desconectar(self):
        self._cerrando = True   # desconexión voluntaria: no es una pérdida de red
        try:
            self._c.disconnect()
        finally:
            self._c.loop_stop()

    def publicar(self, topico, payload, retener=None):
        retener = topico in RETENIDOS if retener is None else retener
        try:
            datos = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            info = self._c.publish(topico, datos, qos=0 if topico == LECTURAS else 1, retain=retener)
        except (TypeError, ValueError, OSError) as e:
            log.warning("no se pudo publicar en %s: %s", topico, e)
            return False
        return info.rc == 0

    # --- callbacks de paho (firma distinta entre 1.x y 2.x: *args) ---
    def _on_connect(self, cliente, userdata, flags, rc, *args):
        if _fallo(rc):
            log.error("MQTT: conexión rechazada (%s)", rc)
            return
        self._conectado.set()
        log.info("MQTT conectado a %s:%s", self._host, self._puerto)
        for filtro, _ in self._subs:
            cliente.subscribe(filtro, qos=1)
        for aviso in list(self._avisos):
            try:
                aviso()
            except Exception:
                log.exception("error en al_conectar")

    def _on_disconnect(self, cliente, userdata, *args):
        if self._conectado.is_set() and not self._cerrando:
            log.warning("MQTT desconectado; se reintenta")
        self._conectado.clear()

    def _on_message(self, cliente, userdata, msg):
        try:
            datos = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            log.warning("JSON inválido en %s: %r", msg.topic, msg.payload[:80])
            return
        if not isinstance(datos, dict):
            log.warning("payload no es un objeto en %s", msg.topic)
            return
        for filtro, callback in list(self._subs):
            if self._paho.topic_matches_sub(filtro, msg.topic):
                try:
                    callback(msg.topic, datos)
                except Exception:
                    log.exception("error procesando %s", msg.topic)
