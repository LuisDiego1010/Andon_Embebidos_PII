"""CU-03, CU-04, CU-05 y CU-06 con los dos servicios reales (sensores en sim + core), un Mosquitto
real y tools/fake_ollama.py. Se omite sin broker. Deje detenido el servicio `sensores` de compose."""
import importlib.util
import pathlib

import pytest

from andon.common import topicos
from andon.common.config import Config, OllamaCfg
from andon.core.registro import Registro
from andon.core.servicio import Core
from andon.hal.sim import HalSim
from andon.sensores.servicio import Sensores

from .test_mqtt_integracion import HOST, PUERTO, _requiere_broker, cliente, esperar, limpiar_retenidos  # noqa: F401

spec = importlib.util.spec_from_file_location(
    "fake_ollama", pathlib.Path(__file__).resolve().parents[2] / "tools" / "fake_ollama.py")
fake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fake)

pytestmark = pytest.mark.integracion


class Sistema:
    def __init__(self, tmp_path, modo_ollama="ok"):
        limpiar_retenidos(topicos.SEGURIDAD, topicos.ESTADO, topicos.SALIDAS)
        self.ollama = fake.ServidorFalso(modo=modo_ollama).iniciar()
        self.cfg = Config(modo="sim", db_ruta=":memory:", paro_ruta=str(tmp_path / "paro.json"),
                          mqtt=Config().mqtt.__class__(HOST, PUERTO),
                          ollama=OllamaCfg(url=self.ollama.url, calentar=False, timeout_s=1.0))
        self.sensores = Sensores(self.cfg, HalSim(), cliente("sensores"))
        self.core = Core(self.cfg, cliente("core"), Registro(":memory:"))
        self.web = cliente("web")
        self.eventos, self.estados, self.salidas = [], [], []
        self.web.suscribir(topicos.EVENTO, lambda t, d: self.eventos.append(d))
        self.web.suscribir(topicos.ESTADO, lambda t, d: self.estados.append(d["estado"]))
        self.web.suscribir(topicos.SALIDAS, lambda t, d: self.salidas.append(d))
        self.web.conectar()
        assert self.web.esperar_conexion(5)
        self.sensores.iniciar()
        self.core.iniciar()
        assert esperar(lambda: self.salidas and "reposo" in self.estados, 5), "no arrancó"

    def reportar(self, texto, id="r"):
        n = len(self.eventos)
        self.web.publicar(topicos.REPORTE, {"id": id, "texto": texto, "ts_navegador": 1.0})
        assert esperar(lambda: len(self.eventos) > n, 5), "sin evento"
        return self.eventos[-1]

    def ultima(self):
        return self.salidas[-1]

    def cerrar(self):
        self.core.detener()
        self.sensores.detener()
        self.web.desconectar()
        self.ollama.detener()


@pytest.fixture
def sis(tmp_path):
    s = Sistema(tmp_path)
    yield s
    s.cerrar()


def test_cu03_falla_que_los_sensores_no_ven(sis):
    ev = sis.reportar("Salen chispas del cable y huele a quemado")
    assert (ev["categoria"], ev["accion"], ev["area"]) == ("falla_electrica", "parar_maquina",
                                                           "mantenimiento")
    assert esperar(lambda: sis.ultima()["maquina"] is False, 3)
    assert sis.ultima()["luz"] == "roja" and sis.ultima()["zumbador"] is True
    assert not sis.sensores.seguridad.activo        # no fue un paro por umbral
    assert sis.core.estado == "detenida"


def test_cu04_reporte_de_calidad(sis):
    ev = sis.reportar("Las piezas salen rayadas y fuera de especificación")
    assert (ev["categoria"], ev["accion"], ev["area"]) == ("problema_calidad", "avisar", "calidad")
    assert esperar(lambda: sis.ultima()["luz"] == "amarilla", 3)
    assert sis.ultima()["maquina"] is True


def test_cu05_reporte_ambiguo_va_a_revision_manual(sis):
    ev = sis.reportar("Algo ambiguo pasa con la máquina")
    assert ev["accion"] == "revision_manual" and ev["prob"] < 0.92
    assert esperar(lambda: sis.ultima()["luz"] == "amarilla", 3)
    assert sis.ultima()["maquina"] is True


def test_ollama_caido_es_amarillo_y_el_paro_de_seguridad_sigue_funcionando(sis):
    sis.ollama.modo = "colgado"
    ev = sis.reportar("hay ruido", id="lento")          # timeout de 1 s
    assert ev["accion"] == "revision_manual" and ev["categoria"] is None
    sis.sensores.hal.inyectar(vib_g=2.0, duracion_s=5)
    assert esperar(lambda: sis.sensores.seguridad.activo, 3)
    assert esperar(lambda: sis.core.estado == "paro_seguridad", 3)


def test_cu06_reinicio_desde_la_web_libera_la_detencion(sis):
    sis.reportar("chispas en el cable")
    assert esperar(lambda: sis.core.estado == "detenida", 3)
    sis.web.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    assert esperar(lambda: sis.core.estado == "reposo", 3)
    assert esperar(lambda: sis.ultima()["maquina"] is True and sis.ultima()["luz"] == "verde", 3)


def test_un_reinicio_del_core_no_libera_la_detencion(sis):
    sis.reportar("chispas en el cable")
    sis.web.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "core"})
    assert esperar(lambda: False, 0.5) is None
    assert sis.ultima()["maquina"] is False and sis.core.estado == "detenida"
