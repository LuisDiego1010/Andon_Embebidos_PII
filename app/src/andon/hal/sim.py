"""Hardware simulado (ANDON_MODO=sim). Genera MUESTRAS CRUDAS de aceleración a la
cadencia con que se le pida (100 Hz en la placa), no el RMS ya calculado: el cálculo
y los umbrales son el mismo código que en la placa (D6).

Modelo:
- Máquina encendida: vibración RMS nominal `vib_rms_g` repartida en los tres ejes
  (senoides de 25 Hz, ciclo entero por ventana de 1 s) + ruido; apagada: solo ruido.
- Gravedad en z (+1 g) y un pequeño desvío de montaje.
- Temperatura de primer orden hacia ambiente (apagada) o ambiente + calentamiento
  (encendida), cuantizada a 0,0625 °C como el DS18B20.
- `inyectar()` fuerza una falla temporal. La vibración inyectada existe mientras la
  máquina gira: tras un paro desaparece, como un aspa desbalanceada que se detiene.
"""

import math
import random
import threading
import time

from andon.hal.base import HAL, ErrorHardware, Salidas

FREC_HZ = 25.0
PASO_TEMP_C = 0.0625

# Controles del panel /simulador (sim/ajustar). Persisten hasta que se vuelvan a mover.
AJUSTES_INICIALES = {"vib_g": 0.10, "ruido_g": 0.01, "temp_c": None, "mpu_ok": True, "ds18b20_ok": True}
_RANGOS = {"vib_g": (0.0, 3.0), "ruido_g": (0.0, 0.5), "temp_c": (0.0, 120.0)}


def validar_ajustes(campos):
    """Copia validada de `campos`. `temp_c` None = modelo térmico automático. Lanza ValueError."""
    limpios = {}
    for clave, valor in campos.items():
        if clave not in AJUSTES_INICIALES:
            raise ValueError(f"control desconocido: {clave}")
        if clave in ("mpu_ok", "ds18b20_ok"):
            if not isinstance(valor, bool):
                raise ValueError(f"{clave}: debe ser verdadero o falso")
        elif not (clave == "temp_c" and valor is None):
            minimo, maximo = _RANGOS[clave]
            if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                    or not math.isfinite(valor) or not minimo <= valor <= maximo):
                raise ValueError(f"{clave}: debe estar entre {minimo:g} y {maximo:g}")
        limpios[clave] = valor
    return limpios


class HalSim(HAL):
    def __init__(self, reloj=time.monotonic, semilla=1, vib_rms_g=0.10, ruido_g=0.01,
                 ambiente_c=25.0, calentamiento_c=15.0, tau_s=60.0, maquina_inicial=False):
        super().__init__()
        self._reloj = reloj
        self._rng = random.Random(semilla)
        self.vib_rms_g = vib_rms_g
        self.ruido_g = ruido_g
        self.ambiente_c = ambiente_c
        self.calentamiento_c = calentamiento_c
        self.tau_s = tau_s
        self._temp_c = ambiente_c
        self._t_temp = reloj()
        self._inyeccion = None  # (vib_g|None, temp_c|None, vence_en)
        self._temp_manual = None
        self._mpu_ok = True
        self._ds18b20_ok = True
        self._lock = threading.Lock()
        self._salidas = Salidas(maquina=maquina_inicial)

    # --- inyección de fallas (tópico sim/inyectar) ---
    def inyectar(self, vib_g=None, temp_c=None, duracion_s=5.0):
        if duracion_s <= 0:
            raise ValueError("duracion_s debe ser positiva")
        with self._lock:
            self._inyeccion = (vib_g, temp_c, self._reloj() + duracion_s)

    def ajustar(self, **campos):
        """Controles del panel: `vib_g`, `ruido_g`, `temp_c`, `mpu_ok`, `ds18b20_ok`."""
        c = validar_ajustes(campos)
        with self._lock:
            self.vib_rms_g = c.get("vib_g", self.vib_rms_g)
            self.ruido_g = c.get("ruido_g", self.ruido_g)
            self._temp_manual = c.get("temp_c", self._temp_manual)
            self._mpu_ok = c.get("mpu_ok", self._mpu_ok)
            self._ds18b20_ok = c.get("ds18b20_ok", self._ds18b20_ok)

    def _inyeccion_activa(self, ahora):
        with self._lock:
            if self._inyeccion and ahora >= self._inyeccion[2]:
                self._inyeccion = None
            return self._inyeccion

    # --- entradas ---
    def leer_acel(self):
        if not self._mpu_ok:
            raise ErrorHardware("MPU-6050 desconectado (simulado)")
        t = self._reloj()
        inj = self._inyeccion_activa(t)
        vib = 0.0
        if self._salidas.maquina:
            vib = inj[0] if inj and inj[0] is not None else self.vib_rms_g
        por_eje = vib / math.sqrt(3)       # RMS por eje
        amp = por_eje * math.sqrt(2)       # amplitud de la senoide
        w = 2 * math.pi * FREC_HZ * t
        g = self._rng.gauss
        return (0.02 + amp * math.sin(w) + g(0, self.ruido_g),
                -0.01 + amp * math.sin(w + 2.0) + g(0, self.ruido_g),
                1.00 + amp * math.sin(w + 4.0) + g(0, self.ruido_g))

    def leer_temp(self):
        if not self._ds18b20_ok:
            raise ErrorHardware("DS18B20 desconectado (simulado)")
        t = self._reloj()
        inj = self._inyeccion_activa(t)
        objetivo = self.ambiente_c + (self.calentamiento_c if self._salidas.maquina else 0.0)
        dt = max(0.0, t - self._t_temp)
        self._temp_c += (objetivo - self._temp_c) * (1 - math.exp(-dt / self.tau_s))
        self._t_temp = t
        base = self._temp_c if self._temp_manual is None else self._temp_manual
        valor = inj[1] if inj and inj[1] is not None else base
        return round(valor / PASO_TEMP_C) * PASO_TEMP_C

    # --- salidas: solo quedan registradas (salidas()/suscribir) ---
    def _escribir_maquina(self, encendida): pass
    def _escribir_luz(self, color): pass
    def _escribir_zumbador(self, activo): pass
    def _escribir_oled(self, lineas): pass
