"""Registro SQLite de eventos (REQ-F10)."""
import sqlite3

from andon.core.registro import Registro

EV = {"reporte_id": "r1", "ts": 1.5, "vib_rms_g": 0.4, "temp_c": 40.0, "texto": "ruido",
      "categoria": "falla_mecanica", "prob": 0.97, "accion": "parar_maquina",
      "area": "mantenimiento", "latencia_ms": 16800, "error": None}


def test_guarda_y_lee_todos_los_campos():
    r = Registro(":memory:")
    assert r.guardar(EV) == 1
    (fila,) = r.ultimos()
    assert {k: fila[k] for k in EV} == EV


def test_ultimos_en_orden_inverso_y_limitados():
    r = Registro(":memory:")
    for i in range(5):
        r.guardar({**EV, "texto": f"t{i}"})
    assert [f["texto"] for f in r.ultimos(2)] == ["t4", "t3"]
    assert r.contar() == 5


def test_campos_ausentes_quedan_nulos_pero_texto_y_accion_son_obligatorios(tmp_path):
    r = Registro(":memory:")
    r.guardar({"ts": 1.0, "texto": "x", "accion": "revision_manual"})
    assert r.ultimos()[0]["categoria"] is None
    try:
        r.guardar({"ts": 1.0})
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("debía rechazar un evento sin texto ni acción")


def test_persiste_en_disco_y_crea_el_directorio(tmp_path):
    ruta = str(tmp_path / "sub" / "andon.db")
    r = Registro(ruta)
    r.guardar(EV)
    r.cerrar()
    assert Registro(ruta).contar() == 1
