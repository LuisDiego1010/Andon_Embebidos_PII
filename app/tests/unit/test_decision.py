"""Tabla 9 y umbral de confianza (REQ-F06, REQ-F08)."""
import pytest

from andon.core.decision import REVISION_MANUAL, TABLA, decidir

UMBRAL = 0.92


@pytest.mark.parametrize("cat,luz,parar,area", [
    ("operacion_normal", "verde", False, None),
    ("falla_mecanica", "roja", True, "mantenimiento"),
    ("falla_electrica", "roja", True, "mantenimiento"),
    ("problema_calidad", "amarilla", False, "calidad"),
    ("material_faltante", "amarilla", False, "supervision"),
])
def test_tabla_9(cat, luz, parar, area):
    d = decidir(cat, 0.97, UMBRAL)
    assert (d.luz, d.parar, d.area) == (luz, parar, area)


@pytest.mark.parametrize("cat", list(TABLA))
def test_bajo_el_umbral_es_revision_manual(cat):
    assert decidir(cat, 0.91, UMBRAL) is REVISION_MANUAL


def test_en_el_umbral_se_aplica_la_tabla():
    assert decidir("falla_mecanica", UMBRAL, UMBRAL).parar


@pytest.mark.parametrize("cat,prob", [(None, None), ("inventada", 0.99), ("falla_mecanica", None)])
def test_sin_clasificacion_valida_es_revision_manual(cat, prob):
    assert decidir(cat, prob, UMBRAL) is REVISION_MANUAL


def test_revision_manual_nunca_para_la_maquina():
    assert not REVISION_MANUAL.parar and REVISION_MANUAL.luz == "amarilla"


def test_ninguna_decision_arranca_la_maquina():
    # El Decision no tiene una acción de arranque: solo `parar` (invariante 3).
    assert all(d.accion != "arrancar" for d in [*TABLA.values(), REVISION_MANUAL])
