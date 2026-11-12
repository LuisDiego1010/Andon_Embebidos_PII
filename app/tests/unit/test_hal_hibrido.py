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


def test_lcd1602_desde_la_configuracion(gp):
    from andon.common.config import I2c
    bus = FakeSMBus()
    h = HalHibrido(Config(i2c=I2c(oled=0x27, pantalla="lcd1602")), sim=HalSim(reloj=Reloj()),
                   gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus))
    h.mostrar_oled(["OPERANDO", "Todo normal"])
    limite = time.monotonic() + 2
    while not bus.bytes and time.monotonic() < limite:
        time.sleep(0.01)
    h.cerrar()
    assert bus.bytes and all(addr == 0x27 for addr, _ in bus.bytes) and bus.bloques == []


def test_pantalla_que_no_responde_no_afecta_las_salidas(gp):
    from andon.common.config import I2c
    bus = FakeSMBus()
    bus.falla_oled = True
    h = HalHibrido(Config(i2c=I2c(oled=0x27, pantalla="lcd1602")), sim=HalSim(reloj=Reloj()),
                   gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus))
    for i in range(20):
        h.mostrar_oled([f"PARO {i}"])
        h.set_luz("roja" if i % 2 else "verde")
    h.set_luz("roja")
    assert gp.lineas.activos() == {23}
    h.cerrar()


@pytest.mark.parametrize("texto", ["[i2c]\npantalla = lcd2004\n", "[i2c]\noled = 0x99\n"])
def test_pantalla_invalida_se_rechaza(tmp_path, texto):
    r = tmp_path / "a.conf"
    r.write_text(texto)
    with pytest.raises(ErrorConfig):
        cargar(ruta=str(r), entorno={})


def test_pantalla_lcd_desde_el_archivo(tmp_path):
    r = tmp_path / "a.conf"
    r.write_text("[i2c]\npantalla = lcd1602\noled = 0x27\n")
    c = cargar(ruta=str(r), entorno={})
    assert c.i2c.pantalla == "lcd1602" and c.i2c.oled == 0x27
