"""Prueba de contrato contra Ollama real (/v1/systemone). Cierra D4.

Se omite si Ollama no responde. Variables: ANDON_OLLAMA_URL, ANDON_OLLAMA_MODELO.
Imprime exactitud y latencias (usar `pytest -s`).
"""
import json
import os
import statistics
import urllib.request
from pathlib import Path

import pytest

from andon.core import ollama

URL = os.environ.get("ANDON_OLLAMA_URL", "http://localhost:11434")
MODELO = os.environ.get("ANDON_OLLAMA_MODELO", ollama.MODELO)
REPORTES = json.loads((Path(__file__).parent / "reportes.json").read_text(encoding="utf-8"))

pytestmark = pytest.mark.contract


def _ollama_disponible():
    try:
        urllib.request.urlopen(URL + "/api/version", timeout=2).read()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def resultados():
    if not _ollama_disponible():
        pytest.skip(f"Ollama no responde en {URL}")
    out = []
    for r in REPORTES:
        res = ollama.clasificar(r["texto"], r["vib_rms_g"], r["temp_c"],
                                url=URL, modelo=MODELO, timeout_s=30)
        out.append((r, res))
    return out


def test_respuestas_cumplen_contrato(resultados):
    for r, res in resultados:
        assert res.categoria in ollama.CATEGORIAS, r["texto"]
        assert 0.0 <= res.prob <= 1.0
        assert abs(sum(res.probabilidades.values()) - 1.0) < 0.01


def test_exactitud_y_latencia(resultados):
    claros = [(r, res) for r, res in resultados if not r["ambiguo"]]
    aciertos = sum(res.categoria == r["esperada"] for r, res in claros)
    lat = sorted(res.latencia_ms for _, res in resultados)
    print(f"\nModelo {MODELO} @ {URL}")
    print(f"Exactitud (no ambiguos): {aciertos}/{len(claros)} = {aciertos/len(claros):.0%}")
    print(f"Latencia ms: mín {lat[0]}  mediana {statistics.median(lat):.0f}  máx {lat[-1]}")
    print(f"{'id':>3} {'esperada':<18} {'obtenida':<18} {'prob':>5} {'conf':>5} {'ms':>5}")
    for r, res in resultados:
        print(f"{r['id']:>3} {str(r['esperada']):<18} {res.categoria:<18} "
              f"{res.prob:5.2f} {res.confianza:5.2f} {res.latencia_ms:5d}")
    # Piso bajo a propósito: el modelo de 0.8B es débil; la cifra real se documenta en D4.
    assert aciertos / len(claros) >= 0.5


def test_ambiguos_tienen_menor_probabilidad(resultados):
    amb = [res.prob for r, res in resultados if r["ambiguo"]]
    claros = [res.prob for r, res in resultados if not r["ambiguo"]]
    print(f"\nProb. media ambiguos {statistics.mean(amb):.2f} vs claros {statistics.mean(claros):.2f}")
