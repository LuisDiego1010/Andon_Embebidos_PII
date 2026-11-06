import json

import pytest
from paho.mqtt import client as paho

from andon.common import topicos
from andon.common.mqtt import ClienteMqtt


class Info:
    rc = 0


class PahoFalso:
    """Imita un paho.Client lo justo para probar el envoltorio."""

    def __init__(self):
        self.publicados, self.suscripciones = [], []
        self.conexion = None
        self.vivo = False
        self.rc_publicar = 0

    def reconnect_delay_set(self, **k): pass
    def max_queued_messages_set(self, n): self.cola = n
    def connect_async(self, host, puerto, keepalive=60): self.conexion = (host, puerto, keepalive)
    def loop_start(self): self.vivo = True
    def loop_stop(self): self.vivo = False
    def disconnect(self): pass
    def subscribe(self, topico, qos=0): self.suscripciones.append((topico, qos))

    def publish(self, topico, payload, qos=0, retain=False):
        self.publicados.append((topico, payload, qos, retain))
        info = Info()
        info.rc = self.rc_publicar
        return info


class Msg:
    def __init__(self, topic, payload):
        self.topic, self.payload = topic, payload if isinstance(payload, bytes) else json.dumps(payload).encode()


class RcPaho2:
    def __init__(self, falla):
        self.is_failure = falla


@pytest.fixture
def pf():
    return PahoFalso()


@pytest.fixture
def mqtt(pf):
    return ClienteMqtt("broker", 1884, "prueba", paho=paho, cliente=pf)


def test_conectar_usa_connect_async_y_loop(mqtt, pf):
    mqtt.conectar()
    assert pf.conexion == ("broker", 1884, 30) and pf.vivo


def test_publicar_json_y_retencion_por_topico(mqtt, pf):
    assert mqtt.publicar(topicos.SEGURIDAD, {"activo": True, "sensor": "vibración"})
    t, payload, qos, retain = pf.publicados[-1]
    assert t == topicos.SEGURIDAD and retain is True and qos == 1
    assert json.loads(payload) == {"activo": True, "sensor": "vibración"}  # sin escapar el UTF-8
    mqtt.publicar(topicos.LECTURAS, {"vib_rms_g": 0.1})
    assert pf.publicados[-1][2:] == (0, False)   # lecturas: QoS 0, no retenido
    mqtt.publicar(topicos.EVENTO, {"x": 1}, retener=True)
    assert pf.publicados[-1][3] is True


def test_publicar_no_lanza(mqtt, pf):
    assert mqtt.publicar("t", {"x": object()}) is False       # no serializable
    assert mqtt.publicar("t", {"x": float("nan")}) is False   # NaN no es JSON válido
    pf.rc_publicar = 4
    assert mqtt.publicar("t", {"x": 1}) is False


@pytest.mark.parametrize("rc,ok", [(0, True), (5, False), (RcPaho2(False), True), (RcPaho2(True), False)])
def test_on_connect_acepta_paho_1_y_2(mqtt, pf, rc, ok):
    mqtt.suscribir("a/b", lambda t, d: None)
    mqtt._on_connect(pf, None, {}, rc, None)   # paho 2 pasa un argumento más
    assert mqtt.conectado is ok
    assert (("a/b", 1) in pf.suscripciones) is ok


def test_al_reconectar_se_resuscribe_y_se_avisa(mqtt, pf):
    llamadas = []
    mqtt.suscribir("a/b", lambda t, d: None)
    mqtt.al_conectar(lambda: llamadas.append(1))
    mqtt._on_connect(pf, None, {}, 0)
    mqtt._on_disconnect(pf, None, 0)
    assert not mqtt.conectado
    mqtt._on_connect(pf, None, {}, 0)
    assert pf.suscripciones.count(("a/b", 1)) == 2 and llamadas == [1, 1]


def test_suscribir_estando_conectado_suscribe_ya(mqtt, pf):
    mqtt._on_connect(pf, None, {}, 0)
    mqtt.suscribir("x/y", lambda t, d: None)
    assert ("x/y", 1) in pf.suscripciones


def test_aviso_que_falla_no_rompe_la_conexion(mqtt, pf):
    llamadas = []
    mqtt.al_conectar(lambda: 1 / 0)
    mqtt.al_conectar(lambda: llamadas.append(1))
    mqtt._on_connect(pf, None, {}, 0)
    assert mqtt.conectado and llamadas == [1]


def test_mensaje_se_entrega_como_dict(mqtt, pf):
    recibidos = []
    mqtt.suscribir("andon/e1/cmd/#", lambda t, d: recibidos.append((t, d)))
    mqtt.suscribir("otro", lambda t, d: recibidos.append(("mal", d)))
    mqtt._on_message(pf, None, Msg("andon/e1/cmd/maquina", {"accion": "parar"}))
    assert recibidos == [("andon/e1/cmd/maquina", {"accion": "parar"})]


@pytest.mark.parametrize("crudo", [b"no es json", b"\xff\xfe", b"[1, 2]", b'"texto"', b"42", b""])
def test_payload_invalido_se_ignora(mqtt, pf, crudo):
    recibidos = []
    mqtt.suscribir("t", lambda t, d: recibidos.append(d))
    mqtt._on_message(pf, None, Msg("t", crudo))
    assert recibidos == []


def test_error_en_el_callback_no_se_propaga(mqtt, pf):
    llamadas = []
    mqtt.suscribir("t", lambda t, d: 1 / 0)
    mqtt.suscribir("t", lambda t, d: llamadas.append(d))
    mqtt._on_message(pf, None, Msg("t", {"a": 1}))
    assert llamadas == [{"a": 1}]


def test_desconexion_voluntaria_no_avisa_de_perdida(mqtt, pf, caplog):
    mqtt._on_connect(pf, None, {}, 0)
    with caplog.at_level("WARNING"):
        mqtt.desconectar()
        mqtt._on_disconnect(pf, None, 0)
    assert "se reintenta" not in caplog.text


def test_perdida_de_conexion_si_avisa(mqtt, pf, caplog):
    mqtt._on_connect(pf, None, {}, 0)
    with caplog.at_level("WARNING"):
        mqtt._on_disconnect(pf, None, 7)
    assert "se reintenta" in caplog.text
