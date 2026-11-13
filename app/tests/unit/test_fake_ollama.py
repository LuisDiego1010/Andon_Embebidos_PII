"""tools/fake_ollama.py habla el mismo contrato que el cliente real (D4)."""
import importlib.util
import pathlib

import pytest

from andon.core import ollama

RUTA = pathlib.Path(__file__).resolve().parents[2] / "tools" / "fake_ollama.py"
spec = importlib.util.spec_from_file_location("fake_ollama", RUTA)
fake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fake)


@pytest.fixture
def srv():
    with fake.ServidorFalso() as s:
        yield s


@pytest.mark.parametrize("texto,cat", [
    ("Todo funciona bien, sin novedades", "operacion_normal"),
    ("El ventilador hace un ruido metálico fuerte", "falla_mecanica"),
    ("Salen chispas y huele a quemado", "falla_electrica"),
    ("Las piezas salen rayadas", "problema_calidad"),
    ("Falta material para seguir", "material_faltante"),
    ("olor a quemado cerca del motor", "falla_electrica"),
])
def test_clasifica_por_palabras_clave(srv, texto, cat):
    r = ollama.clasificar(texto, url=srv.url)
    assert r.categoria == cat and r.prob >= 0.92


def test_ambiguo_cae_bajo_el_umbral(srv):
    assert ollama.clasificar("algo ambiguo pasa", url=srv.url).prob < 0.92
    assert ollama.clasificar("xyz", url=srv.url).prob < 0.92        # no entiende


def test_probabilidad_forzada(srv):
    assert ollama.clasificar("ruido #prob=0.5", url=srv.url).prob == pytest.approx(0.5)


def test_las_lecturas_viajan_en_el_estado(srv):
    ollama.clasificar("ruido", 0.9, 42.0, url=srv.url)
    assert "vibración 0.90 g RMS" in srv.consultas[-1]


def test_error_http_y_basura_son_errores_del_cliente():
    with fake.ServidorFalso(modo="error") as s, pytest.raises(ollama.ErrorRespuesta):
        ollama.clasificar("ruido", url=s.url)
    with fake.ServidorFalso(modo="basura") as s, pytest.raises(ollama.ErrorRespuesta):
        ollama.clasificar("ruido", url=s.url)


def test_colgado_agota_el_timeout():
    with fake.ServidorFalso(modo="colgado") as s, pytest.raises(ollama.ErrorTimeout):
        ollama.clasificar("ruido", url=s.url, timeout_s=0.3)


def test_marcas_en_el_texto_provocan_fallos(srv):
    with pytest.raises(ollama.ErrorRespuesta):
        ollama.clasificar("ruido #error", url=srv.url)


def test_calentar_funciona_contra_el_falso(srv):
    assert ollama.calentar(url=srv.url) is not None
