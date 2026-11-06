"""andon-sensores: el ÚNICO proceso que toca el hardware y corre el lazo de seguridad.

Hilos:
- acelerómetro, 100 Hz: lee, acumula, evalúa el RMS de 1 s cada 100 ms y decide el paro;
- temperatura, 1 Hz (el DS18B20 tarda ~750 ms por lectura);
- publicación, 1 Hz: `lecturas` y el vigilante de fallas de sensor.
Los comandos MQTT llegan por el hilo de red de paho.

Invariantes (CLAUDE.md): el paro se decide aquí, sin MQTT ni modelo; queda retenido hasta
`cmd/maquina: reiniciar` de origen `web` (el PIN lo valida la web); ningún resultado del
modelo arranca la máquina; una falla de sensor es un paro retenido (D13).
La lógica de cada paso (`paso_*`) es pública para probarla con un reloj falso.
"""

import logging
import math
import threading
import time

from andon.common import topicos
from andon.common.config import ErrorConfig, cargar
from andon.hal.base import ErrorHardware
from andon.sensores.rms import HZ, VentanaRms
from andon.sensores.seguridad import Seguridad, borrar_paro, guardar_paro, leer_paro

log = logging.getLogger(__name__)

PERIODO_ACEL_S = 1.0 / HZ
EVALUAR_CADA = HZ // 10      # el RMS se evalúa cada 100 ms
PERIODO_TEMP_S = 1.0
PERIODO_PUB_S = 1.0
ORIGENES_PARAR = ("core", "web")
ORIGEN_REINICIAR = "web"


def _es_numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _r3(x):
    return None if x is None else round(x, 3)


class Sensores:
    def __init__(self, cfg, hal, mqtt, reloj=time.monotonic, ahora=time.time, cargador=cargar):
        self.cfg, self.hal, self.mqtt = cfg, hal, mqtt
        self._reloj, self._ahora, self._cargador = reloj, ahora, cargador
        self.seguridad = Seguridad(cfg.umbrales, cfg.sensores.tolerancia_fallo_s, reloj())
        self.ventana = VentanaRms()
        self._lock = threading.RLock()   # serializa transiciones de seguridad y comandos
        self._fin = threading.Event()
        self._hilos = []
        self._n = 0
        self._vib = None
        self._temp = None
        self._fallos_avisados = {}
        self.parada_manual = False
        self.latencia_paro_ms = None     # de la muestra que cruzó el umbral a la máquina detenida
        self.atrasos = 0                 # veces que el lazo de 100 Hz se retrasó más de 10 periodos

    # ------------------------------------------------------------------ ciclo de vida
    def preparar(self):
        """Suscripciones, conexión MQTT y arranque de la estación (sin lanzar hilos)."""
        self.mqtt.suscribir(topicos.CMD_MAQUINA, self._on_maquina)
        self.mqtt.suscribir(topicos.CMD_SENAL, self._on_senal)
        self.mqtt.suscribir(topicos.CMD_RECARGAR, self._on_recargar)
        if self.cfg.modo == "sim":      # sim/inyectar no existe fuera del modo sim (D11)
            self.mqtt.suscribir(topicos.SIM_INYECTAR, self._on_inyectar)
        self.mqtt.al_conectar(self._republicar)
        self.hal.suscribir(self._on_salida)
        self.mqtt.conectar()
        self._arrancar()

    def iniciar(self):
        self.preparar()
        self._fin.clear()
        for nombre, periodo, paso in (("acel", PERIODO_ACEL_S, self.paso_acel),
                                      ("temp", PERIODO_TEMP_S, self.paso_temp),
                                      ("pub", PERIODO_PUB_S, self.paso_publicar)):
            h = threading.Thread(target=self._periodico, args=(nombre, periodo, paso),
                                 name=f"sensores-{nombre}", daemon=True)
            h.start()
            self._hilos.append(h)
        log.info("andon-sensores en marcha (modo %s)", self.cfg.modo)

    def solicitar_fin(self):
        self._fin.set()

    def esperar(self):
        self._fin.wait()

    def detener(self):
        """Para los hilos y deja el hardware en reposo (máquina detenida)."""
        self._fin.set()
        for h in self._hilos:
            h.join(timeout=3)
        try:
            self.hal.cerrar()
        except ErrorHardware as e:
            log.error("al cerrar el hardware: %s", e)
        self.mqtt.desconectar()
        log.info("andon-sensores detenido")

    def _arrancar(self):
        """Arranque de la estación. Si el servicio cayó con un paro activo, sigue en paro."""
        with self._lock:
            paro = leer_paro(self.cfg.paro_ruta)
            if paro is not None:
                self.seguridad.restaurar(paro, self._reloj())
                log.error("arranca con un paro retenido (%s): la máquina sigue detenida", paro.sensor)
                self._aplicar_paro(paro, None, guardar=False)
            else:
                self._hacer(self.hal.set_maquina, True)
                self._hacer(self.hal.set_luz, "verde")
                self._hacer(self.hal.mostrar_oled, ["OPERANDO"])
                self._publicar_seguridad()
            self._publicar_salidas()

    def _periodico(self, nombre, periodo, paso):
        siguiente = self._reloj()
        while not self._fin.is_set():
            try:
                paso()
            except Exception:
                log.exception("fallo inesperado en el hilo %s", nombre)
            siguiente += periodo
            espera = siguiente - self._reloj()
            if espera > 0:
                self._fin.wait(espera)
            elif espera < -10 * periodo:
                self.atrasos += 1
                log.warning("el hilo %s se retrasó %.0f ms (%d veces)", nombre, -espera * 1000, self.atrasos)
                siguiente = self._reloj()

    # ------------------------------------------------------------------ pasos del lazo
    def paso_acel(self):
        try:
            ax, ay, az = self.hal.leer_acel()
        except ErrorHardware as e:
            self._avisar_fallo("mpu6050", e)
        else:
            t = self._reloj()
            self.ventana.agregar(ax, ay, az)
            with self._lock:
                self.seguridad.lectura_ok("mpu6050", t)
        self._n += 1
        if self._n % EVALUAR_CADA == 0:
            self._evaluar(self._reloj())

    def _evaluar(self, t):
        rms = self.ventana.rms()
        with self._lock:
            paro = None
            if rms is not None:
                self._vib = rms
                paro = self.seguridad.evaluar_vibracion(rms)
            paro = paro or self.seguridad.vigilar(t)
            if paro:
                self._aplicar_paro(paro, t)

    def paso_temp(self):
        try:
            temp = self.hal.leer_temp()
        except ErrorHardware as e:
            self._avisar_fallo("ds18b20", e)
            return
        t = self._reloj()
        with self._lock:
            self._temp = temp
            self.seguridad.lectura_ok("ds18b20", t)
            paro = self.seguridad.evaluar_temperatura(temp)
            if paro:
                self._aplicar_paro(paro, t)

    def paso_publicar(self):
        t = self._reloj()
        with self._lock:
            paro = self.seguridad.vigilar(t)
            if paro:
                self._aplicar_paro(paro, t)
            vib, temp = self._vib, self._temp
        self.mqtt.publicar(topicos.LECTURAS,
                           {"ts": self._ts(), "vib_rms_g": _r3(vib), "temp_c": _r3(temp)})

    def _avisar_fallo(self, sensor, error):
        """Un aviso por segundo como máximo por sensor (a 100 Hz inundaría el log)."""
        t = self._reloj()
        if t - self._fallos_avisados.get(sensor, -1e9) >= 1.0:
            self._fallos_avisados[sensor] = t
            log.warning("%s sin lectura válida: %s", sensor, error)

    # ------------------------------------------------------------------ paro y reinicio
    def _hacer(self, accion, *args):
        """Ejecuta una salida; un fallo no impide intentar las demás."""
        try:
            accion(*args)
        except ErrorHardware as e:
            log.critical("no se pudo %s%s: %s", getattr(accion, "__name__", accion), args, e)

    def _aplicar_paro(self, paro, t_lectura, guardar=True):
        """Con `self._lock` tomado. Orden: detener, señalar, guardar, publicar."""
        self._hacer(self.hal.set_maquina, False)   # primero lo esencial
        t_parada = self._reloj()
        if t_lectura is not None:
            self.latencia_paro_ms = round((t_parada - t_lectura) * 1000, 2)
        self._senalizar(paro)
        if guardar:
            guardar_paro(self.cfg.paro_ruta, paro, self._ts())
        self._publicar_seguridad()
        log.error("PARO por %s: %.3f (umbral %.3f); máquina detenida en %s ms",
                  paro.sensor, paro.valor, paro.umbral, self.latencia_paro_ms)

    def _senalizar(self, paro):
        self._hacer(self.hal.set_luz, "roja")
        self._hacer(self.hal.set_zumbador, True)
        self._hacer(self.hal.mostrar_oled, ["PARO", paro.sensor, f"{paro.valor:.2f}>{paro.umbral:.2f}"])

    def parar_manual(self, origen):
        """Parar por orden (core o web): detiene sin retener. Reiniciar lo arranca de nuevo."""
        with self._lock:
            if self.seguridad.activo:
                return
            self.parada_manual = True
            self._hacer(self.hal.set_maquina, False)
            log.info("máquina detenida por orden de %s", origen)

    def reiniciar(self):
        """Libera el paro y arranca. El PIN ya lo validó la web (CU-06)."""
        with self._lock:
            habia = self.seguridad.reiniciar(self._reloj())
            borrar_paro(self.cfg.paro_ruta)
            self.ventana.limpiar()
            self.parada_manual = False
            self._hacer(self.hal.set_zumbador, False)
            self._hacer(self.hal.set_luz, "verde")
            self._hacer(self.hal.set_maquina, True)
            self._hacer(self.hal.mostrar_oled, ["OPERANDO"])
            self._publicar_seguridad()
            log.info("reinicio: máquina en marcha (había paro: %s)", habia)

    # ------------------------------------------------------------------ comandos MQTT
    def _on_maquina(self, topico, d):
        accion, origen = d.get("accion"), d.get("origen")
        if accion == "parar" and origen in ORIGENES_PARAR:
            self.parar_manual(origen)
        elif accion == "reiniciar" and origen == ORIGEN_REINICIAR:
            self.reiniciar()
        else:
            log.warning("orden de máquina ignorada: %s", d)

    def _on_senal(self, topico, d):
        with self._lock:
            if self.seguridad.activo:
                log.info("cmd/senal ignorado: paro retenido")
                return
            if "luz" in d:
                if d["luz"] is None or d["luz"] in topicos.LUCES:
                    self._hacer(self.hal.set_luz, d["luz"])
                else:
                    log.warning("luz inválida: %r", d["luz"])
            if isinstance(d.get("zumbador"), bool):
                self._hacer(self.hal.set_zumbador, d["zumbador"])
            if isinstance(d.get("oled"), list):
                self._hacer(self.hal.mostrar_oled, [str(x) for x in d["oled"]])

    def _on_recargar(self, topico, d):
        """CU-07: umbrales nuevos sin reiniciar. Si el archivo es inválido se conservan los actuales."""
        try:
            nueva = self._cargador()
        except ErrorConfig as e:
            log.error("recarga ignorada, configuración inválida: %s", e)
            return
        with self._lock:
            self.seguridad.actualizar(nueva.umbrales, nueva.sensores.tolerancia_fallo_s)
        log.info("umbrales recargados: vibración %.2f g, temperatura %.1f °C",
                 nueva.umbrales.vib_rms_g, nueva.umbrales.temp_c)

    def _on_inyectar(self, topico, d):
        if self.cfg.modo != "sim" or not hasattr(self.hal, "inyectar"):
            log.warning("sim/inyectar ignorado: no es modo sim")
            return
        vib, temp, dur = d.get("vib_g"), d.get("temp_c"), d.get("duracion_s", 5.0)
        valido = (all(x is None or _es_numero(x) for x in (vib, temp)) and _es_numero(dur)
                  and dur > 0 and (vib is None or vib >= 0))
        if not valido:
            log.warning("sim/inyectar inválido: %s", d)
            return
        self.hal.inyectar(vib_g=vib, temp_c=temp, duracion_s=dur)
        log.info("falla inyectada: vib=%s g, temp=%s °C, %s s", vib, temp, dur)

    # ------------------------------------------------------------------ publicación
    def _ts(self):
        return round(self._ahora(), 3)

    def _publicar_seguridad(self):
        self.mqtt.publicar(topicos.SEGURIDAD, self.seguridad.payload(self._ts()))

    def _publicar_salidas(self):
        s = self.hal.salidas()
        self.mqtt.publicar(topicos.SALIDAS, {"ts": self._ts(), "maquina": s.maquina, "luz": s.luz,
                                             "zumbador": s.zumbador, "oled": list(s.oled)})

    def _on_salida(self, nombre, valor):
        self._publicar_salidas()

    def _republicar(self):
        """Tras (re)conectar a MQTT, los estados retenidos se vuelven a publicar."""
        with self._lock:
            self._publicar_seguridad()
            self._publicar_salidas()
