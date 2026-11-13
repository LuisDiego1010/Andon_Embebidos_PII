"""Las MISMAS pruebas para hal/sim.py y hal/rpi.py (criterio de salida de F2)."""
import pytest

from andon.common.config import Config
from andon.hal.base import OLED_COLUMNAS, OLED_LINEAS, ErrorHardware, Salidas
from andon.hal.hibrido import HalHibrido
from andon.hal.rpi import HalRpi
from andon.hal.sim import HalSim

from .dobles_hw import FakeGpiod, FakeSMBus, FakeSmbusModulo, crear_w1


@pytest.fixture(params=["sim", "rpi", "hibrido"])
def hal(request, tmp_path):
    if request.param == "sim":
        h = HalSim()
    elif request.param == "hibrido":
        h = HalHibrido(Config(), gpiod_mod=FakeGpiod(), smbus_mod=FakeSmbusModulo(FakeSMBus()))
    else:
        crear_w1(tmp_path)
        h = HalRpi(Config(), gpiod_mod=FakeGpiod(),
                   smbus_mod=FakeSmbusModulo(FakeSMBus()), ruta_w1=str(tmp_path))
    yield h
    h.cerrar()


def test_estado_inicial_en_reposo(hal):
    assert hal.salidas() == Salidas(maquina=False, luz=None, zumbador=False, oled=())


def test_maquina(hal):
    hal.set_maquina(True)
    assert hal.salidas().maquina is True
    hal.set_maquina(False)
    assert hal.salidas().maquina is False


@pytest.mark.parametrize("color", ["verde", "amarilla", "roja", None])
def test_luz(hal, color):
    hal.set_luz(color)
    assert hal.salidas().luz == color


def test_luz_invalida(hal):
    with pytest.raises(ValueError):
        hal.set_luz("azul")
    assert hal.salidas().luz is None


def test_zumbador(hal):
    hal.set_zumbador(True)
    assert hal.salidas().zumbador is True
    hal.set_zumbador(False)
    assert hal.salidas().zumbador is False


def test_oled_recorta_lineas_y_columnas(hal):
    hal.mostrar_oled(["a" * 50, "b", "c", "d", "e"])
    o = hal.salidas().oled
    assert len(o) == OLED_LINEAS and len(o[0]) == OLED_COLUMNAS


def test_observadores_solo_en_cambios(hal):
    eventos = []
    hal.suscribir(lambda n, v: eventos.append((n, v)))
    hal.set_luz("roja")
    hal.set_luz("roja")  # repetido: sin evento
    hal.set_maquina(True)
    assert eventos == [("luz", "roja"), ("maquina", True)]


def test_aceleracion_en_reposo_mide_1g_en_z(hal):
    ax, ay, az = hal.leer_acel()
    assert abs(ax) < 0.2 and abs(ay) < 0.2 and az == pytest.approx(1.0, abs=0.15)


def test_temperatura_plausible(hal):
    assert 10 < hal.leer_temp() < 60


def test_cerrar_deja_todo_en_reposo_y_es_idempotente(hal):
    hal.set_maquina(True)
    hal.set_luz("verde")
    hal.set_zumbador(True)
    hal.cerrar()
    hal.cerrar()
    assert hal.salidas() == Salidas(maquina=False, luz=None, zumbador=False, oled=())
    with pytest.raises(ErrorHardware):
        hal.set_maquina(True)


def test_contexto_cierra(tmp_path):
    with HalSim() as h:
        h.set_maquina(True)
    assert h.salidas().maquina is False
