"""Broker MQTT en memoria para probar los servicios sin Mosquitto. Entrega de forma síncrona."""
import copy
import threading

from paho.mqtt.client import topic_matches_sub


class ClienteFalso:
    """Mismo API que andon.common.mqtt.ClienteMqtt."""

    def __init__(self, broker):
        self._b = broker
        self._subs = []
        self._avisos = []
        self.conectado = False

    def suscribir(self, filtro, callback):
        self._subs.append((filtro, callback))
        if self.conectado:
            self._b._entregar_retenidos(self, filtro, callback)

    def al_conectar(self, callback):
        self._avisos.append(callback)

    def conectar(self):
        self.conectado = True
        for filtro, cb in list(self._subs):
            self._b._entregar_retenidos(self, filtro, cb)
        for aviso in list(self._avisos):
            aviso()

    def esperar_conexion(self, timeout):
        return self.conectado

    def desconectar(self):
        self.conectado = False

    def publicar(self, topico, payload, retener=None):
        return self._b.publicar(topico, payload, retener)


class BrokerFalso:
    def __init__(self, retenidos_de=()):
        from andon.common.topicos import RETENIDOS
        self._ret_por_defecto = RETENIDOS
        self.retenidos = {}
        self.mensajes = []          # (topico, payload) en orden
        self._clientes = []
        self._lock = threading.Lock()

    def cliente(self):
        c = ClienteFalso(self)
        self._clientes.append(c)
        return c

    def publicar(self, topico, payload, retener=None):
        retener = topico in self._ret_por_defecto if retener is None else retener
        payload = copy.deepcopy(payload)
        with self._lock:
            self.mensajes.append((topico, payload))
            if retener:
                self.retenidos[topico] = payload
            destinos = [(c, cb) for c in self._clientes if c.conectado
                        for filtro, cb in c._subs if topic_matches_sub(filtro, topico)]
        for _, cb in destinos:
            cb(topico, copy.deepcopy(payload))
        return True

    def _entregar_retenidos(self, cliente, filtro, cb):
        for topico, payload in list(self.retenidos.items()):
            if topic_matches_sub(filtro, topico):
                cb(topico, copy.deepcopy(payload))

    # --- ayudas para las pruebas ---
    def de(self, topico):
        return [p for t, p in self.mensajes if t == topico]

    def ultimo(self, topico):
        m = self.de(topico)
        return m[-1] if m else None
