"""andon-web: API, PIN (D8), umbrales (CU-07) y caché de MQTT, con broker en memoria."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("flask")

from andon.common import topicos  # noqa: E402
from andon.common.config import Config, cargar  # noqa: E402
from andon.web.app import crear_app  # noqa: E402
from andon.web.servicio import BLOQUEO_PIN_S, MAX_FALLOS_PIN, ServicioWeb  # noqa: E402
from tests.unit.dobles_mqtt import BrokerFalso  # noqa: E402

CONF = Path(__file__).resolve().parents[2] / "config" / "andon.conf"


class Reloj:
    t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def entorno(tmp_path):
    ruta = tmp_path / "andon.conf"
    shutil.copy(CONF, ruta)
    broker, reloj = BrokerFalso(), Reloj()
    cfg = cargar(ruta=str(ruta), entorno={})
    servicio = ServicioWeb(cfg, broker.cliente(), reloj=reloj, ruta_conf=str(ruta),
                           cargador=lambda: cargar(ruta=str(ruta), entorno={}))
    servicio.preparar()
    return broker, servicio, crear_app(servicio).test_client(), ruta, reloj


def test_paginas_se_sirven(entorno):
    _, _, web, _, _ = entorno
    for ruta in ("/", "/tablero", "/supervisor"):
        assert web.get(ruta).status_code == 200


def test_ninguna_pagina_usa_recursos_externos(sim):
    """La estación no tiene Internet: nada de CDN, fuentes ni scripts de afuera."""
    _, _, web = sim
    for ruta in ("/", "/tablero", "/supervisor", "/simulador", "/defensa"):
        html = web.get(ruta).data
        assert b"http://" not in html and b"https://" not in html and b"src=\"//" not in html, ruta


def test_reporte_se_publica_con_hora_del_navegador(entorno):
    broker, _, web, _, _ = entorno
    r = web.post("/api/reporte", json={"texto": "  Huele a quemado ", "ts_navegador": 1762700000.5})
    assert r.status_code == 202
    assert broker.ultimo(topicos.REPORTE) == {
        "id": r.get_json()["id"], "texto": "Huele a quemado", "ts_navegador": 1762700000.5}


def test_reporte_de_280_pasa_y_de_281_no(entorno):
    broker, _, web, _, _ = entorno
    assert web.post("/api/reporte", json={"texto": "x" * 280}).status_code == 202
    assert web.post("/api/reporte", json={"texto": "x" * 281}).status_code == 400


def test_reporte_con_acentos_cuenta_caracteres_no_bytes(entorno):
    broker, _, web, _, _ = entorno
    texto = "ñáéíóú" * 46 + "üñ"            # 278 caracteres, ~556 bytes en UTF-8
    assert web.post("/api/reporte", json={"texto": texto}).status_code == 202
    assert broker.ultimo(topicos.REPORTE)["texto"] == texto
    assert len(broker.de(topicos.REPORTE)) == 1


@pytest.mark.parametrize("cuerpo", [{"texto": "   "}, {"texto": 5}, {}])
def test_reporte_invalido_no_se_publica(entorno, cuerpo):
    broker, _, web, _, _ = entorno
    assert web.post("/api/reporte", json=cuerpo).status_code == 400
    assert broker.de(topicos.REPORTE) == []


def test_reporte_sin_broker_da_503(entorno, monkeypatch):
    _, servicio, web, _, _ = entorno
    monkeypatch.setattr(servicio.mqtt, "publicar", lambda *a, **k: False)
    assert web.post("/api/reporte", json={"texto": "hola"}).status_code == 503


def test_evento_se_encuentra_por_id(entorno):
    broker, _, web, _, _ = entorno
    assert web.get("/api/evento/abc").status_code == 404
    broker.publicar(topicos.EVENTO, {"id": "abc", "categoria": "falla_mecanica"})
    assert web.get("/api/evento/abc").get_json()["categoria"] == "falla_mecanica"


def test_evento_perdido_se_recupera_del_estado_retenido(entorno):
    """La web se reinició mientras el core analizaba: el `evento` no llegó, pero el `estado`
    retenido trae el último evento y el operario igual ve su resultado."""
    broker, _, web, _, _ = entorno
    broker.publicar(topicos.ESTADO, {"estado": "atencion",
                                     "ultimo_evento": {"id": "xyz", "categoria": "problema_calidad"}},
                    retener=True)
    assert web.get("/api/evento/xyz").get_json()["categoria"] == "problema_calidad"
    assert web.get("/api/evento/otro").status_code == 404


def test_estado_refleja_lo_publicado(entorno):
    broker, _, web, _, _ = entorno
    broker.publicar(topicos.SALIDAS, {"luz": "roja", "maquina": False})
    broker.publicar(topicos.SEGURIDAD, {"activo": True, "sensor": "vibracion"})
    broker.publicar(topicos.ESTADO, {"estado": "paro_seguridad", "ultimo_evento": None})
    broker.publicar(topicos.LECTURAS, {"vib_rms_g": 2.0, "temp_c": 30.0})
    s = web.get("/api/estado").get_json()
    assert s["salidas"]["luz"] == "roja" and s["seguridad"]["activo"]
    assert s["estado"]["estado"] == "paro_seguridad"
    assert s["lecturas"]["vib_rms_g"] == 2.0 and s["lecturas_edad_s"] == 0
    assert s["umbrales"]["umbral_confianza"] == 0.92


def test_reiniciar_con_pin_correcto(entorno):
    broker, _, web, _, _ = entorno
    assert web.post("/api/reiniciar", json={"pin": "1234"}).status_code == 200
    assert broker.ultimo(topicos.CMD_MAQUINA) == {"accion": "reiniciar", "origen": "web"}


@pytest.mark.parametrize("cuerpo", [{"pin": "0000"}, {"pin": 1234}, {}])
def test_reiniciar_sin_pin_valido_no_publica(entorno, cuerpo):
    broker, _, web, _, _ = entorno
    assert web.post("/api/reiniciar", json=cuerpo).status_code == 403
    assert broker.de(topicos.CMD_MAQUINA) == []


def test_pin_se_bloquea_tras_varios_fallos(entorno):
    broker, _, web, _, reloj = entorno
    for _ in range(MAX_FALLOS_PIN):
        assert web.post("/api/reiniciar", json={"pin": "0"}).status_code == 403
    assert web.post("/api/reiniciar", json={"pin": "1234"}).status_code == 429
    assert broker.de(topicos.CMD_MAQUINA) == []
    reloj.t += BLOQUEO_PIN_S + 1
    assert web.post("/api/reiniciar", json={"pin": "1234"}).status_code == 200


def test_umbrales_se_guardan_y_avisan(entorno):
    broker, _, web, ruta, _ = entorno
    valores = {"vib_rms_g": "1.5", "temp_c": "70", "umbral_confianza": "0.9"}
    assert web.post("/api/umbrales", json={"pin": "1234", "valores": valores}).status_code == 200
    c = cargar(ruta=str(ruta), entorno={})
    assert (c.umbrales.vib_rms_g, c.umbrales.temp_c, c.ollama.umbral_confianza) == (1.5, 70.0, 0.9)
    assert "# PROVISIONALES" in ruta.read_text(encoding="utf-8")
    assert broker.de(topicos.CMD_RECARGAR)
    assert web.get("/api/estado").get_json()["umbrales"]["vib_rms_g"] == 1.5


@pytest.mark.parametrize("valores", [
    {"vib_rms_g": "0"}, {"vib_rms_g": "-1"}, {"vib_rms_g": "4.1"}, {"temp_c": "126"},
    {"umbral_confianza": "1.5"}, {"temp_c": "abc"}, {"temp_c": "nan"}, {"temp_c": "inf"},
    {"vib_rms_g": "1,2,3"}, {"vib_rms_g": "0,0"}, {"pin": "1"}, {},
])
def test_umbrales_invalidos_no_tocan_el_archivo(entorno, valores):
    broker, _, web, ruta, _ = entorno
    antes = ruta.read_bytes()
    assert web.post("/api/umbrales", json={"pin": "1234", "valores": valores}).status_code == 400
    assert ruta.read_bytes() == antes
    assert broker.de(topicos.CMD_RECARGAR) == []


def test_umbrales_aceptan_coma_decimal(entorno):
    # Aceptación en la laptop (11 nov, A2): el supervisor escribe «0,05» como se lee en la página
    _, _, web, ruta, _ = entorno
    valores = {"vib_rms_g": "0,05", "umbral_confianza": "0,5"}
    assert web.post("/api/umbrales", json={"pin": "1234", "valores": valores}).status_code == 200
    c = cargar(ruta=str(ruta), entorno={})
    assert (c.umbrales.vib_rms_g, c.ollama.umbral_confianza) == (0.05, 0.5)


@pytest.mark.parametrize("ruta", ["/", "/supervisor"])
def test_formularios_no_usan_la_validacion_del_navegador(entorno, ruta):
    # Aceptación en la laptop (11 nov, O14 y A1): los avisos nativos salen en el idioma del
    # navegador (inglés) o no salen. La página y el servidor validan, en español.
    _, _, web, _, _ = entorno
    html = web.get(ruta).get_data(as_text=True)
    assert '<form id="form" novalidate>' in html
    assert 'type="number"' not in html and " required" not in html


def test_error_de_umbral_usa_el_nombre_que_ve_el_supervisor(entorno):
    _, _, web, _, _ = entorno
    r = web.post("/api/umbrales", json={"pin": "1234", "valores": {"vib_rms_g": "9"}})
    assert r.status_code == 400
    assert r.get_json()["error"] == "Vibración RMS máxima: debe ser mayor que 0 y como máximo 4."


def test_umbrales_requieren_pin(entorno):
    broker, _, web, ruta, _ = entorno
    antes = ruta.read_bytes()
    r = web.post("/api/umbrales", json={"pin": "0", "valores": {"temp_c": "70"}})
    assert r.status_code == 403
    assert ruta.read_bytes() == antes
    assert broker.de(topicos.CMD_RECARGAR) == []


def test_guardar_no_deja_temporales(entorno):
    _, _, web, ruta, _ = entorno
    web.post("/api/umbrales", json={"pin": "1234", "valores": {"temp_c": "70"}})
    web.post("/api/umbrales", json={"pin": "1234", "valores": {"temp_c": "999"}})
    assert [p.name for p in ruta.parent.iterdir()] == ["andon.conf"]


def test_recarga_cambia_el_pin(entorno):
    broker, servicio, web, ruta, _ = entorno
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("pin = 1234", "pin = 9876"), encoding="utf-8")
    broker.publicar(topicos.CMD_RECARGAR, {})
    assert servicio.cfg.web.pin == "9876"
    assert web.post("/api/reiniciar", json={"pin": "9876"}).status_code == 200


def test_recarga_invalida_conserva_la_configuracion(entorno):
    broker, servicio, _, ruta, _ = entorno
    ruta.write_text("[umbrales]\ntemp_c = -5\n", encoding="utf-8")
    broker.publicar(topicos.CMD_RECARGAR, {})
    assert servicio.cfg.umbrales.temp_c == Config().umbrales.temp_c


@pytest.fixture
def sim(tmp_path, monkeypatch):
    ruta = tmp_path / "andon.conf"
    shutil.copy(CONF, ruta)
    broker = BrokerFalso()
    cfg = cargar(ruta=str(ruta), entorno={"ANDON_MODO": "sim"})
    servicio = ServicioWeb(cfg, broker.cliente(), ruta_conf=str(ruta),
                           cargador=lambda: cargar(ruta=str(ruta), entorno={"ANDON_MODO": "sim"}))
    servicio.preparar()
    return broker, servicio, crear_app(servicio).test_client()


def test_simulador_no_existe_fuera_de_modo_sim(entorno):
    broker, _, web, _, _ = entorno
    assert web.get("/simulador").status_code == 404
    assert web.get("/defensa").status_code == 404     # sus casos usan el simulador
    assert web.post("/api/sim/ajustar", json={"vib_g": 2.0}).status_code == 404
    assert broker.de(topicos.SIM_AJUSTAR) == []
    assert b"/simulador" not in web.get("/").data and b"/defensa" not in web.get("/").data


def test_simulador_disponible_en_modo_sim(sim):
    _, _, web = sim
    assert web.get("/simulador").status_code == 200
    assert web.get("/defensa").status_code == 200
    assert b"/simulador" in web.get("/").data and b"/defensa" in web.get("/").data


def test_ajuste_publica_el_estado_completo_retenido(sim):
    broker, _, web = sim
    assert web.post("/api/sim/ajustar", json={"vib_g": 2.0}).status_code == 200
    assert web.post("/api/sim/ajustar", json={"mpu_ok": False}).status_code == 200
    esperado = {"vib_g": 2.0, "ruido_g": 0.01, "temp_c": None, "mpu_ok": False, "ds18b20_ok": True}
    assert broker.ultimo(topicos.SIM_AJUSTAR) == esperado
    assert broker.retenidos[topicos.SIM_AJUSTAR] == esperado
    assert web.get("/api/estado").get_json()["sim"] == esperado


@pytest.mark.parametrize("cuerpo", [{"vib_g": 3.1}, {"vib_g": -1}, {"vib_g": True}, {"temp_c": 500},
                                    {"mpu_ok": 1}, {"otro": 1}, {}])
def test_ajuste_invalido_no_se_publica(sim, cuerpo):
    broker, _, web = sim
    assert web.post("/api/sim/ajustar", json=cuerpo).status_code == 400
    assert broker.de(topicos.SIM_AJUSTAR) == []


def test_temperatura_vuelve_a_automatica(sim):
    broker, _, web = sim
    web.post("/api/sim/ajustar", json={"temp_c": 80})
    web.post("/api/sim/ajustar", json={"temp_c": None})
    assert broker.ultimo(topicos.SIM_AJUSTAR)["temp_c"] is None
