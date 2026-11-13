"""Modo híbrido (ANDON_MODO=hibrido, D18): sensores simulados, salidas reales.

Para mostrar la torre de luces, el zumbador y la OLED físicos sin MPU-6050 ni DS18B20:
- entradas (`leer_acel`, `leer_temp`, `ajustar`, `inyectar`) → `HalSim`, movido desde el
  panel /simulador igual que en modo sim;
- salidas (GPIO de LEDs, zumbador y MOSFET; OLED por I2C) → `HalRpi`, mismo mapa de pines
  de docs/hardware.md.

El simulador sigue el estado de la máquina (con la máquina detenida no hay vibración), así
que el paro, el reinicio con PIN y D13 se comportan igual que en modo sim. HalRpi nunca toca
el MPU-6050 ni el DS18B20 en este modo: solo se usan sus salidas.
"""

from andon.hal.rpi import HalRpi
from andon.hal.sim import HalSim


class HalHibrido(HalRpi):
    def __init__(self, cfg, sim=None, **kw):
        self._sim = sim or HalSim()
        super().__init__(cfg, **kw)

    # --- entradas simuladas ---
    def leer_acel(self):
        return self._sim.leer_acel()

    def leer_temp(self):
        return self._sim.leer_temp()

    def ajustar(self, **campos):
        self._sim.ajustar(**campos)

    def inyectar(self, **kw):
        self._sim.inyectar(**kw)

    def verificar_sensores(self):
        return {n: (True, "simulado (modo híbrido)") for n in ("mpu6050", "ds18b20")}

    # --- salidas reales; la máquina también se informa al simulador ---
    def _escribir_maquina(self, encendida):
        super()._escribir_maquina(encendida)
        self._sim.set_maquina(encendida)
