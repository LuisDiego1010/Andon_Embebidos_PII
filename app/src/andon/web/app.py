"""Rutas de Flask: tres páginas y una API JSON. Sin recursos externos: la estación no tiene Internet."""

from flask import Flask, abort, jsonify, render_template, request

from andon.common.config import ErrorConfig
from andon.web.servicio import MAX_TEXTO, PIN_BLOQUEADO, PIN_OK


def _numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def crear_app(servicio):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

    def error(mensaje, codigo):
        return jsonify(error=mensaje), codigo

    def rechazo_pin(datos):
        """Devuelve la respuesta de error, o None si el PIN es válido."""
        resultado = servicio.verificar_pin(datos.get("pin"))
        if resultado == PIN_OK:
            return None
        if resultado == PIN_BLOQUEADO:
            return error("Demasiados intentos. Espere 30 s.", 429)
        return error("PIN incorrecto.", 403)

    @app.context_processor
    def plantillas():
        return {"modo_sim": servicio.modo_sim}

    @app.get("/simulador")
    def simulador():
        if not servicio.modo_sim:      # en producción no existe forma de falsear sensores
            abort(404)
        return render_template("simulador.html", max_texto=MAX_TEXTO)

    @app.post("/api/sim/ajustar")
    def api_sim_ajustar():
        if not servicio.modo_sim:
            abort(404)
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict) or not datos:
            return error("Sin controles que ajustar.", 400)
        try:
            enviado = servicio.ajustar_simulador(datos)
        except ValueError as e:
            return error(str(e), 400)
        return jsonify(ok=True) if enviado else error("No se pudo enviar el ajuste.", 503)

    @app.get("/defensa")
    def defensa():
        if not servicio.modo_sim:      # sus casos mueven las perillas del simulador (D15)
            abort(404)
        return render_template("defensa.html")

    @app.get("/")
    def formulario():
        return render_template("formulario.html", max_texto=MAX_TEXTO)

    @app.get("/tablero")
    def tablero():
        return render_template("tablero.html")

    @app.get("/supervisor")
    def supervisor():
        return render_template("supervisor.html")

    @app.get("/api/estado")
    def api_estado():
        return jsonify(servicio.instantanea())

    @app.get("/api/evento/<reporte_id>")
    def api_evento(reporte_id):
        evento = servicio.evento(reporte_id)
        return jsonify(evento) if evento else error("Aún sin resultado.", 404)

    @app.post("/api/reporte")
    def api_reporte():
        datos = request.get_json(silent=True) or {}
        texto = datos.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return error("Escriba qué está pasando.", 400)
        texto = texto.strip()
        if len(texto) > MAX_TEXTO:
            return error(f"El reporte supera {MAX_TEXTO} caracteres.", 400)
        ts = datos.get("ts_navegador")
        rid = servicio.enviar_reporte(texto, ts if _numero(ts) else None)
        if rid is None:
            return error("La estación no pudo recibir el reporte. Intente de nuevo.", 503)
        return jsonify(id=rid), 202

    @app.post("/api/reiniciar")
    def api_reiniciar():
        datos = request.get_json(silent=True) or {}
        rechazo = rechazo_pin(datos)
        if rechazo:
            return rechazo
        if not servicio.reiniciar_maquina():
            return error("No se pudo enviar la orden.", 503)
        return jsonify(ok=True)

    @app.post("/api/umbrales")
    def api_umbrales():
        datos = request.get_json(silent=True) or {}
        rechazo = rechazo_pin(datos)
        if rechazo:
            return rechazo
        try:
            aviso = servicio.guardar_umbrales(datos.get("valores") or {})
        except ErrorConfig as e:
            return error(str(e), 400)
        except OSError as e:
            return error(f"No se pudo guardar la configuración: {e.strerror}", 500)
        if not aviso:
            return error("Guardado, pero no se pudo avisar a los servicios.", 503)
        return jsonify(ok=True)

    return app
