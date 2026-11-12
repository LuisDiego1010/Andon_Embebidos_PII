"""Modo híbrido (D18): sensores de HalSim, salidas por GPIO e I2C reales."""
import time

import pytest

from andon.common.config import Config, ErrorConfig, cargar
from andon.hal import crear_hal
from andon.hal.base import ErrorHardware
from andon.hal.hibrido import HalHibrido
from andon.hal.sim import HalSim

from .dobles_hw import FakeGpiod, FakeSMBus, FakeSmbusModulo


class Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def gp():
    return FakeGpiod()


@pytest.fixture
def bus():
    return FakeSMBus()


@pytest.fixture
def hal(gp, bus):
    h = HalHibrido(Config(), sim=HalSim(reloj=Reloj()), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus))
    yield h
    h.cerrar()


def rms_z(h, n=100):
    m = [h.leer_acel()[2] - 1.0 for _ in range(n)]
    return (sum(x * x for x in m) / n) ** 0.5


def test_luces_y_zumbador_van_a_los_gpio(hal, gp):
    hal.set_luz("roja")
    hal.set_zumbador(True)
    assert gp.lineas.activos() == {23, 24}
    hal.set_luz("verde")
    hal.set_zumbador(False)
    assert gp.lineas.activos() == {22}


def test_oled_escribe_en_el_bus_i2c(hal, bus):
    hal.mostrar_oled(["Andon E1", "OK"])
    limite = time.monotonic() + 2      # la OLED se dibuja en su propio hilo
    while not bus.bloques and time.monotonic() < limite:
        time.sleep(0.01)
    assert bus.bloques and all(addr == 0x3C for addr, _, _ in bus.bloques)


def test_nunca_toca_los_sensores_reales(hal, bus):
    hal.set_maquina(True)
    for _ in range(50):
        hal.leer_acel()
    hal.leer_temp()
    assert bus.escrituras == []    # sin configurar el MPU-6050 (0x68)


def test_la_vibracion_simulada_sigue_a_la_maquina_real(hal, gp):
    hal.ajustar(vib_g=2.0, ruido_g=0.0)
    assert rms_z(hal) < 0.01                      # máquina detenida: sin vibración
    hal.set_maquina(True)
    assert gp.lineas.activos() == {17}            # el MOSFET recibe la orden
    assert rms_z(hal) > 0.5


def test_sensor_desconectado_desde_el_panel(hal):
    hal.ajustar(mpu_ok=False, ds18b20_ok=False)
    with pytest.raises(ErrorHardware):
        hal.leer_acel()
    with pytest.raises(ErrorHardware):
        hal.leer_temp()


def test_cerrar_deja_todo_apagado(hal, gp):
    hal.set_maquina(True)
    hal.set_luz("amarilla")
    hal.cerrar()
    assert gp.lineas.activos() == set() and gp.lineas.liberada


def test_crear_hal_y_config(tmp_path):
    cfg = cargar(ruta=str(tmp_path / "no-existe.conf"), entorno={"ANDON_MODO": "hibrido"})
    assert cfg.modo == "hibrido" and cfg.entradas_simuladas
    assert Config(modo="sim").entradas_simuladas and not Config(modo="rpi").entradas_simuladas
    with pytest.raises(ErrorHardware):    # en la PC no hay gpiod: falla como el modo rpi
        crear_hal(cfg)


def test_modo_invalido_sigue_rechazado(tmp_path):
    with pytest.raises(ErrorConfig):
        cargar(ruta=str(tmp_path / "x.conf"), entorno={"ANDON_MODO": "mixto"})
