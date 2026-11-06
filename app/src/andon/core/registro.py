"""Registro persistente de eventos en SQLite (REQ-F10): fecha, lecturas, texto, categoría,
probabilidad, acción y latencia. Una conexión compartida protegida por un cerrojo (el core
guarda desde el hilo que consulta al modelo y lee desde el hilo MQTT).
"""
import logging
import os
import sqlite3
import threading

log = logging.getLogger(__name__)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    reporte_id    TEXT,
    ts            REAL NOT NULL,
    vib_rms_g     REAL,
    temp_c        REAL,
    texto         TEXT NOT NULL,
    categoria     TEXT,
    prob          REAL,
    accion        TEXT NOT NULL,
    area          TEXT,
    latencia_ms   INTEGER,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS eventos_ts ON eventos (ts);
"""
CAMPOS = ("reporte_id", "ts", "vib_rms_g", "temp_c", "texto", "categoria", "prob",
          "accion", "area", "latencia_ms", "error")


class Registro:
    def __init__(self, ruta):
        if ruta != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self._db = sqlite3.connect(ruta, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(ESQUEMA)

    def guardar(self, e):
        """Guarda un evento (dict con las claves de CAMPOS; las ausentes quedan nulas)."""
        valores = [e.get(c) for c in CAMPOS]
        with self._lock:
            cur = self._db.execute(
                f"INSERT INTO eventos ({','.join(CAMPOS)}) VALUES ({','.join('?' * len(CAMPOS))})",
                valores)
            self._db.commit()
            return cur.lastrowid

    def ultimos(self, n=20):
        with self._lock:
            filas = self._db.execute(
                "SELECT * FROM eventos ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        return [dict(f) for f in filas]

    def contar(self):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]

    def cerrar(self):
        with self._lock:
            self._db.close()
