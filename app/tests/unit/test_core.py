"""andon-core: transiciones de la máquina de estados, Tabla 9, invariantes y registro.

Sin hilos ni Ollama: el clasificador es un doble y `procesar` se llama directamente.
"""
import threading

import pytest

from andon.common import topicos
from andon.common.config import Config, ErrorConfig, OllamaCfg
from andon.core import ollama
from andon.core.registro import Registro
from andon.core.servicio import (ACCION_PARO_ACTIVO, ACCION_YA_DETENIDA, ATENCION, CALENTANDO,
                                 DETENIDA, PARO_SEGURIDAD, REPOSO, Core)

from .dobles_mqtt import BrokerFalso


class Clasificador:
    """Devuelve lo que se le programe; registra con qué se le llamó."""

    def __init__(self):
        self.resultado = ("operacion_normal", 0.97)
        self.error = None
        self.llamadas = []
        self.durante = None     # callback para simular eventos MQTT mientras «analiza»

    def __call__(self, texto, vib, temp, url=None, modelo=None, timeout_s=None):
        self.llamadas.append({"texto": texto, "vib": vib, "temp": temp, "url": url,
                              "modelo": modelo, "timeout_s": timeout_s})
        if self.durante:
            self.durante()
        if self.error:
            raise self.error
        cat, prob = self.resultado
        return ollama.Resultado(cat, prob, prob, {cat: prob}, 1)


class Entorno:
    def __init__(self, calentar=False, umbral=0.92, cargador=None):
        self.cfg = Config(db_ruta=":memory:", ollama=OllamaCfg(umbral_confianza=umbral,
                                                               calentar=calentar,
                                                               url="http://x", modelo="m",
                                                               timeout_s=7.0))
        self.broker = BrokerFalso()
        self.clasif = Clasificador()
        self.calentados = []
        self.t = 100.0
        self.core = Core(self.cfg, self.broker.cliente(), Registro(":memory:"),
                         clasificador=self.clasif,
                         calentador=lambda url, modelo: self.calentados.append((url, modelo)) or 1.0,
                         reloj=lambda: self.t, ahora=lambda: 1_700_000_000.0,
                         cargador=cargador or (lambda: self.cfg))
        self.core.preparar()
        self.web = self.broker.cliente()
        self.web.conectar()

    def lecturas(self, vib=0.3, temp=40.0):
        self.web.publicar(topicos.LECTURAS, {"ts": 1, "vib_rms_g": vib, "temp_c": temp})

    def seguridad(self, activo, sensor="vibracion"):
        self.web.publicar(topicos.SEGURIDAD, {"ts": 1, "activo": activo, "sensor": sensor})

    def salidas(self, luz, maquina):
        self.web.publicar(topicos.SALIDAS, {"ts": 1, "maquina": maquina, "luz": luz,
                                            "zumbador": False, "oled": []})

    def reporte(self, texto="ruido", id="r1"):
        item = {"id": id, "texto": texto, "ts_navegador": 1.0, "recibido": self.t}
        self.core.procesar(item)
        return self.broker.ultimo(topicos.EVENTO)

    def senales(self):
        return self.broker.de(topicos.CMD_SENAL)

    def ordenes(self):
        return self.broker.de(topicos.CMD_MAQUINA)

    def estado(self):
        return self.broker.ultimo(topicos.ESTADO)["estado"]


@pytest.fixture
def e():
    return Entorno()


# ---------------------------------------------------------------- Tabla 9 de extremo a extremo
@pytest.mark.parametrize("cat,luz,parar,area,estado", [
    ("operacion_normal", "verde", False, None, REPOSO),
    ("falla_mecanica", "roja", True, "mantenimiento", DETENIDA),
    ("falla_electrica", "roja", True, "mantenimiento", DETENIDA),
    ("problema_calidad", "amarilla", False, "calidad", ATENCION),
    ("material_faltante", "amarilla", False, "supervision", ATENCION),
])
def test_clasificacion_segura_aplica_la_tabla(e, cat, luz, parar, area, estado):
    e.clasif.resultado = (cat, 0.97)
    ev = e.reporte()
    assert ev["categoria"] == cat and ev["area"] == area
    assert e.senales()[-1]["luz"] == luz
    assert e.ordenes() == ([{"accion": "parar", "origen": "core"}] if parar else [])
    assert e.core.estado == estado == e.estado()


def test_zumbador_solo_con_la_parada(e):
    e.clasif.resultado = ("falla_mecanica", 0.97)
    e.reporte()
    assert e.senales()[-1]["zumbador"] is True


def test_la_parada_se_ordena_antes_que_las_senales(e):
    e.clasif.resultado = ("falla_electrica", 0.99)
    e.reporte()
    orden = [t for t, _ in e.broker.mensajes if t in (topicos.CMD_MAQUINA, topicos.CMD_SENAL)]
    assert orden == [topicos.CMD_SENAL, topicos.CMD_MAQUINA, topicos.CMD_SENAL]  # «analizando», parar, roja


def test_el_core_nunca_ordena_arrancar(e):
    for cat in ("operacion_normal", "falla_mecanica", "problema_calidad"):
        e.core.estado = REPOSO
        e.clasif.resultado = (cat, 0.99)
        e.reporte()
    assert all(o["accion"] == "parar" for o in e.ordenes())


# ---------------------------------------------------------------- baja confianza y fallos de Ollama
def test_probabilidad_bajo_el_umbral_es_revision_manual(e):
    e.clasif.resultado = ("falla_mecanica", 0.86)
    ev = e.reporte()
    assert (ev["accion"], ev["area"], ev["categoria"]) == ("revision_manual", "supervision",
                                                           "falla_mecanica")
    assert e.senales()[-1]["luz"] == "amarilla" and e.ordenes() == []
    assert e.core.estado == ATENCION


@pytest.mark.parametrize("exc", [ollama.ErrorTimeout("t"), ollama.ErrorConexion("c"),
                                 ollama.ErrorRespuesta("r")])
def test_ollama_falla_amarilla_sin_parar_y_sin_caer(e, exc):
    e.clasif.error = exc
    ev = e.reporte()
    assert ev["accion"] == "revision_manual" and ev["categoria"] is None and ev["prob"] is None
    assert e.senales()[-1]["luz"] == "amarilla" and e.ordenes() == []
    assert type(exc).__name__ in e.core.registro.ultimos(1)[0]["error"]
    e.clasif.error = None
    e.clasif.resultado = ("operacion_normal", 0.99)
    assert e.reporte()["accion"] == "ninguna"      # el servicio sigue atendiendo


# ---------------------------------------------------------------- «analizando» y lecturas
def test_analizando_pone_amarilla_antes_de_consultar(e):
    e.lecturas(vib=0.8, temp=51.5)
    vistos = []
    e.clasif.durante = lambda: vistos.append((e.core.estado, e.senales()[-1]["luz"]))
    e.reporte()
    assert vistos == [("analizando", "amarilla")]


def test_envia_las_ultimas_lecturas_y_la_configuracion_al_cliente(e):
    e.lecturas(vib=0.8, temp=51.5)
    e.reporte("hay ruido")
    ll = e.clasif.llamadas[-1]
    assert (ll["texto"], ll["vib"], ll["temp"]) == ("hay ruido", 0.8, 51.5)
    assert (ll["url"], ll["modelo"], ll["timeout_s"]) == ("http://x", "m", 7.0)
    assert e.broker.ultimo(topicos.EVENTO)["lecturas"] == {"vib_rms_g": 0.8, "temp_c": 51.5}


def test_sin_lecturas_se_consulta_con_none(e):
    e.reporte()
    assert e.clasif.llamadas[-1]["vib"] is None and e.clasif.llamadas[-1]["temp"] is None


def test_lecturas_invalidas_se_ignoran(e):
    e.web.publicar(topicos.LECTURAS, {"vib_rms_g": "mucho", "temp_c": float("inf")})
    e.reporte()
    assert e.clasif.llamadas[-1]["vib"] is None


# ---------------------------------------------------------------- paro de seguridad (CU-02/CU-06)
def test_paro_de_seguridad_cambia_el_estado_y_se_libera(e):
    e.seguridad(True)
    assert e.core.estado == PARO_SEGURIDAD == e.estado()
    e.seguridad(False)
    assert e.core.estado == REPOSO


def test_con_paro_activo_no_emite_ordenes_de_luz_ni_de_maquina(e):
    e.seguridad(True)
    e.clasif.resultado = ("operacion_normal", 0.99)
    ev = e.reporte()
    assert ev["accion"] == ACCION_PARO_ACTIVO and ev["categoria"] == "operacion_normal"
    assert e.senales() == [] and e.ordenes() == []
    assert e.core.estado == PARO_SEGURIDAD


def test_paro_que_llega_mientras_analiza_gana(e):
    e.clasif.resultado = ("operacion_normal", 0.99)
    e.clasif.durante = lambda: e.seguridad(True)
    ev = e.reporte()
    assert ev["accion"] == ACCION_PARO_ACTIVO
    assert e.core.estado == PARO_SEGURIDAD
    assert [s["luz"] for s in e.senales()] == ["amarilla"]     # solo el «analizando» previo


def test_el_paro_retenido_se_conoce_al_arrancar_el_core():
    e = Entorno()
    e.broker.publicar(topicos.SEGURIDAD, {"activo": True, "sensor": "temperatura"})
    nuevo = Core(e.cfg, e.broker.cliente(), Registro(":memory:"), clasificador=e.clasif)
    nuevo.preparar()
    assert nuevo.estado == PARO_SEGURIDAD


# ---------------------------------------------------------------- máquina detenida por el core
def test_detenida_no_se_libera_con_un_reporte_normal(e):
    e.clasif.resultado = ("falla_mecanica", 0.99)
    e.reporte()
    n_senales = len(e.senales())
    e.clasif.resultado = ("operacion_normal", 0.99)
    ev = e.reporte()
    assert ev["accion"] == ACCION_YA_DETENIDA
    assert len(e.senales()) == n_senales and e.core.estado == DETENIDA   # sigue en rojo


def test_reinicio_de_la_web_saca_de_detenida(e):
    e.clasif.resultado = ("falla_electrica", 0.99)
    e.reporte()
    e.salidas("roja", False)
    assert e.core.estado == DETENIDA
    e.salidas("verde", True)
    assert e.core.estado == REPOSO == e.estado()


def test_reinicio_limpia_la_atencion_amarilla(e):
    e.clasif.resultado = ("problema_calidad", 0.99)
    e.reporte()
    e.salidas("verde", True)
    assert e.core.estado == REPOSO


def test_un_reporte_normal_limpia_la_atencion(e):
    e.clasif.resultado = ("problema_calidad", 0.99)
    e.reporte()
    e.clasif.resultado = ("operacion_normal", 0.99)
    e.reporte()
    assert e.core.estado == REPOSO and e.senales()[-1]["luz"] == "verde"


# ---------------------------------------------------------------- evento, estado y registro
def test_evento_con_los_campos_del_contrato(e):
    e.lecturas(0.5, 41.0)
    e.t = 100.0
    e.clasif.resultado = ("problema_calidad", 0.95)
    ev = e.reporte("piezas rayadas")
    assert set(ev) == {"id", "ts", "lecturas", "texto", "categoria", "prob", "accion", "area",
                       "latencia_ms", "error"}
    assert ev["texto"] == "piezas rayadas" and ev["prob"] == 0.95 and ev["accion"] == "avisar"
    assert ev["id"] == "r1" and ev["error"] is None


@pytest.mark.parametrize("exc,codigo", [(ollama.ErrorTimeout("t"), "timeout"),
                                        (ollama.ErrorConexion("c"), "conexion"),
                                        (ollama.ErrorRespuesta("r"), "respuesta")])
def test_evento_informa_el_codigo_del_fallo_de_ollama(e, exc, codigo):
    e.clasif.error = exc
    assert e.reporte(id="x9")["error"] == codigo
    assert e.broker.ultimo(topicos.EVENTO)["id"] == "x9"
    assert type(exc).__name__ in e.core.registro.ultimos(1)[0]["error"]   # el detalle queda en el registro


def test_latencia_incluye_la_espera_en_la_cola(e):
    item = {"id": "r", "texto": "ruido", "ts_navegador": None, "recibido": 100.0}
    e.clasif.durante = lambda: setattr(e, "t", 117.0)
    e.core.procesar(item)
    assert e.broker.ultimo(topicos.EVENTO)["latencia_ms"] == 17000


def test_estado_retenido_incluye_el_ultimo_evento(e):
    ev = e.reporte()
    assert e.broker.retenidos[topicos.ESTADO] == {"estado": REPOSO, "ultimo_evento": ev}
    assert topicos.EVENTO not in e.broker.retenidos       # el evento no se retiene


def test_cada_reporte_queda_registrado_con_su_id(e):
    e.lecturas(0.7, 55.0)
    e.clasif.resultado = ("falla_mecanica", 0.97)
    e.reporte("ruido", id="abc")
    (f,) = e.core.registro.ultimos()
    assert (f["reporte_id"], f["texto"], f["categoria"], f["accion"], f["vib_rms_g"],
            f["temp_c"], f["error"]) == ("abc", "ruido", "falla_mecanica", "parar_maquina",
                                         0.7, 55.0, None)


# ---------------------------------------------------------------- reportes entrantes
def test_reporte_valido_se_encola(e):
    e.web.publicar(topicos.REPORTE, {"id": 7, "texto": "  hay ruido ", "ts_navegador": 5})
    item = e.core._cola.get_nowait()
    assert (item["id"], item["texto"], item["ts_navegador"]) == ("7", "hay ruido", 5)


@pytest.mark.parametrize("cuerpo", [{}, {"texto": ""}, {"texto": "   "}, {"texto": 5},
                                    {"texto": "x" * 281}])
def test_reporte_invalido_se_ignora(e, cuerpo):
    e.web.publicar(topicos.REPORTE, cuerpo)
    assert e.core._cola.empty()


def test_reporte_de_280_caracteres_es_valido(e):
    e.web.publicar(topicos.REPORTE, {"texto": "x" * 280})
    assert not e.core._cola.empty()


def test_cola_llena_descarta_y_deja_constancia(e):
    for i in range(8):
        e.web.publicar(topicos.REPORTE, {"id": i, "texto": "ruido"})
    e.web.publicar(topicos.REPORTE, {"id": 99, "texto": "ruido"})
    assert e.core._cola.qsize() == 8
    assert e.broker.ultimo(topicos.EVENTO)["accion"] == "descartado"
    assert e.broker.ultimo(topicos.EVENTO)["error"] == "cola_llena" and e.broker.ultimo(topicos.EVENTO)["id"] == "99"
    assert e.core.registro.ultimos(1)[0]["reporte_id"] == "99"


# ---------------------------------------------------------------- recarga (D7)
def test_recarga_cambia_el_umbral_sin_reiniciar():
    nueva = Config(db_ruta=":memory:", ollama=OllamaCfg(umbral_confianza=0.5, calentar=False))
    e = Entorno(cargador=lambda: nueva)
    e.clasif.resultado = ("falla_mecanica", 0.80)
    assert e.reporte()["accion"] == "revision_manual"
    e.web.publicar(topicos.CMD_RECARGAR, {})
    assert e.reporte()["accion"] == "parar_maquina"


def test_recarga_invalida_conserva_la_configuracion():
    def malo():
        raise ErrorConfig("umbral_confianza inválido")
    e = Entorno(cargador=malo)
    e.web.publicar(topicos.CMD_RECARGAR, {})
    assert e.core.cfg.ollama.umbral_confianza == 0.92


# ---------------------------------------------------------------- calentamiento y arranque (D4)
def test_calienta_el_modelo_al_arrancar_sin_bloquear():
    e = Entorno(calentar=True)
    e.core.iniciar()
    try:
        e.core._hilos[-1].join(timeout=3)
        assert e.calentados == [("http://x", "m")]
        assert e.core.estado == REPOSO
    finally:
        e.core.detener()


def test_estado_calentando_mientras_carga_el_modelo():
    e = Entorno(calentar=True)
    liberar, visto = threading.Event(), []
    e.core._calentar = lambda url, modelo: (visto.append(e.core.estado), liberar.wait(3))[1]
    e.core.iniciar()
    try:
        for _ in range(100):
            if visto:
                break
            threading.Event().wait(0.01)
        assert visto == [CALENTANDO] and e.estado() == CALENTANDO
        liberar.set()
        e.core._hilos[-1].join(timeout=3)
        assert e.core.estado == REPOSO
    finally:
        liberar.set()
        e.core.detener()


def test_sin_calentar_publica_reposo_al_iniciar():
    e = Entorno(calentar=False)
    e.core.iniciar()
    try:
        assert e.estado() == REPOSO and e.calentados == []
    finally:
        e.core.detener()


def test_un_fallo_inesperado_no_tumba_el_trabajador():
    e = Entorno()
    e.clasif.error = RuntimeError("bug")
    e.core.iniciar()
    try:
        e.web.publicar(topicos.REPORTE, {"id": 1, "texto": "ruido"})
        for _ in range(200):
            if e.core.estado == ATENCION:
                break
            threading.Event().wait(0.01)
        assert e.core.estado == ATENCION
        e.clasif.error = None
        e.web.publicar(topicos.REPORTE, {"id": 2, "texto": "ruido"})
        for _ in range(200):
            if e.core.registro.contar():
                break
            threading.Event().wait(0.01)
        assert e.core.registro.contar() == 1
    finally:
        e.core.detener()
