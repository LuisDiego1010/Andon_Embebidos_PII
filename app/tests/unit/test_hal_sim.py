import math

import pytest

from andon.common.config import Config
from andon.hal import crear_hal
from andon.hal.base import ErrorHardware
from andon.hal.sim import PASO_TEMP_C, HalSim


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def rms_1s(hal, reloj, n=100):
    """RMS de la componente dinámica del vector de aceleración en una ventana de n muestras a 100 Hz."""
    m = []
    for _ in range(n):
        m.append(hal.leer_acel())
        reloj.avanzar(0.01)
    medias = [sum(x[i] for x in m) / n for i in range(3)]
    return math.sqrt(sum((x[i] - medias[i]) ** 2 for x in m for i in range(3)) / n)


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def sim(reloj):
    h = HalSim(reloj=reloj)
    h.set_maquina(True)
    return h


def test_rms_nominal(sim, reloj):
    assert rms_1s(sim, reloj) == pytest.approx(0.10, rel=0.08)


def test_gravedad_en_z(sim, reloj):
    z = [sim.leer_acel()[2] for _ in range(100) if not reloj.avanzar(0.01)]
    assert sum(z) / len(z) == pytest.approx(1.0, abs=0.02)


def test_maquina_apagada_solo_ruido(sim, reloj):
    sim.set_maquina(False)
    assert rms_1s(sim, reloj) < 0.03


def test_inyeccion_de_vibracion_y_retorno(sim, reloj):
    sim.inyectar(vib_g=2.0, duracion_s=5)
    assert rms_1s(sim, reloj) == pytest.approx(2.0, rel=0.05)
    reloj.avanzar(10)
    assert rms_1s(sim, reloj) == pytest.approx(0.10, rel=0.08)


def test_vibracion_inyectada_desaparece_al_parar(sim, reloj):
    sim.inyectar(vib_g=2.0, duracion_s=30)
    sim.set_maquina(False)  # paro por umbral: el aspa se detiene
    assert rms_1s(sim, reloj) < 0.03


def test_inyeccion_de_temperatura(sim, reloj):
    sim.inyectar(temp_c=90.0, duracion_s=5)
    assert sim.leer_temp() == pytest.approx(90.0, abs=PASO_TEMP_C)
    reloj.avanzar(6)
    assert sim.leer_temp() < 40


def test_inyeccion_invalida(sim):
    with pytest.raises(ValueError):
        sim.inyectar(vib_g=1.0, duracion_s=0)


def test_temperatura_primer_orden(sim, reloj):
    sim.leer_temp()
    reloj.avanzar(600)  # 10 constantes de tiempo
    t = sim.leer_temp()
    assert t == pytest.approx(40.0, abs=0.1)
    assert (t / PASO_TEMP_C) == pytest.approx(round(t / PASO_TEMP_C))  # cuantizada como el DS18B20


def test_temperatura_sube_gradualmente(sim, reloj):
    sim.leer_temp()
    reloj.avanzar(30)
    assert 25.5 < sim.leer_temp() < 35


def test_determinista_con_la_misma_semilla():
    a, b = Reloj(), Reloj()
    ha, hb = HalSim(reloj=a, semilla=7), HalSim(reloj=b, semilla=7)
    ha.set_maquina(True)
    hb.set_maquina(True)
    assert [ha.leer_acel() for _ in range(20)] == [hb.leer_acel() for _ in range(20)]


def test_crear_hal_sim():
    assert isinstance(crear_hal(Config(modo="sim")), HalSim)


def test_crear_hal_rpi_sin_gpiod(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "gpiod", None)  # fuerza ImportError
    with pytest.raises(ErrorHardware):
        crear_hal(Config(modo="rpi"))
