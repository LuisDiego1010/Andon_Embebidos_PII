"""Con un Mosquitto real (docker compose up -d mosquitto). Se omite si no hay broker.
Host: ANDON_MQTT_HOST (por defecto localhost). Deje detenido el servicio `sensores` de compose."""
import os
import socket
import time
import uuid

import pytest

from andon.common import topicos
from andon.common.config import Config
from andon.common.mqtt import ClienteMqtt
from andon.hal.sim import HalSim
from andon.sensores.servicio import Sensores

HOST = os.environ.get("ANDON_MQTT_HOST", "localhost")
PUERTO = int(os.environ.get("ANDON_MQTT_PUERTO", "1883"))

pytestmark = pytest.mark.integracion


def _hay_broker():
    try:
        socket.create_connection((HOST, PUERTO), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _requiere_broker():
    if not _hay_broker():
        pytest.skip(f"no hay broker MQTT en {HOST}:{PUERTO}")


def cliente(nombre):
    c = ClienteMqtt(HOST, PUERTO, f"{nombre}-{uuid.uuid4().hex[:6]}")
    return c


def esperar(cond, maximo_s):
    t0 = time.monotonic()
    while time.monotonic() - t0 < maximo_s:
        if cond():
            return time.monotonic() - t0
        time.sleep(0.005)
    return None


def limpiar_retenidos(*topicos_):
    c = cliente("limpieza")
    c.conectar()
    assert c.esperar_conexion(5)
    for t in topicos_:
        c._c.publish(t, b"", qos=1, retain=True).wait_for_publish(2)
    time.sleep(0.2)
    c.desconectar()


def test_ida_y_vuelta_y_retenido():
    topico = f"andon/e1/prueba/{uuid.uuid4().hex}"
    emisor, receptor = cliente("emisor"), cliente("receptor")
    emisor.conectar()
    assert emisor.esperar_conexion(5)
    assert emisor.publicar(topico, {"x": 1, "texto": "ñandú"}, retener=True)
    time.sleep(0.3)
    recibidos = []
    receptor.suscribir(topico, lambda t, d: recibidos.append(d))   # llega tarde: debe recibir el retenido
    receptor.conectar()
    assert esperar(lambda: recibidos, 5) is not None
    assert recibidos[0] == {"x": 1, "texto": "ñandú"}
    emisor._c.publish(topico, b"", qos=1, retain=True).wait_for_publish(2)   # limpiar
    emisor.desconectar()
    receptor.desconectar()


def test_paro_de_extremo_a_extremo_con_mqtt_real(tmp_path):
    """Inyección por MQTT → paro → `seguridad` retenido en el broker, todo < 1 s."""
    limpiar_retenidos(topicos.SEGURIDAD, topicos.SALIDAS)
    hal = HalSim()
    svc = Sensores(Config(modo="sim", mqtt=Config().mqtt.__class__(HOST, PUERTO),
                          paro_ruta=str(tmp_path / "paro.json")),
                   hal, cliente("sensores"))
    web = cliente("web")
    seguridad = []
    web.suscribir(topicos.SEGURIDAD, lambda t, d: seguridad.append(d))
    web.conectar()
    assert web.esperar_conexion(5)
    svc.iniciar()
    try:
        assert esperar(lambda: svc.ventana.listo, 3) is not None
        t0 = time.monotonic()
        web.publicar(topicos.SIM_INYECTAR, {"vib_g": 2.0, "duracion_s": 10})
        espera = esperar(lambda: any(m["activo"] for m in seguridad), 3)
        assert espera is not None, "no llegó el aviso de seguridad"
        total = time.monotonic() - t0
        print(f"\nextremo a extremo (inyección → aviso en la web): {total * 1000:.0f} ms")
        assert total < 1.0 and hal.salidas().maquina is False
        # Reinicio por MQTT: origen web libera; origen core no
        web.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "core"})
        time.sleep(0.4)
        assert svc.seguridad.activo
    finally:
        svc.detener()
        web.desconectar()
        limpiar_retenidos(topicos.SEGURIDAD, topicos.SALIDAS)
