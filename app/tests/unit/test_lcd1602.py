"""LCD 16x2 HD44780 con adaptador PCF8574 (D18)."""
import pytest

from andon.hal.lcd1602 import E, LUZ, RS, Lcd1602, a_ascii, acomodar

from .dobles_hw import FakeSMBus


def decodificar(escrituras):
    """Reconstruye (modo, byte) de cada par de mitades leídas en el flanco de bajada de E."""
    # cada mitad se manda con E en alto y luego en bajo: vale la escritura que baja E
    flancos = []
    previo = None
    for _, v in escrituras:
        if previo is not None and previo & E and not v & E:
            flancos.append(v)
        previo = v
    return flancos


def texto_escrito(bus):
    """Caracteres enviados como datos (RS = 1), después de la secuencia de arranque."""
    f = decodificar(bus.bytes)
    datos = []
    for alta, baja in zip(f[::2], f[1::2]):
        if alta & RS:
            datos.append(chr((alta & 0xF0) | (baja >> 4)))
    return "".join(datos)


def test_acomoda_las_lineas_en_dos_filas():
    assert acomodar(["OPERANDO", "Todo normal"]) == ["OPERANDO        ", "Todo normal     "]
    assert acomodar(["PARO", "vibracion", "1.08>1.00"]) == ["PARO vibracion  ", "1.08>1.00       "]
    assert acomodar(["Aviso supervision largo"]) == ["Aviso supervisio", " " * 16]
    assert acomodar([]) == [" " * 16, " " * 16]


def test_quita_tildes_y_marca_lo_que_no_es_ascii():
    assert a_ascii("Revisión ñandú") == "Revision nandu"
    assert a_ascii("ruido 🔧") == "ruido ?"


def test_primera_vez_inicia_en_4_bits_con_luz_y_escribe():
    bus = FakeSMBus()
    Lcd1602(bus, 0x27, dormir=lambda s: None).mostrar(["OPERANDO", "Todo normal"])
    assert {a for a, _ in bus.bytes} == {0x27}
    assert all(v & LUZ for _, v in bus.bytes)            # la luz de fondo nunca se apaga
    assert decodificar(bus.bytes)[:4] == [0x30 | LUZ, 0x30 | LUZ, 0x30 | LUZ, 0x20 | LUZ]
    assert texto_escrito(bus) == "OPERANDO        Todo normal     "


def test_solo_reescribe_la_fila_que_cambia():
    bus = FakeSMBus()
    lcd = Lcd1602(bus, 0x27, dormir=lambda s: None)
    lcd.mostrar(["OPERANDO", "Todo normal"])
    bus.bytes.clear()
    lcd.mostrar(["OPERANDO", "Aviso a calidad"])
    assert texto_escrito(bus) == "Aviso a calidad "
    bus.bytes.clear()
    lcd.mostrar(["OPERANDO", "Aviso a calidad"])
    assert bus.bytes == []


def test_un_error_se_propaga_y_la_proxima_vez_reinicia():
    bus = FakeSMBus()
    lcd = Lcd1602(bus, 0x27, dormir=lambda s: None)
    bus.falla_oled = True
    with pytest.raises(OSError):
        lcd.mostrar(["PARO"])
    bus.falla_oled = False
    lcd.mostrar(["PARO"])
    assert decodificar(bus.bytes)[:4] == [0x30 | LUZ, 0x30 | LUZ, 0x30 | LUZ, 0x20 | LUZ]
    assert texto_escrito(bus).startswith("PARO")
