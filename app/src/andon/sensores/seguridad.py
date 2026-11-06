"""Lógica del paro de seguridad. Sin MQTT, sin hilos y sin hardware: solo decide.

- Paro por umbral (REQ-F07): vibración RMS o temperatura por ENCIMA de su umbral.
- Falla de sensor (D13): sin lectura válida durante `tolerancia_fallo_s` seguidos
  (incluye un sensor que se cuelga y deja de responder) → paro igual que por umbral.
- El paro queda retenido: solo `reiniciar()` lo libera. Mientras está retenido no cambia
  de causa. Todo el estado se puede guardar en disco para sobrevivir a un reinicio.
"""

import json
import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)

VIBRACION = "vibracion"
TEMPERATURA = "temperatura"
SENSORES = ("mpu6050", "ds18b20")


@dataclass(frozen=True)
class Paro:
    sensor: str     # "vibracion" | "temperatura" | "mpu6050_fallo" | "ds18b20_fallo"
    valor: float    # valor medido (o segundos sin lectura, en una falla de sensor)
    umbral: float   # umbral cruzado (o tolerancia, en una falla de sensor)


class Seguridad:
    def __init__(self, umbrales, tolerancia_fallo_s, ahora):
        self.umbrales = umbrales
        self.tolerancia_fallo_s = tolerancia_fallo_s
        self.causa = None
        self._ultima_lectura = {s: ahora for s in SENSORES}

    @property
    def activo(self):
        return self.causa is not None

    def _disparar(self, paro):
        if self.causa is not None:
            return None  # ya retenido: se conserva la primera causa
        self.causa = paro
        log.error("PARO %s: valor=%.3f umbral=%.3f", paro.sensor, paro.valor, paro.umbral)
        return paro

    def evaluar_vibracion(self, rms_g):
        if rms_g > self.umbrales.vib_rms_g:
            return self._disparar(Paro(VIBRACION, rms_g, self.umbrales.vib_rms_g))
        return None

    def evaluar_temperatura(self, temp_c):
        if temp_c > self.umbrales.temp_c:
            return self._disparar(Paro(TEMPERATURA, temp_c, self.umbrales.temp_c))
        return None

    def lectura_ok(self, sensor, ahora):
        self._ultima_lectura[sensor] = ahora

    def vigilar(self, ahora):
        """Falla de sensor: ninguno puede pasar más de la tolerancia sin una lectura válida."""
        for sensor, ultima in self._ultima_lectura.items():
            sin_lectura = ahora - ultima
            if sin_lectura > self.tolerancia_fallo_s:
                return self._disparar(Paro(f"{sensor}_fallo", round(sin_lectura, 3), self.tolerancia_fallo_s))
        return None

    def restaurar(self, paro, ahora):
        """Recupera un paro guardado en disco (el servicio se reinició con el paro activo)."""
        self.causa = paro
        self._ultima_lectura = {s: ahora for s in SENSORES}

    def reiniciar(self, ahora):
        """Libera el paro. Devuelve True si había uno. Da a cada sensor una gracia nueva."""
        habia = self.causa is not None
        self.causa = None
        self._ultima_lectura = {s: ahora for s in SENSORES}
        return habia

    def actualizar(self, umbrales, tolerancia_fallo_s):
        """Recarga en caliente (CU-07). No toca un paro ya retenido."""
        self.umbrales = umbrales
        self.tolerancia_fallo_s = tolerancia_fallo_s

    def payload(self, ts):
        """Cuerpo del tópico `seguridad` (retenido)."""
        c = self.causa
        return {"ts": ts, "activo": c is not None,
                "sensor": c.sensor if c else None,
                "valor": c.valor if c else None,
                "umbral": c.umbral if c else None}


# --- persistencia: el paro sobrevive a un reinicio del servicio o de la estación ---
def guardar_paro(ruta, paro, ts):
    """Escritura atómica. Devuelve False (y lo deja en el log) si no se pudo."""
    try:
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sensor": paro.sensor, "valor": paro.valor, "umbral": paro.umbral, "ts": ts}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
        return True
    except OSError as e:
        log.error("no se pudo guardar el paro en %s: %s", ruta, e)
        return False


def leer_paro(ruta):
    """Paro guardado, o None si no hay o el archivo es ilegible."""
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        return Paro(str(d["sensor"]), float(d["valor"]), float(d["umbral"]))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.error("archivo de paro ilegible (%s): %s; se asume paro activo por seguridad", ruta, e)
        return Paro("paro_guardado_ilegible", 0.0, 0.0)


def borrar_paro(ruta):
    try:
        os.remove(ruta)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("no se pudo borrar %s: %s", ruta, e)
