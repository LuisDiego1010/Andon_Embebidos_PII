"""Pantalla LCD de caracteres HD44780 (16x2) con adaptador I2C PCF8574, sobre smbus2 (D18).

Alternativa a la OLED SSD1306 (`[i2c] pantalla = lcd1602`). El adaptador suele responder en 0x27.
Se maneja en modo de 4 bits: cada byte se manda en dos mitades, con un pulso en la línea E.

Bits del PCF8574: P0 = RS (0 comando, 1 dato), P1 = RW (siempre 0), P2 = E, P3 = luz de fondo,
P4..P7 = D4..D7.

Las líneas que llegan (hasta 4, pensadas para la OLED) se acomodan en las 2 filas: se juntan con un
espacio mientras quepan. Solo ASCII: las tildes se quitan y lo demás se muestra como «?».
"""

import time
import unicodedata

COLUMNAS = 16
FILAS = 2
RS = 0x01
E = 0x04
LUZ = 0x08
INICIO_FILA = (0x80, 0xC0)      # dirección de la DDRAM de cada fila
CONFIGURAR = (0x28, 0x0C, 0x06)  # 4 bits y 2 líneas; pantalla encendida sin cursor; avance a la derecha
BORRAR = 0x01


def a_ascii(texto):
    """«é» → «e», «ñ» → «n»; lo que no tiene equivalente (un emoji, un salto de línea) → «?»."""
    salida = []
    for c in texto:
        base = unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode("ascii")[:1]
        salida.append(base if base and 0x20 <= ord(base) <= 0x7E else "?")
    return "".join(salida)


def acomodar(lineas, columnas=COLUMNAS, filas=FILAS):
    """Reparte las líneas en `filas` filas de `columnas` caracteres, rellenas con espacios."""
    salida = []
    for linea in (a_ascii(str(l)).strip() for l in lineas):
        if not linea:
            continue
        if salida and len(salida[-1]) + 1 + len(linea) <= columnas:
            salida[-1] += " " + linea
        else:
            salida.append(linea)
    salida = (salida + [""] * filas)[:filas]
    return [f[:columnas].ljust(columnas) for f in salida]


class Lcd1602:
    """`bus` es un SMBus abierto (basta `write_byte`). Los errores de I2C se propagan como OSError."""

    def __init__(self, bus, direccion, dormir=time.sleep):
        self._bus, self._dir, self._dormir = bus, direccion, dormir
        self._actual = None     # filas en pantalla; None obliga a reiniciar y redibujar

    def invalidar(self):
        self._actual = None

    def _mitad(self, valor):
        self._bus.write_byte(self._dir, valor | LUZ | E)
        self._bus.write_byte(self._dir, (valor | LUZ) & ~E)   # el HD44780 lee en el flanco de bajada

    def _byte(self, valor, modo=0):
        self._mitad((valor & 0xF0) | modo)
        self._mitad(((valor << 4) & 0xF0) | modo)

    def _iniciar(self):
        self._bus.write_byte(self._dir, LUZ)
        self._dormir(0.05)
        for mitad in (0x30, 0x30, 0x30, 0x20):   # secuencia de la hoja de datos para entrar en 4 bits
            self._mitad(mitad)
            self._dormir(0.005)
        for comando in CONFIGURAR:
            self._byte(comando)
        self._byte(BORRAR)
        self._dormir(0.002)                       # borrar tarda 1,52 ms

    def mostrar(self, lineas):
        filas = acomodar(lineas)
        if self._actual is None:
            self._iniciar()
            previas = [None] * FILAS
        else:
            previas = self._actual
        self._actual = None     # si algo falla a medias, la próxima vez se reinicia todo
        for numero, (nueva, previa) in enumerate(zip(filas, previas)):
            if nueva == previa:
                continue
            self._byte(INICIO_FILA[numero])
            for caracter in nueva:
                self._byte(ord(caracter), RS)
        self._actual = filas
