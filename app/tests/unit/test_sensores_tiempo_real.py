"""andon-sensores con hilos y reloj real: mide el paro de REQ-N04 (< 1 s) en simulación."""
import threading
import time

import pytest

from andon.common import topicos
from andon.common.config import Config
from andon.hal.sim import HalSim
from andon.sensores.servicio import Sensores

from .dobles_mqtt import BrokerFalso


def esperar(condicion, maximo_s):
    t0 = time.monotonic()
    while time.monotonic() - t0 < maximo_s:
        if condicion():
            return time.monotonic() - t0
        time.sleep(0.002)
    return None


@pytest.fixture
def estacion(tmp_path):
    broker = BrokerFalso()
    hal = HalSim()
    svc = Sensores(Config(modo="sim", paro_ruta=str(tmp_path / "paro.json")), hal, broker.cliente())
    svc.iniciar()
    yield svc, hal, broker
    svc.detener()


def test_paro_por_vibracion_en_menos_de_1s(estacion):
    svc, hal, broker = estacion
    assert esperar(lambda: svc.ventana.listo, 2) is not None     # el lazo ya llena la ventana
    assert hal.salidas().maquina is True
    t0 = time.monotonic()
    broker.publicar(topicos.SIM_INYECTAR, {"vib_g": 2.0, "duracion_s": 10}, retener=False)
    asta = esperar(lambda: hal.salidas().maquina is False, 3)
    assert asta is not None, "la máquina nunca se detuvo"
    total = time.monotonic() - t0
    print(f"\nPARO: {total * 1000:.0f} ms desde la inyección; "
          f"{svc.latencia_paro_ms} ms desde la muestra que cruzó el umbral")
    assert total < 1.0, f"REQ-N04: el paro tardó {total:.3f} s"
    assert svc.latencia_paro_ms < 100
    # La máquina se detiene primero; luz, zumbador y aviso van justo después
    assert esperar(lambda: hal.salidas().luz == "roja" and hal.salidas().zumbador, 1) is not None
    assert esperar(lambda: (broker.ultimo(topicos.SEGURIDAD) or {}).get("activo"), 1) is not None


def test_el_lazo_mantiene_100_hz(estacion):
    svc, hal, broker = estacion
    n0, t0 = svc._n, time.monotonic()
    time.sleep(2.0)
    hz = (svc._n - n0) / (time.monotonic() - t0)
    print(f"\nlazo: {hz:.1f} Hz, atrasos: {svc.atrasos}")
    assert 90 <= hz <= 110 and svc.atrasos == 0


def test_publica_lecturas_a_1_hz(estacion):
    svc, hal, broker = estacion
    time.sleep(3.3)
    n = len(broker.de(topicos.LECTURAS))
    assert 3 <= n <= 5
    assert broker.ultimo(topicos.LECTURAS)["temp_c"] is not None


def test_detener_para_los_hilos_y_deja_la_maquina_detenida(tmp_path):
    broker, hal = BrokerFalso(), HalSim()
    svc = Sensores(Config(modo="sim", paro_ruta=str(tmp_path / "p.json")), hal, broker.cliente())
    svc.iniciar()
    time.sleep(0.3)
    antes = threading.active_count()
    svc.detener()
    assert all(not h.is_alive() for h in svc._hilos)
    assert threading.active_count() < antes
    assert hal.salidas().maquina is False and hal.salidas().luz is None
    assert broker.ultimo(topicos.SALIDAS)["maquina"] is False
