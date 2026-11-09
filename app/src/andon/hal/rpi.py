"""Hardware real de la Raspberry Pi 4 (RPi 5 sin cambios: todo GPIO va por libgpiod v2).

- MPU-6050 (I2C 0x68, smbus2): ±4 g, filtro pasa-bajos de 44 Hz, muestras crudas.
- DS18B20 (1-Wire, sysfs): /sys/bus/w1/devices/28-*/w1_slave, con verificación de CRC.
- MOSFET del ventilador, torre de luces y zumbador: líneas GPIO como salidas (libgpiod).

Los módulos `gpiod` y `smbus2` se pueden inyectar (pruebas sin hardware). Este archivo
se importa solo en la placa: `hal.crear_hal` no lo carga en modo sim.

Seguridad: la compuerta del MOSFET lleva una resistencia a GND (docs/hardware.md); si el
proceso muere, las líneas se liberan y la máquina queda detenida.
"""

import glob
import logging
import os
import threading
import time

from andon.hal.base import HAL, ErrorHardware
from andon.hal.ssd1306 import Ssd1306

log = logging.getLogger(__name__)

# Registros del MPU-6050
REG_SMPLRT_DIV = 0x19
REG_CONFIG = 0x1A
REG_ACCEL_CONFIG = 0x1C
REG_ACCEL_XOUT_H = 0x3B
REG_PWR_MGMT_1 = 0x6B
REG_WHO_AM_I = 0x75

WHO_AM_I_MPU6050 = 0x68
DLPF_44HZ = 0x03        # ancho de banda del acelerómetro: 44 Hz
ACCEL_4G = 0x08         # AFS_SEL = 1
LSB_POR_G = 8192.0      # sensibilidad a ±4 g
RELOJ_PLL_GIRO_X = 0x01

RUTA_W1 = "/sys/bus/w1/devices"
REINICIO_DS18B20_C = 85.0  # valor de arranque: la conversión no se hizo
# Sin MPU-6050, cada intento de iniciarlo toca el bus; en un bus vacío ~1 de cada 1000 queda
# colgado el segundo completo que espera el kernel (medido en la RPi 4, 9 nov). Se reintenta
# como mucho cada medio segundo en vez de 100 veces por segundo. D13 sigue vigilando aparte.
REINTENTO_MPU_S = 0.5


class _BusCompartido:
    """Serializa cada transacción: smbus2 fija la dirección y luego transmite en dos llamadas,
    así que sin cerrojo un hilo podría escribir datos de la OLED en los registros del MPU-6050."""

    def __init__(self, bus, cerrojo):
        self._bus, self._cerrojo = bus, cerrojo

    def write_i2c_block_data(self, direccion, registro, datos):
        with self._cerrojo:
            self._bus.write_i2c_block_data(direccion, registro, datos)


def _con_signo(alto, bajo):
    v = (alto << 8) | bajo
    return v - 65536 if v & 0x8000 else v


class HalRpi(HAL):
    def __init__(self, cfg, gpiod_mod=None, smbus_mod=None, ruta_w1=RUTA_W1, reloj=time.monotonic):
        super().__init__()
        self._cfg = cfg
        self._ruta_w1 = ruta_w1
        self._lock_gpio = threading.Lock()
        self._mpu_listo = False
        self._reloj = reloj
        self._mpu_proximo_intento = 0.0
        self._bus = None
        self._lineas = None
        self._lock_i2c = threading.Lock()
        self._oled = None
        self._oled_lineas = ()
        self._oled_aviso = threading.Event()
        self._oled_fin = False
        self._oled_hilo = None
        self._oled_fallando = False
        try:
            self._gpiod = gpiod_mod or __import__("gpiod")
            smbus = smbus_mod or __import__("smbus2")
            self._abrir_gpio()
            self._bus = smbus.SMBus(cfg.i2c.bus)
        except (ImportError, OSError) as e:
            self._liberar()
            raise ErrorHardware(f"no se pudo abrir el hardware: {e}") from e
        self._oled = Ssd1306(_BusCompartido(self._bus, self._lock_i2c), cfg.i2c.oled)
        self._oled_hilo = threading.Thread(target=self._bucle_oled, name="hal-oled", daemon=True)
        self._oled_hilo.start()

    # --- GPIO ---
    def _pines(self):
        g = self._cfg.gpio
        return {"maquina": g.maquina, "verde": g.verde, "amarilla": g.amarilla,
                "roja": g.roja, "zumbador": g.zumbador}

    def _abrir_gpio(self):
        gp = self._gpiod
        ajuste = gp.LineSettings(direction=gp.line.Direction.OUTPUT,
                                 output_value=gp.line.Value.INACTIVE)
        self._lineas = gp.request_lines(
            self._cfg.gpio.chip, consumer="andon-sensores",
            config={pin: ajuste for pin in self._pines().values()})

    def _poner(self, nombre, activo):
        valor = self._gpiod.line.Value.ACTIVE if activo else self._gpiod.line.Value.INACTIVE
        try:
            with self._lock_gpio:
                if self._lineas is None:
                    raise ErrorHardware("GPIO liberado")
                self._lineas.set_value(self._pines()[nombre], valor)
        except OSError as e:
            raise ErrorHardware(f"GPIO {nombre}: {e}") from e

    def _escribir_maquina(self, encendida):
        self._poner("maquina", encendida)

    def _escribir_luz(self, color):
        # Apaga primero las otras: nunca dos luces a la vez
        for luz in ("verde", "amarilla", "roja"):
            if luz != color:
                self._poner(luz, False)
        if color is not None:
            self._poner(color, True)

    def _escribir_zumbador(self, activo):
        self._poner("zumbador", activo)

    # --- OLED: en su propio hilo. Dibujar tarda decenas de ms y no debe frenar el lazo de
    # seguridad; una pantalla ausente o dañada solo se registra (es informativa).
    def _escribir_oled(self, lineas):
        self._oled_lineas = lineas
        self._oled_aviso.set()

    def _bucle_oled(self):
        while True:
            self._oled_aviso.wait()
            self._oled_aviso.clear()
            if self._oled_fin:
                return
            try:
                self._oled.mostrar(self._oled_lineas)
                self._oled_fallando = False
            except OSError as e:
                self._oled.invalidar()
                if not self._oled_fallando:
                    log.warning("OLED en 0x%02x no responde: %s", self._cfg.i2c.oled, e)
                self._oled_fallando = True

    def _liberar(self):
        if self._oled_hilo is not None:
            self._oled_fin = True
            self._oled_aviso.set()
            self._oled_hilo.join(timeout=2)
            self._oled_hilo = None
        with self._lock_gpio:
            if self._lineas is not None:
                try:
                    self._lineas.release()
                except OSError:
                    pass
                self._lineas = None
        if self._bus is not None:
            try:
                self._bus.close()
            except OSError:
                pass
            self._bus = None

    # --- MPU-6050 ---
    def _iniciar_mpu(self):
        addr = self._cfg.i2c.mpu
        try:
            with self._lock_i2c:
                quien = self._bus.read_byte_data(addr, REG_WHO_AM_I)
                if quien != WHO_AM_I_MPU6050:
                    raise ErrorHardware(f"MPU-6050 en 0x{addr:02x}: WHO_AM_I=0x{quien:02x} (se esperaba 0x68)")
                self._bus.write_byte_data(addr, REG_PWR_MGMT_1, RELOJ_PLL_GIRO_X)  # despierta
                self._bus.write_byte_data(addr, REG_CONFIG, DLPF_44HZ)
                self._bus.write_byte_data(addr, REG_SMPLRT_DIV, 0)                 # 1 kHz internos
                self._bus.write_byte_data(addr, REG_ACCEL_CONFIG, ACCEL_4G)
        except OSError as e:
            raise ErrorHardware(f"MPU-6050 en 0x{addr:02x} no responde: {e}") from e
        self._mpu_listo = True

    def leer_acel(self):
        if self._bus is None:
            raise ErrorHardware("bus I2C cerrado")
        if not self._mpu_listo:
            ahora = self._reloj()
            if ahora < self._mpu_proximo_intento:
                raise ErrorHardware("MPU-6050 sin respuesta (esperando para reintentar)")
            try:
                self._iniciar_mpu()
            except ErrorHardware:
                self._mpu_proximo_intento = ahora + REINTENTO_MPU_S
                raise
        try:
            with self._lock_i2c:
                b = self._bus.read_i2c_block_data(self._cfg.i2c.mpu, REG_ACCEL_XOUT_H, 6)
        except OSError as e:
            self._mpu_listo = False  # reconfigurar si el sensor se reinició
            raise ErrorHardware(f"lectura del MPU-6050: {e}") from e
        return tuple(_con_signo(b[i], b[i + 1]) / LSB_POR_G for i in (0, 2, 4))

    # --- DS18B20 ---
    def _archivo_ds18b20(self):
        hallados = sorted(glob.glob(os.path.join(self._ruta_w1, "28-*", "w1_slave")))
        if not hallados:
            raise ErrorHardware(f"no hay DS18B20 en {self._ruta_w1}/28-*")
        return hallados[0]

    def leer_temp(self):
        ruta = self._archivo_ds18b20()
        try:
            with open(ruta, encoding="ascii") as f:
                lineas = f.read().splitlines()
        except OSError as e:
            raise ErrorHardware(f"DS18B20: {e}") from e
        if len(lineas) < 2 or not lineas[0].rstrip().endswith("YES"):
            raise ErrorHardware("DS18B20: CRC inválido")
        try:
            temp = int(lineas[1].rsplit("t=", 1)[1]) / 1000.0
        except (IndexError, ValueError) as e:
            raise ErrorHardware(f"DS18B20: lectura ilegible {lineas[1]!r}") from e
        if temp == REINICIO_DS18B20_C:
            raise ErrorHardware("DS18B20: 85 °C es el valor de arranque, conversión no hecha")
        return temp

    # --- diagnóstico ---
    def verificar_sensores(self):
        """{'mpu6050': (ok, detalle), 'ds18b20': (ok, detalle)}. No lanza."""
        estado = {}
        try:
            self._iniciar_mpu()
            ax, ay, az = self.leer_acel()
            estado["mpu6050"] = (True, f"a=({ax:+.3f}, {ay:+.3f}, {az:+.3f}) g")
        except ErrorHardware as e:
            estado["mpu6050"] = (False, str(e))
        try:
            estado["ds18b20"] = (True, f"{self.leer_temp():.2f} °C")
        except ErrorHardware as e:
            estado["ds18b20"] = (False, str(e))
        return estado
