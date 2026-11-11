"""andon-web: puente entre el navegador y MQTT. No toca hardware ni el modelo.

Guarda en memoria lo último publicado por sensores y core para servirlo al navegador, publica
los reportes del operario y, con PIN (D8), `cmd/maquina reiniciar` y `cmd/recargar`.
"""

import hmac
import logging
import math
import os
import re
import tempfile
import threading
import time
import uuid
from collections import deque

from andon.common import topicos
from andon.common.config import RUTA_POR_DEFECTO, ErrorConfig, cargar
from andon.hal.sim import AJUSTES_INICIALES, validar_ajustes

log = logging.getLogger(__name__)

MAX_TEXTO = 280
MAX_EVENTOS = 20
MAX_FALLOS_PIN = 5
BLOQUEO_PIN_S = 30.0
PIN_OK, PIN_MAL, PIN_BLOQUEADO = "ok", "mal", "bloqueado"

# campo del formulario → (sección, clave, máximo, nombre para el usuario). Los máximos evitan
# que un error de dedo deje el lazo de seguridad sin efecto: el MPU-6050 se configura a ±4 g
# (hal/rpi.py) y el DS18B20 llega a 125 °C; un umbral por encima de eso nunca dispararía el paro.
UMBRALES = {
    "vib_rms_g": ("umbrales", "vib_rms_g", 4.0, "Vibración RMS máxima"),
    "temp_c": ("umbrales", "temp_c", 125.0, "Temperatura máxima"),
    "umbral_confianza": ("ollama", "umbral_confianza", 1.0, "Confianza mínima del modelo"),
}


def actualizar_conf(ruta, valores):
    """Cambia claves de un INI sin perder sus comentarios. `valores`: {(sección, clave): texto}.

    Escribe en un temporal, lo valida con `cargar` y solo entonces reemplaza el archivo: una
    edición inválida nunca llega a los servicios. Lanza ErrorConfig u OSError.
    """
    with open(ruta, encoding="utf-8") as f:
        lineas = f.readlines()
    pendientes, seccion = dict(valores), None
    for i, linea in enumerate(lineas):
        cabecera = re.match(r"\s*\[([^\]]+)\]", linea)
        if cabecera:
            seccion = cabecera.group(1).strip()
            continue
        clave = re.match(r"\s*(\w+)\s*=", linea)
        if clave and (seccion, clave.group(1)) in pendientes:
            lineas[i] = f"{clave.group(1)} = {pendientes.pop((seccion, clave.group(1)))}\n"
    if pendientes:
        raise ErrorConfig(f"claves ausentes en {ruta}: {sorted(pendientes)}")

    fd, temporal = tempfile.mkstemp(dir=os.path.dirname(ruta) or ".", prefix=".andon.conf.")
    try:
        os.fchmod(fd, os.stat(ruta).st_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(lineas)
        cargar(ruta=temporal, entorno={})
        os.replace(temporal, ruta)
    except BaseException:
        os.unlink(temporal)
        raise


class ServicioWeb:
    def __init__(self, cfg, mqtt, cargador=cargar, reloj=time.monotonic, ruta_conf=None):
        self.cfg, self.mqtt = cfg, mqtt
        self._cargador, self._reloj = cargador, reloj
        self._ruta_conf = ruta_conf or os.environ.get("ANDON_CONF", RUTA_POR_DEFECTO)
        self._lock = threading.Lock()
        self._lecturas = self._seguridad = self._salidas = self._estado = None
        self._lecturas_t = None
        self._eventos = deque(maxlen=MAX_EVENTOS)
        self._fallos_pin = 0
        self._bloqueado_hasta = 0.0
        self._ajustes = dict(AJUSTES_INICIALES)

    @property
    def modo_sim(self):
        return self.cfg.modo == "sim"

    def preparar(self):
        m = self.mqtt
        m.suscribir(topicos.LECTURAS, self._on_lecturas)
        m.suscribir(topicos.SEGURIDAD, lambda t, d: self._guardar("_seguridad", d))
        m.suscribir(topicos.SALIDAS, lambda t, d: self._guardar("_salidas", d))
        m.suscribir(topicos.ESTADO, lambda t, d: self._guardar("_estado", d))
        m.suscribir(topicos.EVENTO, self._on_evento)
        m.suscribir(topicos.CMD_RECARGAR, self._on_recargar)
        if self.modo_sim:
            m.suscribir(topicos.SIM_AJUSTAR, self._on_ajustar)
        m.conectar()

    # ------------------------------------------------------------------ entradas MQTT
    def _guardar(self, atributo, datos):
        with self._lock:
            setattr(self, atributo, datos)

    def _on_ajustar(self, topico, d):
        with self._lock:
            self._ajustes = {**AJUSTES_INICIALES, **d}

    def _on_lecturas(self, topico, d):
        with self._lock:
            self._lecturas, self._lecturas_t = d, self._reloj()

    def _on_evento(self, topico, d):
        with self._lock:
            self._eventos.appendleft(d)

    def _on_recargar(self, topico, d):
        """D7: la web relee PIN y umbrales. Un archivo inválido deja la configuración vigente."""
        try:
            nueva = self._cargador()
        except ErrorConfig as e:
            log.error("recarga ignorada, configuración inválida: %s", e)
            return
        with self._lock:
            self.cfg = nueva

    # ------------------------------------------------------------------ consultas
    def instantanea(self):
        with self._lock:
            edad = None if self._lecturas_t is None else self._reloj() - self._lecturas_t
            c = self.cfg
            return {"conectado": bool(self.mqtt.conectado), "estado": self._estado,
                    "seguridad": self._seguridad, "salidas": self._salidas,
                    "lecturas": self._lecturas, "lecturas_edad_s": edad,
                    "eventos": list(self._eventos),
                    "sim": dict(self._ajustes) if self.modo_sim else None,
                    "umbrales": {"vib_rms_g": c.umbrales.vib_rms_g, "temp_c": c.umbrales.temp_c,
                                 "umbral_confianza": c.ollama.umbral_confianza}}

    def evento(self, reporte_id):
        """Evento de un reporte. Si la web se reinició o perdió el mensaje mientras el core
        analizaba, lo recupera de `estado.ultimo_evento` (retenido)."""
        with self._lock:
            evento = next((e for e in self._eventos if e.get("id") == reporte_id), None)
            if evento is None and isinstance(self._estado, dict):
                ultimo = self._estado.get("ultimo_evento")
                if isinstance(ultimo, dict) and ultimo.get("id") == reporte_id:
                    evento = ultimo
            return evento

    # ------------------------------------------------------------------ acciones
    def enviar_reporte(self, texto, ts_navegador):
        """Publica el reporte. Devuelve su id, o None si el broker no lo aceptó."""
        rid = uuid.uuid4().hex[:8]
        ok = self.mqtt.publicar(topicos.REPORTE, {"id": rid, "texto": texto,
                                                  "ts_navegador": ts_navegador})
        return rid if ok else None

    def verificar_pin(self, pin):
        with self._lock:
            ahora = self._reloj()
            if ahora < self._bloqueado_hasta:
                return PIN_BLOQUEADO
            correcto = isinstance(pin, str) and hmac.compare_digest(
                pin.encode("utf-8"), self.cfg.web.pin.encode("utf-8"))
            if correcto:
                self._fallos_pin = 0
                return PIN_OK
            self._fallos_pin += 1
            if self._fallos_pin >= MAX_FALLOS_PIN:
                self._fallos_pin = 0
                self._bloqueado_hasta = ahora + BLOQUEO_PIN_S
                log.warning("PIN incorrecto %d veces: bloqueado %.0f s", MAX_FALLOS_PIN, BLOQUEO_PIN_S)
            return PIN_MAL

    def reiniciar_maquina(self):
        """CU-06. Solo se llama tras validar el PIN."""
        log.info("reinicio de la máquina autorizado desde la web")
        return self.mqtt.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})

    def ajustar_simulador(self, campos):
        """Publica los controles completos, retenidos: un sensores reiniciado los recupera.
        Lanza ValueError si un valor no es válido; devuelve False si el broker no lo aceptó."""
        limpios = validar_ajustes(campos)
        with self._lock:
            self._ajustes = {**self._ajustes, **limpios}
            completos = dict(self._ajustes)
        return self.mqtt.publicar(topicos.SIM_AJUSTAR, completos, retener=True)

    def guardar_umbrales(self, valores):
        """CU-07. Valida, escribe el archivo y avisa a los servicios. Lanza ErrorConfig u OSError."""
        cambios = {}
        for campo, texto in valores.items():
            if campo not in UMBRALES:
                raise ErrorConfig(f"campo desconocido: {campo}")
            seccion, clave, maximo, nombre = UMBRALES[campo]
            try:
                numero = float(texto)
            except (TypeError, ValueError):
                raise ErrorConfig(f"{nombre}: no es un número.") from None
            if not math.isfinite(numero) or not 0 < numero <= maximo:
                raise ErrorConfig(f"{nombre}: debe ser mayor que 0 y como máximo {maximo:g}.")
            cambios[seccion, clave] = repr(numero)
        if not cambios:
            raise ErrorConfig("no hay valores que guardar")
        actualizar_conf(self._ruta_conf, cambios)
        log.info("umbrales actualizados desde la web: %s", valores)
        return self.mqtt.publicar(topicos.CMD_RECARGAR, {"origen": "web"})
