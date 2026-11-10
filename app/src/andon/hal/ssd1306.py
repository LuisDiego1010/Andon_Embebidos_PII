"""Controlador mínimo de la OLED SSD1306 de 128x64 por I2C (D5), sobre smbus2.

Texto de 4 líneas y 21 columnas con una fuente de 5x7. Solo ASCII: lo demás se muestra como «?».
Escribe en bloques cortos y solo las páginas que cambiaron, para no ocupar el bus que comparte
con el MPU-6050.
"""

ANCHO = 128
PAGINAS = 8
PAGINAS_DE_TEXTO = (0, 2, 4, 6)  # una línea sí y una no, para que se lea a distancia
BLOQUE = 30                      # smbus2 admite hasta 32 bytes por escritura
CONTROL_COMANDO = 0x00
CONTROL_DATOS = 0x40

INICIO = (0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8,
          0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF)

# ASCII 0x20 a 0x7E, 5 columnas por carácter
_FUENTE = bytes.fromhex(
    "0000000000 00005F0000 0007000700 147F147F14 242A7F2A12 2313086462 3649562050 0008070300"
    "001C224100 0041221C00 2A1C7F1C2A 08083E0808 0080703000 0808080808 0000606000 2010080402"
    "3E5149453E 00427F4000 7249494946 2141494D33 1814127F10 2745454539 3C4A494931 4121110907"
    "3649494936 464949291E 0000140000 0040340000 0008142241 1414141414 0041221408 0201590906"
    "3E415D594E 7C1211127C 7F49494936 3E41414122 7F4141413E 7F49494941 7F09090901 3E41415173"
    "7F0808087F 00417F4100 2040413F01 7F08142241 7F40404040 7F021C027F 7F0408107F 3E4141413E"
    "7F09090906 3E4151215E 7F09192946 2649494932 03017F0103 3F4040403F 1F2040201F 3F4038403F"
    "6314081463 0304780403 6159494D43 007F414141 0204081020 004141417F 0402010204 4040404040"
    "0003070800 2054547840 7F28444438 3844444428 384444287F 3854545418 00087E0902 18A4A49C78"
    "7F08040478 00447D4000 2040403D00 7F10284400 00417F4000 7C04780478 7C08040478 3844444438"
    "FC18242418 18242418FC 7C08040408 4854545424 04043F4424 3C4040207C 1C2040201C 3C4030403C"
    "4428102844 4C9090907C 4464544C44 0008364100 0000770000 0041360800 0201020402"
)


def glifo(caracter):
    codigo = ord(caracter)
    if not 0x20 <= codigo <= 0x7E:
        codigo = ord("?")
    inicio = (codigo - 0x20) * 5
    return _FUENTE[inicio:inicio + 5]


def renderizar(lineas):
    """Devuelve las 8 páginas (128 bytes cada una) con el texto dado."""
    paginas = [bytearray(ANCHO) for _ in range(PAGINAS)]
    for pagina, linea in zip(PAGINAS_DE_TEXTO, lineas):
        columna = 0
        for caracter in linea[:ANCHO // 6]:
            paginas[pagina][columna:columna + 5] = glifo(caracter)
            columna += 6
    return [bytes(p) for p in paginas]


class Ssd1306:
    """`bus` es un SMBus abierto. Los errores de I2C se propagan como OSError."""

    def __init__(self, bus, direccion):
        self._bus, self._dir = bus, direccion
        self._actual = None     # páginas en pantalla; None obliga a reiniciar y redibujar

    def invalidar(self):
        self._actual = None

    def _comandos(self, valores):
        for i in range(0, len(valores), BLOQUE):
            self._bus.write_i2c_block_data(self._dir, CONTROL_COMANDO, list(valores[i:i + BLOQUE]))

    def mostrar(self, lineas):
        paginas = renderizar(lineas)
        if self._actual is None:
            self._comandos(INICIO)
            previas = [None] * PAGINAS
        else:
            previas = self._actual
        self._actual = None     # si algo falla a medias, la próxima vez se redibuja todo
        for numero, (nueva, previa) in enumerate(zip(paginas, previas)):
            if nueva == previa:
                continue
            self._comandos((0x21, 0, ANCHO - 1, 0x22, numero, numero))
            for i in range(0, ANCHO, BLOQUE):
                self._bus.write_i2c_block_data(self._dir, CONTROL_DATOS, list(nueva[i:i + BLOQUE]))
        self._actual = paginas
