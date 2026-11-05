"""Cliente de Ollama para /v1/systemone (API JEV). Solo biblioteca estándar.

Contrato observado (ver docs/decisiones/D4-contrato-systemone.md):
  POST {url}/v1/systemone
  {"model": ..., "state": <texto>, "questions": {nombre: {"instructions": ...,
   "type": "choice", "criteria": {opcion: descripcion}}}}
  -> {"answers": {nombre: {"choice": ..., "probabilities": {...}, "confidence": ...}}}

Cualquier fallo se reporta con una subclase de ErrorOllama. El core lo traduce
a luz amarilla y revisión manual (REQ-F08); nunca se propaga como caída del servicio.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

MODELO = "tev1:0.8b"
PREGUNTA = "categoria"

CATEGORIAS = {
    "operacion_normal": "La máquina funciona con normalidad, sin ningún problema",
    "falla_mecanica": "Ruido, golpeteo, vibración, aspa o piezas rotas, flojas o desgastadas, atasco",
    "falla_electrica": "Chispas, olor a quemado, cortocircuito, cable dañado, la máquina no enciende",
    "problema_calidad": "Piezas defectuosas, rayadas o fuera de especificación, rechazo de producto",
    "material_faltante": "Falta material, insumos, tornillos o piezas para seguir produciendo",
}

INSTRUCCIONES = "Clasifica el reporte del operario de una estación de producción"


class ErrorOllama(Exception):
    """Base de los fallos al consultar el modelo."""


class ErrorConexion(ErrorOllama):
    """No se pudo contactar a Ollama."""


class ErrorTimeout(ErrorOllama):
    """Ollama no respondió dentro del tiempo límite."""


class ErrorRespuesta(ErrorOllama):
    """Ollama respondió con error HTTP o con un cuerpo que no cumple el contrato."""


@dataclass(frozen=True)
class Resultado:
    categoria: str
    prob: float  # probabilidad de la categoría elegida
    confianza: float  # campo "confidence" de la respuesta
    probabilidades: dict
    latencia_ms: int


def construir_estado(texto, vib_rms_g=None, temp_c=None):
    """Estado enviado al modelo (REQ-F04): reporte del operario + últimas lecturas."""
    partes = [f"Reporte del operario: {texto.strip()}"]
    lecturas = []
    if vib_rms_g is not None:
        lecturas.append(f"vibración {vib_rms_g:.2f} g RMS")
    if temp_c is not None:
        lecturas.append(f"temperatura {temp_c:.1f} °C")
    if lecturas:
        partes.append("Lecturas de sensores: " + ", ".join(lecturas) + ".")
    return " ".join(partes)


def construir_solicitud(estado, modelo=MODELO):
    return {
        "model": modelo,
        "state": estado,
        "questions": {
            PREGUNTA: {
                "instructions": INSTRUCCIONES,
                "type": "choice",
                "criteria": CATEGORIAS,
            }
        },
    }


def _interpretar(cuerpo):
    try:
        respuesta = cuerpo["answers"][PREGUNTA]
        categoria = respuesta["choice"]
        probabilidades = respuesta["probabilities"]
        prob = float(probabilidades[categoria])
        confianza = float(respuesta["confidence"])
    except (KeyError, TypeError, ValueError) as e:
        raise ErrorRespuesta(f"respuesta fuera de contrato: {e!r}") from e
    if categoria not in CATEGORIAS:
        raise ErrorRespuesta(f"categoría desconocida: {categoria!r}")
    if not 0.0 <= prob <= 1.0:
        raise ErrorRespuesta(f"probabilidad fuera de rango: {prob}")
    return categoria, prob, confianza, probabilidades


def clasificar(texto, vib_rms_g=None, temp_c=None, url="http://localhost:11434",
               modelo=MODELO, timeout_s=10.0):
    """Clasifica un reporte. Devuelve Resultado o lanza una subclase de ErrorOllama."""
    estado = construir_estado(texto, vib_rms_g, temp_c)
    datos = json.dumps(construir_solicitud(estado, modelo)).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/systemone", data=datos,
        headers={"Content-Type": "application/json"}, method="POST")

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            crudo = r.read()
    except urllib.error.HTTPError as e:
        raise ErrorRespuesta(f"HTTP {e.code}: {e.read()[:200]!r}") from e
    except TimeoutError as e:
        raise ErrorTimeout(f"sin respuesta en {timeout_s} s") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise ErrorTimeout(f"sin respuesta en {timeout_s} s") from e
        raise ErrorConexion(str(e.reason)) from e
    except OSError as e:
        raise ErrorConexion(str(e)) from e
    latencia_ms = round((time.monotonic() - t0) * 1000)

    try:
        cuerpo = json.loads(crudo)
    except ValueError as e:
        raise ErrorRespuesta("el cuerpo no es JSON válido") from e
    categoria, prob, confianza, probabilidades = _interpretar(cuerpo)
    return Resultado(categoria, prob, confianza, probabilidades, latencia_ms)
