import json

import pytest

from andon.common.config import Umbrales
from andon.sensores.seguridad import (Paro, Seguridad, borrar_paro, guardar_paro,
                                      leer_paro)


@pytest.fixture
def seg():
    return Seguridad(Umbrales(vib_rms_g=1.0, temp_c=60.0), tolerancia_fallo_s=2.0, ahora=100.0)


def test_sin_cruce_no_hay_paro(seg):
    assert seg.evaluar_vibracion(0.99) is None and seg.evaluar_temperatura(59.9) is None
    assert not seg.activo


def test_exactamente_el_umbral_no_dispara(seg):
    assert seg.evaluar_vibracion(1.0) is None and seg.evaluar_temperatura(60.0) is None


def test_vibracion_sobre_el_umbral(seg):
    p = seg.evaluar_vibracion(1.5)
    assert p == Paro("vibracion", 1.5, 1.0) and seg.activo


def test_temperatura_sobre_el_umbral(seg):
    assert seg.evaluar_temperatura(75.0) == Paro("temperatura", 75.0, 60.0)


def test_paro_retenido_conserva_la_primera_causa(seg):
    seg.evaluar_vibracion(1.5)
    assert seg.evaluar_temperatura(99.0) is None       # no cambia de causa
    assert seg.evaluar_vibracion(0.1) is None           # bajar el valor no lo libera
    assert seg.causa.sensor == "vibracion" and seg.activo


def test_reiniciar_libera(seg):
    seg.evaluar_vibracion(1.5)
    assert seg.reiniciar(200.0) is True and not seg.activo
    assert seg.reiniciar(200.0) is False


def test_payload_activo_e_inactivo(seg):
    assert seg.payload(5.0) == {"ts": 5.0, "activo": False, "sensor": None, "valor": None, "umbral": None}
    seg.evaluar_temperatura(70.0)
    assert seg.payload(6.0) == {"ts": 6.0, "activo": True, "sensor": "temperatura", "valor": 70.0, "umbral": 60.0}


# --- falla de sensor (D13) ---
def test_dentro_de_la_tolerancia_no_dispara(seg):
    assert seg.vigilar(101.9) is None


def test_sin_lectura_mas_de_la_tolerancia_dispara(seg):
    p = seg.vigilar(102.5)
    assert p.sensor == "mpu6050_fallo" and p.umbral == 2.0 and p.valor == pytest.approx(2.5)


def test_una_lectura_reinicia_la_cuenta(seg):
    seg.lectura_ok("mpu6050", 101.9)
    seg.lectura_ok("ds18b20", 101.9)
    assert seg.vigilar(103.8) is None and seg.vigilar(104.0) is not None


def test_cada_sensor_se_vigila_por_separado(seg):
    seg.lectura_ok("mpu6050", 109.0)
    assert seg.vigilar(110.0).sensor == "ds18b20_fallo"


def test_reiniciar_da_gracia_nueva_a_los_sensores(seg):
    seg.vigilar(150.0)
    seg.reiniciar(150.0)
    assert seg.vigilar(151.9) is None and seg.vigilar(152.5) is not None


def test_actualizar_umbrales_en_caliente(seg):
    assert seg.evaluar_vibracion(1.5) is not None
    seg.reiniciar(100.0)
    seg.actualizar(Umbrales(vib_rms_g=3.0, temp_c=60.0), 5.0)
    assert seg.evaluar_vibracion(1.5) is None and seg.tolerancia_fallo_s == 5.0


# --- persistencia ---
def test_guardar_leer_borrar(tmp_path):
    ruta = str(tmp_path / "sub" / "paro.json")
    assert leer_paro(ruta) is None
    assert guardar_paro(ruta, Paro("vibracion", 1.5, 1.0), 123.0)
    assert leer_paro(ruta) == Paro("vibracion", 1.5, 1.0)
    borrar_paro(ruta)
    assert leer_paro(ruta) is None
    borrar_paro(ruta)  # borrar lo que no existe no falla


def test_archivo_ilegible_se_trata_como_paro_activo(tmp_path):
    ruta = tmp_path / "paro.json"
    ruta.write_text("{ esto no es json", encoding="utf-8")
    assert leer_paro(str(ruta)).sensor == "paro_guardado_ilegible"
    ruta.write_text(json.dumps({"sensor": "x"}), encoding="utf-8")  # faltan campos
    assert leer_paro(str(ruta)) is not None


def test_guardar_en_ruta_imposible_no_lanza(tmp_path):
    archivo = tmp_path / "es_un_archivo"
    archivo.write_text("x")
    assert guardar_paro(str(archivo / "no" / "paro.json"), Paro("a", 1, 1), 1.0) is False


def test_restaurar(seg):
    seg.restaurar(Paro("temperatura", 80.0, 60.0), 500.0)
    assert seg.activo and seg.causa.sensor == "temperatura"
