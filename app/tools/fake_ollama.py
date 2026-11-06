#!/usr/bin/env python3
"""Ollama falso para pruebas deterministas de andon-core (QEMU, CI, sin el modelo).

    fake_ollama.py --puerto 11434 [--latencia-s 0.5] [--modo ok|error|colgado|basura]

Habla el mismo contrato que /v1/systemone (docs/decisiones/D4): clasifica por palabras clave
del reporte y devuelve probabilidades fijas. Frases de control para las pruebas:
  - «ambiguo» ........ probabilidad 0,60 (cae bajo el umbral de confianza)
  - «#prob=0.xx» ..... fuerza la probabilidad de la categoría elegida
  - «#lento=N» ....... tarda N segundos en responder
  - «#error» ......... responde HTTP 500 · «#basura» responde algo que no es JSON
También se importa desde las pruebas: `ServidorFalso(...)` arranca en un puerto libre.
GET /api/version responde como el Ollama real (sirve de sonda de salud).
"""
import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CATEGORIAS = ("operacion_normal", "falla_mecanica", "falla_electrica",
              "problema_calidad", "material_faltante")

# Orden importa: la primera que coincide gana. Lo eléctrico va antes que lo mecánico
# («olor a quemado del motor» es eléctrico).
PALABRAS = (
    ("falla_electrica", ("chispa", "quemado", "cortocircuito", "cable", "no enciende", "eléctric", "electric")),
    ("material_faltante", ("falta", "no hay material", "sin material", "insumo", "tornillo", "se acabó", "se acabo")),
    ("problema_calidad", ("defectuos", "rayad", "calidad", "especificación", "especificacion", "rechazo")),
    ("falla_mecanica", ("ruido", "golpe", "vibra", "aspa", "atasc", "rota", "floja", "desgast", "mecánic", "mecanic")),
    ("operacion_normal", ("normal", "sin novedad", "en orden", "funciona bien", "todo bien", "sin problema")),
)
PROB_CLARA = 0.97
PROB_AMBIGUA = 0.60


def clasificar(estado):
    """(categoria, probabilidad) para un `state` de texto."""
    t = estado.lower()
    m = re.search(r"#prob=([01](?:\.\d+)?)", t)
    forzada = float(m.group(1)) if m else None
    cat = None
    for nombre, claves in PALABRAS:
        if any(c in t for c in claves):
            cat = nombre
            break
    prob = PROB_CLARA
    if cat is None:
        cat, prob = "falla_mecanica", PROB_AMBIGUA   # lo que no entiende, lo adivina mal
    if "ambiguo" in t:
        prob = PROB_AMBIGUA
    return cat, (forzada if forzada is not None else prob)


def respuesta(modelo, estado, opciones):
    cat, prob = clasificar(estado)
    if cat not in opciones:
        cat = next(iter(opciones))
    resto = (1.0 - prob) / max(len(opciones) - 1, 1)
    probs = {o: (prob if o == cat else round(resto, 4)) for o in opciones}
    return {
        "model": modelo,
        "answers": {"categoria": {"type": "choice", "choice": cat, "probabilities": probs,
                                  "confidence": prob}},
        "usage": {"input_tokens": len(estado.split()), "output_tokens": 0},
    }


class ServidorFalso:
    """Servidor en un hilo. `modo` y `latencia_s` pueden cambiarse mientras corre."""

    def __init__(self, puerto=0, modo="ok", latencia_s=0.0, host="127.0.0.1"):
        self.modo, self.latencia_s = modo, latencia_s
        self.consultas = []                      # `state` de cada POST recibido
        padre = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _enviar(self, codigo, cuerpo, tipo="application/json"):
                datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def do_GET(self):
                if self.path == "/api/version":
                    self._enviar(200, {"version": "0.0.0-fake"})
                else:
                    self._enviar(405, {"error": "method not allowed"})

            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                try:
                    cuerpo = json.loads(self.rfile.read(largo))
                    estado = cuerpo["state"]
                    opciones = cuerpo["questions"]["categoria"]["criteria"]
                except (ValueError, KeyError, TypeError):
                    return self._enviar(400, {"error": "solicitud fuera de contrato"})
                padre.consultas.append(estado)
                m = re.search(r"#lento=(\d+(?:\.\d+)?)", estado)
                espera = float(m.group(1)) if m else padre.latencia_s
                if padre.modo == "colgado":
                    espera = max(espera, 3600)
                if espera:
                    time.sleep(espera)
                if padre.modo == "error" or "#error" in estado:
                    return self._enviar(500, {"error": "fallo simulado"})
                if padre.modo == "basura" or "#basura" in estado:
                    return self._enviar(200, b"<html>no es json</html>", "text/html")
                self._enviar(200, respuesta(cuerpo.get("model", "tev1:0.8b"), estado, opciones))

        self._srv = ThreadingHTTPServer((host, puerto), H)
        self._srv.daemon_threads = True
        self._hilo = threading.Thread(target=self._srv.serve_forever, daemon=True)

    @property
    def url(self):
        host, puerto = self._srv.server_address[:2]
        return f"http://{host}:{puerto}"

    def iniciar(self):
        self._hilo.start()
        return self

    def detener(self):
        self._srv.shutdown()
        self._srv.server_close()

    def __enter__(self):
        return self.iniciar()

    def __exit__(self, *exc):
        self.detener()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=11434)
    ap.add_argument("--latencia-s", type=float, default=0.0)
    ap.add_argument("--modo", choices=("ok", "error", "colgado", "basura"), default="ok")
    a = ap.parse_args()
    srv = ServidorFalso(a.puerto, a.modo, a.latencia_s, a.host)
    print(f"fake_ollama en {srv.url} (modo {a.modo}, latencia {a.latencia_s} s)", flush=True)
    try:
        srv._srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
