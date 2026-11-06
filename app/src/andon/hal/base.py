"""Interfaz de hardware (HAL). `sim.py` y `rpi.py` implementan lo mismo y pasan las
mismas pruebas (tests/unit/test_hal_interfaz.py).

Solo `andon-sensores` usa esta interfaz (invariante: único proceso que toca hardware).

Convenciones:
- aceleración en g (el eje z mide ≈ +1 g en reposo), temperatura en °C;
- `set_luz` enciende UNA sola luz de la torre (o ninguna con None);
- las salidas son idempotentes y `cerrar()` las deja en reposo: máquina detenida,
  luces y zumbador apagados.
"""

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from andon.common.topicos import LUCES

OLED_LINEAS = 4
OLED_COLUMNAS = 21


class ErrorHardware(Exception):
    """Fallo de lectura o escritura en un periférico."""


@dataclass(frozen=True)
class Salidas:
    """Último estado ordenado a las salidas."""
    maquina: bool = False
    luz: str | None = None
    zumbador: bool = False
    oled: tuple = ()


class HAL(ABC):
    def __init__(self):
        self._salidas = Salidas()
        self._observadores = []
        self._cerrado = False
        self._cerrojo = threading.Lock()

    # --- entradas (las implementa cada plataforma) ---
    @abstractmethod
    def leer_acel(self):
        """Una muestra cruda (ax, ay, az) en g. Se llama a ~100 Hz."""

    @abstractmethod
    def leer_temp(self):
        """Temperatura en °C. Puede tardar ~750 ms (DS18B20): llamar desde un hilo aparte."""

    # --- salidas: ganchos de cada plataforma ---
    @abstractmethod
    def _escribir_maquina(self, encendida): ...

    @abstractmethod
    def _escribir_luz(self, color): ...

    @abstractmethod
    def _escribir_zumbador(self, activo): ...

    def _escribir_oled(self, lineas):
        """El controlador de la OLED llega después de F3 (D5): por defecto no hace nada."""

    def _liberar(self):
        """Libera recursos de la plataforma (bus, líneas GPIO)."""

    # --- API pública ---
    def set_maquina(self, encendida):
        self._aplicar("maquina", bool(encendida), self._escribir_maquina)

    def set_luz(self, color):
        if color is not None and color not in LUCES:
            raise ValueError(f"luz inválida: {color!r} (use {LUCES} o None)")
        self._aplicar("luz", color, self._escribir_luz)

    def set_zumbador(self, activo):
        self._aplicar("zumbador", bool(activo), self._escribir_zumbador)

    def mostrar_oled(self, lineas):
        recortadas = tuple(str(l)[:OLED_COLUMNAS] for l in list(lineas)[:OLED_LINEAS])
        self._aplicar("oled", recortadas, self._escribir_oled)

    def salidas(self):
        return self._salidas

    def suscribir(self, callback):
        """callback(nombre, valor) en cada cambio de salida (el tablero la usa en sim)."""
        self._observadores.append(callback)

    def cerrar(self):
        """Deja todo en reposo y libera la plataforma. Idempotente."""
        with self._cerrojo:
            if self._cerrado:
                return
            self._cerrado = True
        errores = []
        for nombre, valor, escribir in (("maquina", False, self._escribir_maquina),
                                        ("luz", None, self._escribir_luz),
                                        ("zumbador", False, self._escribir_zumbador)):
            try:
                self._aplicar(nombre, valor, escribir, forzar=True)
            except ErrorHardware as e:  # seguir apagando el resto
                errores.append(e)
        self._liberar()
        if errores:
            raise ErrorHardware("; ".join(str(e) for e in errores))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    # --- interno ---
    def _aplicar(self, nombre, valor, escribir, forzar=False):
        with self._cerrojo:
            if self._cerrado and not forzar:
                raise ErrorHardware("HAL cerrado")
            if not forzar and getattr(self._salidas, nombre) == valor:
                return
        escribir(valor)
        with self._cerrojo:
            self._salidas = Salidas(**{**self._salidas.__dict__, nombre: valor})
        for cb in list(self._observadores):
            cb(nombre, valor)
