"""Lógica de decisión de andon-core: Tabla 9 de la propuesta (REQ-F06, REQ-F08).

Solo si la probabilidad de la categoría elegida alcanza el umbral de confianza se aplica la
tabla. Con probabilidad menor, o si Ollama falla, la decisión es luz amarilla y revisión
manual: nunca se actúa sobre la máquina por una clasificación dudosa.

Ninguna decisión arranca la máquina (invariante 3): como mucho la detiene.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    luz: str            # verde | amarilla | roja
    parar: bool         # ordenar cmd/maquina parar (origen core)
    area: str | None    # a quién se avisa
    accion: str         # ninguna | parar_maquina | avisar | revision_manual


TABLA = {
    "operacion_normal": Decision("verde", False, None, "ninguna"),
    "falla_mecanica": Decision("roja", True, "mantenimiento", "parar_maquina"),
    "falla_electrica": Decision("roja", True, "mantenimiento", "parar_maquina"),
    "problema_calidad": Decision("amarilla", False, "calidad", "avisar"),
    "material_faltante": Decision("amarilla", False, "supervision", "avisar"),
}
REVISION_MANUAL = Decision("amarilla", False, "supervision", "revision_manual")


def decidir(categoria, prob, umbral):
    """Decisión para una clasificación. `prob >= umbral` aplica la Tabla 9."""
    d = TABLA.get(categoria)
    if d is None or prob is None or prob < umbral:
        return REVISION_MANUAL
    return d
