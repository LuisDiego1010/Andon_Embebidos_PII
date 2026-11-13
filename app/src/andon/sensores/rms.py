"""RMS de la vibración a partir de muestras crudas de aceleración (g).

Se calcula sobre la componente dinámica: a cada eje se le resta su media dentro de la
ventana (quita la gravedad y el desvío de montaje) y el RMS del vector es la raíz de la
suma de las varianzas de los tres ejes. El mismo código corre en sim y en la placa.
"""

import math
import threading
from collections import deque

HZ = 100                   # cadencia de muestreo (REQ-F01: >= 100 Hz)
VENTANA_MUESTRAS = HZ      # ventana de 1 s
MINIMO_MUESTRAS = HZ // 2  # no se evalúa con menos de 0,5 s de datos


def rms_dinamico(muestras):
    """RMS de la componente dinámica de una lista de tuplas (ax, ay, az)."""
    n = len(muestras)
    if n == 0:
        return 0.0
    suma_varianzas = 0.0
    for eje in range(3):
        valores = [m[eje] for m in muestras]
        media = sum(valores) / n
        suma_varianzas += sum((v - media) ** 2 for v in valores) / n
    return math.sqrt(suma_varianzas)


class VentanaRms:
    """Ventana deslizante de las últimas `tamano` muestras."""

    def __init__(self, tamano=VENTANA_MUESTRAS, minimo=MINIMO_MUESTRAS):
        self._muestras = deque(maxlen=tamano)
        self._minimo = minimo
        self._lock = threading.Lock()  # el lazo agrega; los comandos limpian

    def agregar(self, ax, ay, az):
        with self._lock:
            self._muestras.append((ax, ay, az))

    def limpiar(self):
        """Descarta lo acumulado (tras reiniciar la máquina, las muestras viejas ya no valen)."""
        with self._lock:
            self._muestras.clear()

    @property
    def listo(self):
        return len(self._muestras) >= self._minimo

    def rms(self):
        """RMS de la ventana, o None si todavía hay pocas muestras."""
        with self._lock:
            copia = list(self._muestras) if len(self._muestras) >= self._minimo else None
        return rms_dinamico(copia) if copia is not None else None
