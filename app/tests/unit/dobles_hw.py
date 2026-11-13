"""Dobles de gpiod v2, smbus2 y sysfs de 1-Wire para probar hal/rpi.py sin hardware."""
import enum
from pathlib import Path


class Direction(enum.Enum):
    INPUT = 1
    OUTPUT = 2


class Value(enum.Enum):
    INACTIVE = 0
    ACTIVE = 1


class _Line:
    Direction = Direction
    Value = Value


class LineSettings:
    def __init__(self, direction=None, output_value=None):
        self.direction = direction
        self.output_value = output_value


class FakeLineas:
    def __init__(self, config):
        self.valores = {pin: s.output_value for pin, s in config.items()}
        self.ajustes = config
        self.liberada = False
        self.falla = False

    def set_value(self, pin, valor):
        if self.falla:
            raise OSError("bus GPIO caído")
        self.valores[pin] = valor

    def activos(self):
        return {p for p, v in self.valores.items() if v == Value.ACTIVE}

    def release(self):
        self.liberada = True


class FakeGpiod:
    """Imita el paquete `gpiod` v2 (solo lo que usa HalRpi)."""
    line = _Line
    LineSettings = LineSettings

    def __init__(self):
        self.chip = None
        self.consumer = None
        self.lineas = None
        self.falla_al_abrir = False

    def request_lines(self, chip, consumer, config):
        if self.falla_al_abrir:
            raise PermissionError("/dev/gpiochip0: permiso denegado")
        self.chip, self.consumer = chip, consumer
        self.lineas = FakeLineas(config)
        return self.lineas


class FakeSMBus:
    def __init__(self, who_am_i=0x68, muestra=(0, 0, 8192)):
        self.who_am_i = who_am_i
        self.muestra = muestra  # cuentas crudas (ax, ay, az)
        self.escrituras = []
        self.bloques = []
        self.bytes = []
        self.falla_oled = False
        self.cerrado = False
        self.falla = False

    def read_byte_data(self, addr, reg):
        if self.falla:
            raise OSError(121, "Remote I/O error")
        assert reg == 0x75
        return self.who_am_i

    def write_byte_data(self, addr, reg, valor):
        if self.falla:
            raise OSError(121, "Remote I/O error")
        self.escrituras.append((addr, reg, valor))

    def write_i2c_block_data(self, addr, reg, datos):
        if self.falla or self.falla_oled:
            raise OSError(121, "Remote I/O error")
        assert len(datos) <= 32
        self.bloques.append((addr, reg, list(datos)))

    def write_byte(self, addr, valor):          # adaptador PCF8574 de la LCD
        if self.falla or self.falla_oled:
            raise OSError(121, "Remote I/O error")
        assert 0 <= valor <= 0xFF
        self.bytes.append((addr, valor))

    def read_i2c_block_data(self, addr, reg, n):
        if self.falla:
            raise OSError(121, "Remote I/O error")
        assert (reg, n) == (0x3B, 6)
        datos = []
        for v in self.muestra:
            v &= 0xFFFF
            datos += [v >> 8, v & 0xFF]
        return datos

    def close(self):
        self.cerrado = True


class FakeSmbusModulo:
    def __init__(self, bus):
        self.bus = bus
        self.abierto = None

    def SMBus(self, numero):
        self.abierto = numero
        return self.bus


def crear_w1(raiz: Path, contenido="a1 01 4b 46 7f ff 0c 10 d8 : crc=d8 YES\n"
                                    "a1 01 4b 46 7f ff 0c 10 d8 t=25125\n"):
    """Imita /sys/bus/w1/devices con un DS18B20."""
    d = raiz / "28-0316a2793e4b"
    d.mkdir(parents=True)
    (d / "w1_slave").write_text(contenido, encoding="ascii")
    (raiz / "w1_bus_master1").mkdir()
    return d / "w1_slave"
