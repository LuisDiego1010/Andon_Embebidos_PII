import pytest

from andon.common.config import Config, Gpio
from andon.hal.base import ErrorHardware
from andon.hal.rpi import HalRpi

from .dobles_hw import FakeGpiod, FakeSMBus, FakeSmbusModulo, Value, crear_w1


@pytest.fixture
def gp():
    return FakeGpiod()


@pytest.fixture
def bus():
    return FakeSMBus()


@pytest.fixture
def hal(gp, bus, tmp_path):
    crear_w1(tmp_path)
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    yield h
    h.cerrar()


def test_solicita_las_cinco_lineas_como_salidas_apagadas(hal, gp):
    g = Config().gpio
    assert gp.consumer == "andon-sensores" and gp.chip == g.chip
    assert set(gp.lineas.valores) == {g.maquina, g.verde, g.amarilla, g.roja, g.zumbador}
    assert gp.lineas.activos() == set()


def test_maquina_usa_el_pin_configurado(hal, gp):
    hal.set_maquina(True)
    assert gp.lineas.activos() == {17}
    hal.set_maquina(False)
    assert gp.lineas.activos() == set()


def test_una_sola_luz_a_la_vez(hal, gp):
    hal.set_luz("roja")
    assert gp.lineas.activos() == {23}
    hal.set_luz("verde")
    assert gp.lineas.activos() == {22}
    hal.set_luz("amarilla")
    assert gp.lineas.activos() == {27}
    hal.set_luz(None)
    assert gp.lineas.activos() == set()


def test_pines_personalizados(gp, bus, tmp_path):
    cfg = Config(gpio=Gpio(maquina=5, verde=6, amarilla=12, roja=13, zumbador=16))
    h = HalRpi(cfg, gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    h.set_zumbador(True)
    assert gp.lineas.activos() == {16}
    h.cerrar()


def test_cerrar_libera_gpio_y_bus(hal, gp, bus):
    hal.set_maquina(True)
    hal.set_zumbador(True)
    hal.cerrar()
    assert gp.lineas.liberada and bus.cerrado
    assert gp.lineas.activos() == set()


def test_cerrar_intenta_apagar_todo_aunque_falle_el_gpio(hal, gp):
    hal.set_maquina(True)
    gp.lineas.falla = True
    with pytest.raises(ErrorHardware):
        hal.cerrar()
    assert gp.lineas.liberada  # igual libera


def test_error_de_gpio_se_reporta_como_error_de_hardware(hal, gp):
    gp.lineas.falla = True
    with pytest.raises(ErrorHardware):
        hal.set_maquina(True)
    gp.lineas.falla = False  # para que el cierre del fixture pueda apagar


def test_sin_permiso_en_gpiochip(gp, bus):
    gp.falla_al_abrir = True
    with pytest.raises(ErrorHardware, match="permiso"):
        HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus))


# --- MPU-6050 ---
def test_configura_el_mpu6050(hal, bus):
    hal.leer_acel()
    esc = {reg: v for _, reg, v in bus.escrituras}
    assert esc[0x6B] == 0x01      # despierta, reloj PLL
    assert esc[0x1A] == 0x03      # filtro de 44 Hz
    assert esc[0x19] == 0x00      # 1 kHz internos
    assert esc[0x1C] == 0x08      # ±4 g
    assert all(a == 0x68 for a, _, _ in bus.escrituras)


def test_configura_una_sola_vez(hal, bus):
    hal.leer_acel()
    n = len(bus.escrituras)
    hal.leer_acel()
    assert len(bus.escrituras) == n


def test_conversion_a_g_con_signo(hal, bus):
    bus.muestra = (4096, -8192, 8192)  # +0,5 g, -1 g, +1 g a ±4 g
    assert hal.leer_acel() == pytest.approx((0.5, -1.0, 1.0))


def test_who_am_i_incorrecto(hal, bus):
    bus.who_am_i = 0x12
    with pytest.raises(ErrorHardware, match="WHO_AM_I"):
        hal.leer_acel()


def test_mpu_ausente(hal, bus):
    bus.falla = True
    with pytest.raises(ErrorHardware, match="no responde"):
        hal.leer_acel()


def test_se_reconfigura_tras_un_error_de_lectura(hal, bus):
    hal.leer_acel()
    bus.falla = True
    with pytest.raises(ErrorHardware):
        hal.leer_acel()
    bus.falla = False
    n = len(bus.escrituras)
    hal.leer_acel()
    assert len(bus.escrituras) > n


def test_mpu_ausente_no_golpea_el_bus_en_cada_muestra(gp, bus, tmp_path):
    from andon.hal.rpi import REINTENTO_MPU_S
    t = [0.0]
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path), reloj=lambda: t[0])
    lecturas = []
    bus.read_byte_data = lambda *a: (lecturas.append(a), (_ for _ in ()).throw(OSError(121, "Remote I/O")))[1]
    for _ in range(100):                  # un segundo a 100 Hz
        with pytest.raises(ErrorHardware):
            h.leer_acel()
        t[0] += 0.01
    assert len(lecturas) == int(1 / REINTENTO_MPU_S)
    h.cerrar()


def test_mpu_que_aparece_se_usa_en_el_siguiente_intento(gp, bus, tmp_path):
    from andon.hal.rpi import REINTENTO_MPU_S
    t = [0.0]
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path), reloj=lambda: t[0])
    bus.falla = True
    with pytest.raises(ErrorHardware):
        h.leer_acel()
    bus.falla = False
    t[0] += REINTENTO_MPU_S
    assert h.leer_acel() == (0.0, 0.0, 1.0)
    h.cerrar()


# --- DS18B20 ---
def test_lee_temperatura(hal):
    assert hal.leer_temp() == pytest.approx(25.125)


def test_temperatura_negativa(gp, bus, tmp_path):
    crear_w1(tmp_path, "xx : crc=aa YES\nxx t=-1250\n")
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    assert h.leer_temp() == pytest.approx(-1.25)
    h.cerrar()


@pytest.mark.parametrize("contenido,msg", [
    ("xx : crc=aa NO\nxx t=25000\n", "CRC"),
    ("xx : crc=aa YES\nxx t=85000\n", "85"),
    ("xx : crc=aa YES\nsin temperatura\n", "ilegible"),
    ("", "CRC"),
])
def test_ds18b20_lecturas_invalidas(gp, bus, tmp_path, contenido, msg):
    crear_w1(tmp_path, contenido)
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    with pytest.raises(ErrorHardware, match=msg):
        h.leer_temp()
    h.cerrar()


def test_ds18b20_ausente(gp, bus, tmp_path):
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    with pytest.raises(ErrorHardware, match="no hay DS18B20"):
        h.leer_temp()
    h.cerrar()


# --- diagnóstico ---
def test_verificar_sensores_ok(hal):
    e = hal.verificar_sensores()
    assert e["mpu6050"][0] and e["ds18b20"][0]


def test_verificar_sensores_sin_hardware_no_lanza(gp, bus, tmp_path):
    bus.falla = True
    h = HalRpi(Config(), gpiod_mod=gp, smbus_mod=FakeSmbusModulo(bus), ruta_w1=str(tmp_path))
    e = h.verificar_sensores()
    assert e["mpu6050"][0] is False and e["ds18b20"][0] is False
    h.cerrar()
