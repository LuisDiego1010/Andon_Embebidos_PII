"""andon-core: máquina de estados, clasificación con Ollama, registro y publicación.

No toca hardware: todo llega y sale por MQTT. Un hilo trabajador atiende los reportes de a
uno (la consulta tarda ~17 s en la RPi 4, D4), así que `on_reporte` solo encola y el resto de
mensajes (seguridad, lecturas, salidas) se siguen procesando mientras se analiza.

Estados (`estado`, retenido):
  calentando     cargando el modelo al arrancar (D4); los reportes igual se atienden
  reposo         operación normal
  analizando     consulta en curso; luz amarilla («Analizando…»)
  atencion       el último reporte dejó luz amarilla (calidad, material o revisión manual)
  detenida       el core detuvo la máquina por una falla; sigue hasta `reiniciar` de la web
  paro_seguridad paro por umbral o falla de sensor decidido por andon-sensores (CU-02/CU-06)

Invariantes (CLAUDE.md): el core nunca arranca la máquina (solo `parar`); con un paro retenido
no emite órdenes de luz ni de máquina (sensores las ignoraría de todos modos); cualquier fallo
de Ollama o probabilidad bajo el umbral → amarilla y revisión manual, sin bloquear el servicio.
"""

import logging
import math
import queue
import threading
import time

from andon.common import topicos
from andon.common.config import ErrorConfig, cargar
from andon.core import ollama
from andon.core.decision import decidir
from andon.core.registro import Registro

log = logging.getLogger(__name__)

CALENTANDO, REPOSO, ANALIZANDO, ATENCION, DETENIDA, PARO_SEGURIDAD = (
    "calentando", "reposo", "analizando", "atencion", "detenida", "paro_seguridad")
MAX_TEXTO = 280
COLA_MAX = 8
ACCION_PARO_ACTIVO = "paro_activo"       # había un paro retenido: se clasificó pero no se actuó
ACCION_YA_DETENIDA = "maquina_detenida"  # ya estaba detenida por una falla: luz roja intacta
ACCION_DESCARTADO = "descartado"         # cola llena
CODIGOS_ERROR = ((ollama.ErrorTimeout, "timeout"), (ollama.ErrorConexion, "conexion"),
                 (ollama.ErrorRespuesta, "respuesta"))
OLED = {
    "operacion_normal": ["OPERANDO", "Todo normal"],
    "falla_mecanica": ["FALLA MECANICA", "Mantenimiento"],
    "falla_electrica": ["FALLA ELECTRICA", "Mantenimiento"],
    "problema_calidad": ["CALIDAD", "Aviso a calidad"],
    "material_faltante": ["FALTA MATERIAL", "Aviso supervision"],
}
OLED_REVISION = ["REVISION MANUAL", "Supervision"]
OLED_ANALIZANDO = ["ANALIZANDO", "Espere..."]


def _probabilidades(res):
    """Probabilidades de las 5 categorías, para mostrar que el modelo sopesa opciones (D16)."""
    if res is None or not isinstance(res.probabilidades, dict):
        return None
    return {c: round(float(p), 4) for c, p in res.probabilidades.items()
            if c in ollama.CATEGORIAS and _numero(p)}


def _numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


class Core:
    def __init__(self, cfg, mqtt, registro, clasificador=ollama.clasificar,
                 calentador=ollama.calentar, reloj=time.monotonic, ahora=time.time,
                 cargador=cargar):
        self.cfg, self.mqtt, self.registro = cfg, mqtt, registro
        self._clasificar, self._calentar = clasificador, calentador
        self._reloj, self._ahora, self._cargador = reloj, ahora, cargador
        self._lock = threading.RLock()
        self._cola = queue.Queue(maxsize=COLA_MAX)
        self._fin = threading.Event()
        self._hilos = []
        self.estado = REPOSO
        self.ultimo_evento = None
        self._vib = None
        self._temp = None
        self._maquina_en_marcha = None
        self._paro_activo = False
        self._preparado = False

    # ------------------------------------------------------------------ ciclo de vida
    def preparar(self):
        if self._preparado:     # `iniciar` también llama a preparar
            return
        self._preparado = True
        m = self.mqtt
        m.suscribir(topicos.LECTURAS, self._on_lecturas)
        m.suscribir(topicos.SEGURIDAD, self._on_seguridad)
        m.suscribir(topicos.SALIDAS, self._on_salidas)
        m.suscribir(topicos.REPORTE, self._on_reporte)
        m.suscribir(topicos.CMD_RECARGAR, self._on_recargar)
        m.al_conectar(self._publicar_estado)
        m.conectar()

    def iniciar(self):
        self.preparar()
        self._fin.clear()
        t = threading.Thread(target=self._trabajador, name="core-reportes", daemon=True)
        t.start()
        self._hilos.append(t)
        if self.cfg.ollama.calentar:
            self._cambiar(CALENTANDO)
            c = threading.Thread(target=self._calentamiento, name="core-calentar", daemon=True)
            c.start()
            self._hilos.append(c)
        else:
            self._publicar_estado()
        log.info("andon-core en marcha (modelo %s en %s)", self.cfg.ollama.modelo,
                 self.cfg.ollama.url)

    def solicitar_fin(self):
        self._fin.set()

    def esperar(self):
        self._fin.wait()

    def detener(self):
        self._fin.set()
        self._cola.put(None)   # despierta al trabajador
        for h in self._hilos:
            h.join(timeout=3)
        self.mqtt.desconectar()
        self.registro.cerrar()
        log.info("andon-core detenido")

    def _calentamiento(self):
        o = self.cfg.ollama
        segundos = self._calentar(o.url, o.modelo)
        if segundos is None:
            log.warning("el modelo no respondió al calentar; el primer reporte pagará la carga")
        with self._lock:
            if self.estado == CALENTANDO:
                self._cambiar(PARO_SEGURIDAD if self._paro_activo else REPOSO)

    # ------------------------------------------------------------------ entradas MQTT
    def _on_lecturas(self, topico, d):
        v, t = d.get("vib_rms_g"), d.get("temp_c")
        with self._lock:
            self._vib = v if _numero(v) else None
            self._temp = t if _numero(t) else None

    def _on_seguridad(self, topico, d):
        activo = d.get("activo")
        if not isinstance(activo, bool):
            return
        with self._lock:
            self._paro_activo = activo
            if activo and self.estado != PARO_SEGURIDAD:
                log.warning("paro de seguridad: %s", d.get("sensor"))
                self._cambiar(PARO_SEGURIDAD)
            elif not activo and self.estado == PARO_SEGURIDAD:
                self._cambiar(REPOSO)

    def _on_salidas(self, topico, d):
        """Una web que reinicia deja luz verde y la máquina en marcha: se sale de «detenida»."""
        with self._lock:
            self._maquina_en_marcha = d.get("maquina") if isinstance(d.get("maquina"), bool) else None
            if (self.estado in (DETENIDA, ATENCION) and d.get("luz") == "verde"
                    and self._maquina_en_marcha):
                self._cambiar(REPOSO)

    def _on_recargar(self, topico, d):
        """D7: configuración nueva sin reiniciar. Si el archivo es inválido se conserva la actual."""
        try:
            nueva = self._cargador()
        except ErrorConfig as e:
            log.error("recarga ignorada, configuración inválida: %s", e)
            return
        with self._lock:
            cambio_modelo = (nueva.ollama.modelo != self.cfg.ollama.modelo
                             or nueva.ollama.url != self.cfg.ollama.url)
            self.cfg = nueva
        log.info("configuración recargada: umbral de confianza %.2f, modelo %s",
                 nueva.ollama.umbral_confianza, nueva.ollama.modelo)
        if cambio_modelo and nueva.ollama.calentar:
            threading.Thread(target=self._calentamiento, name="core-calentar", daemon=True).start()

    def _on_reporte(self, topico, d):
        texto, rid = d.get("texto"), d.get("id")
        if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_TEXTO:
            log.warning("reporte ignorado: texto inválido (%r)", str(texto)[:40])
            return
        item = {"id": None if rid is None else str(rid), "texto": texto.strip(),
                "ts_navegador": d.get("ts_navegador") if _numero(d.get("ts_navegador")) else None,
                "recibido": self._reloj()}
        try:
            self._cola.put_nowait(item)
        except queue.Full:
            log.error("cola de reportes llena: reporte descartado")
            with self._lock:
                self._cerrar_evento(item, None, None, None, ACCION_DESCARTADO,
                                    ("cola_llena", "cola de reportes llena"), self._lecturas())

    # ------------------------------------------------------------------ trabajo
    def _trabajador(self):
        while not self._fin.is_set():
            item = self._cola.get()
            if item is None:
                return
            try:
                self.procesar(item)
            except Exception:   # un reporte malo no tumba el servicio
                log.exception("fallo inesperado al procesar un reporte")
                with self._lock:
                    if self.estado == ANALIZANDO:
                        self._cambiar(PARO_SEGURIDAD if self._paro_activo else ATENCION)

    def procesar(self, item):
        """Clasifica un reporte y aplica la decisión. Público para probarlo sin hilos."""
        with self._lock:
            lecturas = self._lecturas()
            o = self.cfg.ollama
            if not self._bloqueado():
                self._cambiar(ANALIZANDO)
                self._senal("amarilla", False, OLED_ANALIZANDO)
        error = res = None
        try:
            res = self._clasificar(item["texto"], lecturas["vib_rms_g"], lecturas["temp_c"],
                                   url=o.url, modelo=o.modelo, timeout_s=o.timeout_s)
        except ollama.ErrorOllama as e:
            codigo = next((c for tipo, c in CODIGOS_ERROR if isinstance(e, tipo)), "ollama")
            error = (codigo, f"{type(e).__name__}: {e}")
            log.warning("Ollama falló, revisión manual: %s", error[1])
        with self._lock:
            umbral = self.cfg.ollama.umbral_confianza
            cat = res.categoria if res else None
            prob = res.prob if res else None
            d = decidir(cat, prob, umbral)
            accion, area = d.accion, d.area
            if self._paro_activo:
                accion = ACCION_PARO_ACTIVO
            elif self.estado == DETENIDA:
                accion = ACCION_YA_DETENIDA
            else:
                self._aplicar(d, cat)
            modelo = {"umbral": umbral, "probs": _probabilidades(res),
                      "entrada": ollama.construir_estado(item["texto"], lecturas["vib_rms_g"],
                                                         lecturas["temp_c"])}
            self._cerrar_evento(item, cat, prob, area, accion, error, lecturas, modelo)

    def _bloqueado(self):
        """Con paro retenido o la máquina detenida por el core, la luz roja no se toca:
        solo `reiniciar` desde la web la libera (CU-06)."""
        return self._paro_activo or self.estado == DETENIDA

    def _aplicar(self, d, categoria):
        if d.parar:
            # Primero la máquina, después las señales: lo urgente va antes que lo informativo.
            self.mqtt.publicar(topicos.CMD_MAQUINA, {"accion": "parar", "origen": "core"})
            self._senal(d.luz, True, OLED.get(categoria))
            self._cambiar(DETENIDA)
        else:
            self._senal(d.luz, False,
                        OLED.get(categoria) if d.accion != "revision_manual" else OLED_REVISION)
            self._cambiar(REPOSO if d.luz == "verde" else ATENCION)

    def _senal(self, luz, zumbador, oled):
        self.mqtt.publicar(topicos.CMD_SENAL, {"luz": luz, "zumbador": zumbador, "oled": oled or []})

    def _lecturas(self):
        return {"vib_rms_g": self._vib, "temp_c": self._temp}

    def _cerrar_evento(self, item, cat, prob, area, accion, error, lecturas, modelo=None):
        """`error` es None o (código corto para la web, detalle para el registro).
        `modelo`: umbral, probabilidades de las 5 categorías y texto enviado (D16)."""
        latencia = round((self._reloj() - item["recibido"]) * 1000)
        codigo, detalle = error or (None, None)
        # D9: la placa no tiene hora fiable; se usa la del navegador más lo que tardó el análisis.
        navegador = item.get("ts_navegador")
        ts = self._ahora() if navegador is None else navegador + latencia / 1000
        evento = {"id": item["id"], "ts": ts, "lecturas": lecturas,
                  "texto": item["texto"], "categoria": cat, "prob": prob, "accion": accion,
                  "area": area, "latencia_ms": latencia, "error": codigo,
                  "umbral": None, "probs": None, "entrada": None, **(modelo or {})}
        self.registro.guardar({
            "reporte_id": item["id"], "ts": evento["ts"], "vib_rms_g": lecturas["vib_rms_g"],
            "temp_c": lecturas["temp_c"], "texto": item["texto"], "categoria": cat, "prob": prob,
            "accion": accion, "area": area, "latencia_ms": latencia, "error": detalle})
        self.ultimo_evento = evento
        self.mqtt.publicar(topicos.EVENTO, evento)
        self._publicar_estado()
        log.info("reporte %s → %s (%.2f) · %s · %d ms", item["id"], cat,
                 prob if prob is not None else float("nan"), accion, latencia)

    # ------------------------------------------------------------------ estado
    def _cambiar(self, nuevo):
        if nuevo != self.estado:
            log.info("estado: %s → %s", self.estado, nuevo)
            self.estado = nuevo
        self._publicar_estado()

    def _publicar_estado(self):
        self.mqtt.publicar(topicos.ESTADO, {"estado": self.estado,
                                            "ultimo_evento": self.ultimo_evento})
