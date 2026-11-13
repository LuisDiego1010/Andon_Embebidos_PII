"""Pruebas del cliente de Ollama con un servidor HTTP local (sin modelo real)."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from andon.core import ollama
from andon.core.ollama import (ErrorConexion, ErrorRespuesta, ErrorTimeout,
                               calentar, clasificar, construir_estado,
                               construir_solicitud)


def respuesta_ok(cat="falla_mecanica", prob=0.9):
    probs = {c: 0.0 for c in ollama.CATEGORIAS}
    probs[cat] = prob
    return {"model": "tev1:0.8b",
            "answers": {"categoria": {"type": "choice", "choice": cat,
                                      "probabilities": probs, "confidence": prob}},
            "usage": {"input_tokens": 10, "output_tokens": 0}}


@pytest.fixture
def servidor():
    """Servidor falso; el test fija .estado, .cuerpo y .espera_s."""
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.server.recibido = json.loads(self.rfile.read(n))
            self.server.ruta = self.path
            time.sleep(self.server.espera_s)
            datos = self.server.cuerpo
            datos = datos if isinstance(datos, bytes) else json.dumps(datos).encode()
            try:
                self.send_response(self.server.estado)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), H)
    s.estado, s.cuerpo, s.espera_s = 200, respuesta_ok(), 0
    threading.Thread(target=s.serve_forever, daemon=True).start()
    s.url = f"http://127.0.0.1:{s.server_port}"
    yield s
    s.shutdown()
    s.server_close()


def test_clasificar_ok(servidor):
    r = clasificar("ruido metálico", 0.9, 40.0, url=servidor.url)
    assert r.categoria == "falla_mecanica"
    assert r.prob == pytest.approx(0.9)
    assert r.latencia_ms >= 0
    assert servidor.ruta == "/v1/systemone"
    q = servidor.recibido["questions"]["categoria"]
    assert q["type"] == "choice" and set(q["criteria"]) == set(ollama.CATEGORIAS)
    assert "ruido metálico" in servidor.recibido["state"]


def test_estado_incluye_lecturas():
    e = construir_estado("  hola ", 0.25, 31.5)
    assert "hola" in e and "0.25 g" in e and "31.5 °C" in e


def test_estado_sin_lecturas():
    assert "Lecturas" not in construir_estado("hola")


def test_solicitud_usa_modelo():
    assert construir_solicitud("x", "otro")["model"] == "otro"


def test_timeout(servidor):
    servidor.espera_s = 1.0
    with pytest.raises(ErrorTimeout):
        clasificar("x", url=servidor.url, timeout_s=0.2)


def test_conexion_rechazada():
    with pytest.raises(ErrorConexion):
        clasificar("x", url="http://127.0.0.1:1", timeout_s=1)


def test_error_http(servidor):
    servidor.estado, servidor.cuerpo = 404, {"error": "model 'nada' not found"}
    with pytest.raises(ErrorRespuesta, match="404"):
        clasificar("x", url=servidor.url)


def test_json_invalido(servidor):
    servidor.cuerpo = b"esto no es json"
    with pytest.raises(ErrorRespuesta, match="JSON"):
        clasificar("x", url=servidor.url)


def test_categoria_desconocida(servidor):
    servidor.cuerpo = respuesta_ok()
    a = servidor.cuerpo["answers"]["categoria"]
    a["choice"] = "otra"
    a["probabilities"]["otra"] = 0.9
    with pytest.raises(ErrorRespuesta, match="desconocida"):
        clasificar("x", url=servidor.url)


def test_probabilidad_fuera_de_rango(servidor):
    servidor.cuerpo = respuesta_ok(prob=1.5)
    with pytest.raises(ErrorRespuesta, match="rango"):
        clasificar("x", url=servidor.url)


@pytest.mark.parametrize("cuerpo", [{}, {"answers": {}}, {"answers": {"categoria": {"choice": "falla_mecanica"}}}, []])
def test_estructura_incompleta(servidor, cuerpo):
    servidor.cuerpo = cuerpo
    with pytest.raises(ErrorRespuesta):
        clasificar("x", url=servidor.url)


def test_calentar_devuelve_segundos(servidor):
    servidor.espera_s = 0.1
    t = calentar(url=servidor.url)
    assert t is not None and t >= 0.1
    assert "calentamiento" in servidor.recibido["state"]


def test_calentar_no_lanza_si_falla():
    assert calentar(url="http://127.0.0.1:1", timeout_s=1) is None


def test_calentar_no_lanza_con_timeout(servidor):
    servidor.espera_s = 1.0
    assert calentar(url=servidor.url, timeout_s=0.2) is None


def test_timeout_por_defecto_cubre_la_placa():
    assert ollama.TIMEOUT_S >= 45
