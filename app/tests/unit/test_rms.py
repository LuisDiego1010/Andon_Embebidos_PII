import math

import pytest

from andon.sensores.rms import HZ, VentanaRms, rms_dinamico


def senoide(rms_por_eje, n=HZ, ciclos=25, offset=(0.0, 0.0, 1.0)):
    amp = rms_por_eje * math.sqrt(2)
    return [tuple(offset[e] + amp * math.sin(2 * math.pi * ciclos * i / n + e) for e in range(3))
            for i in range(n)]


def test_reposo_perfecto_es_cero():
    assert rms_dinamico([(0.0, 0.0, 1.0)] * 100) == pytest.approx(0.0, abs=1e-12)


def test_la_gravedad_y_el_desvio_no_cuentan():
    a = rms_dinamico([(0.5, -0.3, 1.0)] * 50)
    b = rms_dinamico([(0.0, 0.0, 0.0)] * 50)
    assert a == pytest.approx(b, abs=1e-12) == pytest.approx(0.0, abs=1e-12)


def test_rms_de_una_senoide_en_un_eje():
    m = [(0.2 * math.sqrt(2) * math.sin(2 * math.pi * 25 * i / 100), 0.0, 1.0) for i in range(100)]
    assert rms_dinamico(m) == pytest.approx(0.2, rel=1e-6)


def test_rms_del_vector_suma_los_tres_ejes():
    # 0,1 g RMS en cada eje → raíz de (3 · 0,1²)
    assert rms_dinamico(senoide(0.1)) == pytest.approx(0.1 * math.sqrt(3), rel=1e-6)


def test_lista_vacia():
    assert rms_dinamico([]) == 0.0


def test_ventana_necesita_medio_segundo():
    v = VentanaRms()
    assert v.rms() is None and not v.listo
    for m in senoide(0.1)[:49]:
        v.agregar(*m)
    assert v.rms() is None
    v.agregar(0, 0, 1)
    assert v.listo and v.rms() is not None


def test_ventana_desliza_y_olvida_lo_viejo():
    v = VentanaRms()
    for m in senoide(1.0):          # 1 s fuerte
        v.agregar(*m)
    fuerte = v.rms()
    for _ in range(HZ):             # 1 s de reposo lo reemplaza
        v.agregar(0, 0, 1)
    assert fuerte > 1.0 and v.rms() == pytest.approx(0.0, abs=1e-9)


def test_limpiar():
    v = VentanaRms()
    for m in senoide(1.0):
        v.agregar(*m)
    v.limpiar()
    assert v.rms() is None
