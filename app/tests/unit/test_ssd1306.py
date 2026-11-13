"""Controlador de la OLED y su convivencia con el MPU-6050 en el mismo bus."""
import threading
import time

from andon.common.config import Config
from andon.hal import ssd1306
from andon.hal.rpi import HalRpi
from andon.hal.ssd1306 import Ssd1306, glifo, renderizar

from .dobles_hw import FakeGpiod, FakeSMBus, FakeSmbusModulo


def datos(bus):
    return [b for b in bus.bloques if b[1] == ssd1306.CONTROL_DATOS]


def esperar(condicion, timeout=2.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.005)
    return False


def hal(bus, tmp_path):
    return HalRpi(Config(), gpiod_mod=FakeGpiod(), smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))


def test_fuente_completa():
    assert len(ssd1306._FUENTE) == (0x7F - 0x20) * 5


def test_glifo_conocido_y_no_ascii():
    assert glifo("A") == bytes.fromhex("7C1211127C")
    assert glifo("ñ") == glifo("?")


def test_renderizar_ubica_las_lineas_en_paginas_alternas():
    p = renderizar(["A", "B"])
    assert p[0][:5] == glifo("A") and p[2][:5] == glifo("B")
    assert p[1] == bytes(128) and p[4] == bytes(128)


def test_21_columnas_caben_en_el_ancho():
    p = renderizar(["M" * 30])
    assert p[0][120:125] == glifo("M") and p[0][125:] == bytes(3)


def test_primera_vez_inicializa_y_dibuja_las_8_paginas():
    bus = FakeSMBus()
    Ssd1306(bus, 0x3C).mostrar(["HOLA"])
    comandos = [v for b in bus.bloques if b[1] == ssd1306.CONTROL_COMANDO for v in b[2]]
    assert comandos[:len(ssd1306.INICIO)] == list(ssd1306.INICIO)
    assert sum(len(b[2]) for b in datos(bus)) == 128 * 8
    assert all(len(b[2]) <= 32 for b in bus.bloques)


def test_solo_reescribe_las_paginas_que_cambian():
    bus = FakeSMBus()
    o = Ssd1306(bus, 0x3C)
    o.mostrar(["A", "B"])
    bus.bloques.clear()
    o.mostrar(["A", "C"])
    assert sum(len(b[2]) for b in datos(bus)) == 128
    assert not any(b[2][:len(ssd1306.INICIO)] == list(ssd1306.INICIO) for b in bus.bloques)


def test_tras_un_fallo_reinicia_y_redibuja():
    bus = FakeSMBus()
    o = Ssd1306(bus, 0x3C)
    o.mostrar(["A"])
    bus.falla_oled = True
    try:
        o.mostrar(["B"])
    except OSError:
        pass
    bus.falla_oled = False
    bus.bloques.clear()
    o.mostrar(["B"])
    assert sum(len(b[2]) for b in datos(bus)) == 128 * 8


def test_hal_dibuja_en_segundo_plano(tmp_path):
    bus = FakeSMBus()
    h = hal(bus, tmp_path)
    h.mostrar_oled(["PARO"])
    assert esperar(lambda: len(datos(bus)) > 0)
    h.cerrar()


def test_oled_ausente_no_afecta_al_sensor_ni_lanza(tmp_path):
    bus = FakeSMBus()
    bus.falla_oled = True
    h = hal(bus, tmp_path)
    h.mostrar_oled(["PARO"])
    time.sleep(0.05)
    assert h.salidas().oled == ("PARO",)
    assert h.leer_acel() == (0.0, 0.0, 1.0)
    h.cerrar()


def test_oled_lenta_no_frena_la_llamada(tmp_path):
    bus = FakeSMBus()
    original = bus.write_i2c_block_data
    bus.write_i2c_block_data = lambda *a: (time.sleep(0.01), original(*a))
    h = hal(bus, tmp_path)
    t0 = time.monotonic()
    h.mostrar_oled(["PARO"])
    assert time.monotonic() - t0 < 0.005
    h.cerrar()


def test_oled_y_sensor_nunca_usan_el_bus_a_la_vez(tmp_path):
    bus = FakeSMBus()
    dentro, solapes = [], []
    cerrojo = threading.Lock()

    def envolver(fn):
        def f(*a):
            with cerrojo:
                dentro.append(1)
                if len(dentro) > 1:
                    solapes.append(a)
            time.sleep(0.0002)
            with cerrojo:
                dentro.pop()
            return fn(*a)
        return f
    bus.write_i2c_block_data = envolver(bus.write_i2c_block_data)
    bus.read_i2c_block_data = envolver(bus.read_i2c_block_data)
    h = hal(bus, tmp_path)
    for i in range(30):
        h.mostrar_oled([f"linea {i}"])
        h.leer_acel()
    time.sleep(0.1)
    h.cerrar()
    assert solapes == []
