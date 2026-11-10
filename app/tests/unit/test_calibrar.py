import importlib.util
from pathlib import Path

r = Path(__file__).resolve().parents[2] / "tools" / "calibrar.py"
spec = importlib.util.spec_from_file_location("calibrar", r)
calibrar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibrar)


def test_propone_con_margen():
    assert calibrar.proponer([0.1, 0.2], [30.0, 40.0]) == (0.3, 55.0)


def test_no_propone_mas_alla_del_rango_del_sensor():
    assert calibrar.proponer([3.5], [120.0]) == (4.0, 125.0)
