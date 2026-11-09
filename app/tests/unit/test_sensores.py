"""andon-sensores con reloj falso, HalSim y un broker en memoria (sin hilos ni esperas)."""
import pytest

from andon.common import topicos
from andon.common.config import Config, ErrorConfig, SensoresCfg, Umbrales
from andon.hal.base import ErrorHardware
from andon.hal.sim import HalSim
from andon.sensores.seguridad import leer_paro
from andon.sensores.servicio import Sensores

from .dobles_mqtt import BrokerFalso

T0 = 1000.0


class Reloj:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class Entorno:
    def __init__(self, tmp_path, modo="sim", umbrales=None, cargador=None):
        self.reloj = Reloj()
        self.hal = HalSim(reloj=self.reloj)
        self.broker = BrokerFalso()
        self.cfg = Config(modo=modo, paro_ruta=str(tmp_path / "paro.json"),
                          umbrales=umbrales or Umbrales(vib_rms_g=1.0, temp_c=60.0),
                          sensores=SensoresCfg(tolerancia_fallo_s=2.0))
        self.svc = Sensores(self.cfg, self.hal, self.broker.cliente(), reloj=self.reloj,
                            ahora=lambda: 1_700_000_000.0 + (self.reloj.t - T0),
                            cargador=cargador or (lambda: self.cfg))
        self.svc.preparar()

    def tick(self, temp=True, acel=True, publicar=True):
        """Un periodo de 10 ms; cada segundo, temperatura y publicación."""
        self.reloj.t = round(self.reloj.t + 0.01, 6)
        if acel:
            self.svc.paso_acel()
        if round(self.reloj.t - T0, 2) % 1.0 == 0:
            if temp:
                self.svc.paso_temp()
            if publicar:
                self.svc.paso_publicar()

    def avanzar(self, segundos, **k):
        for _ in range(round(segundos * 100)):
            self.tick(**k)

    def hasta_paro(self, maximo_s=3.0, **k):
        """Avanza hasta que haya paro; devuelve los segundos que tardó."""
        t0 = self.reloj.t
        while not self.svc.seguridad.activo and self.reloj.t - t0 < maximo_s:
            self.tick(**k)
        return round(self.reloj.t - t0, 2)

    def publicar(self, topico, payload):
        self.broker.publicar(topico, payload, retener=False)

    def inyectar(self, **d):
        self.publicar(topicos.SIM_INYECTAR, d)

    def salidas(self):
        return self.hal.salidas()


@pytest.fixture
def e(tmp_path):
    return Entorno(tmp_path)


# ------------------------------------------------------------------ CU-01 operación normal
def test_arranca_con_la_maquina_en_marcha_y_luz_verde(e):
    s = e.salidas()
    assert s.maquina is True and s.luz == "verde" and s.zumbador is False
    assert e.broker.ultimo(topicos.SEGURIDAD)["activo"] is False
    assert e.broker.ultimo(topicos.SALIDAS)["luz"] == "verde"


def test_publica_lecturas_normales_cada_segundo(e):
    e.avanzar(4)
    lecturas = e.broker.de(topicos.LECTURAS)
    assert len(lecturas) == 4
    ultima = lecturas[-1]
    assert ultima["vib_rms_g"] == pytest.approx(0.10, abs=0.02)   # RMS del vector, el nominal del simulador
    assert 25 < ultima["temp_c"] < 30 and isinstance(ultima["ts"], float)
    assert not e.svc.seguridad.activo


def test_primeras_lecturas_sin_vibracion_son_nulas(e):
    e.svc.paso_publicar()
    assert e.broker.ultimo(topicos.LECTURAS) == {"ts": 1_700_000_000.0, "vib_rms_g": None, "temp_c": None}


# ------------------------------------------------------------------ CU-02 paro por umbral
def test_paro_por_vibracion(e):
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=5)
    espera = e.hasta_paro()
    s = e.salidas()
    assert s.maquina is False and s.luz == "roja" and s.zumbador is True
    seg = e.broker.ultimo(topicos.SEGURIDAD)
    assert seg["activo"] is True and seg["sensor"] == "vibracion" and seg["umbral"] == 1.0
    assert seg["valor"] > 1.0
    assert espera < 1.0, f"el paro tardó {espera} s desde que empezó la falla (REQ-N04)"
    assert e.svc.latencia_paro_ms is not None and e.svc.latencia_paro_ms < 100


def test_paro_por_temperatura(e):
    e.avanzar(2)
    e.inyectar(temp_c=90.0, duracion_s=5)
    e.avanzar(1)                       # la temperatura se lee cada segundo
    seg = e.broker.ultimo(topicos.SEGURIDAD)
    assert seg["activo"] and seg["sensor"] == "temperatura" and seg["valor"] == 90.0
    assert e.salidas().maquina is False and e.salidas().luz == "roja"


def test_la_vibracion_baja_del_umbral_no_libera_el_paro(e):
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=1)
    e.hasta_paro()
    e.avanzar(5)                       # la falla ya terminó
    assert e.svc.seguridad.activo and e.salidas().maquina is False


def test_el_paro_se_guarda_en_disco(e):
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=5)
    e.hasta_paro()
    assert leer_paro(e.cfg.paro_ruta).sensor == "vibracion"


def test_si_el_hardware_no_puede_detener_igual_se_senaliza(e):
    def falla(_):
        raise ErrorHardware("GPIO caído")
    e.hal._escribir_maquina = falla
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=5)
    e.hasta_paro()
    assert e.salidas().luz == "roja" and e.salidas().zumbador is True
    assert e.broker.ultimo(topicos.SEGURIDAD)["activo"] is True


# ------------------------------------------------------------------ paro retenido (invariante 2)
def paro_por_vibracion(e):
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=1)
    e.hasta_paro()
    e.avanzar(2)                       # la falla expira


def test_retenido_ignora_ordenes_de_luz_y_zumbador(e):
    paro_por_vibracion(e)
    e.publicar(topicos.CMD_SENAL, {"luz": "verde", "zumbador": False, "oled": ["hola"]})
    s = e.salidas()
    assert s.luz == "roja" and s.zumbador is True and s.oled[0] == "PARO"


@pytest.mark.parametrize("orden", [
    {"accion": "reiniciar", "origen": "core"},     # el core/modelo jamás arranca la máquina
    {"accion": "reiniciar", "origen": "otro"},
    {"accion": "reiniciar"},
    {"accion": "arrancar", "origen": "web"},
    {"origen": "web"},
])
def test_retenido_ignora_reinicios_no_autorizados(e, orden):
    paro_por_vibracion(e)
    e.publicar(topicos.CMD_MAQUINA, orden)
    assert e.svc.seguridad.activo and e.salidas().maquina is False


def test_reinicio_con_origen_web_libera(e):
    paro_por_vibracion(e)
    e.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    s = e.salidas()
    assert s.maquina is True and s.luz == "verde" and s.zumbador is False
    assert e.broker.ultimo(topicos.SEGURIDAD)["activo"] is False
    assert leer_paro(e.cfg.paro_ruta) is None
    e.avanzar(3)
    assert not e.svc.seguridad.activo   # las muestras viejas no provocan otro paro


def test_reinicio_con_la_falla_aun_presente_vuelve_a_parar(e):
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=60)
    e.hasta_paro()
    e.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    e.hasta_paro()
    assert e.svc.seguridad.activo and e.salidas().maquina is False


def test_el_paro_sobrevive_a_un_reinicio_del_servicio(e, tmp_path):
    paro_por_vibracion(e)
    nuevo = Entorno(tmp_path)          # mismo paro_ruta: el servicio "se cayó y volvió"
    s = nuevo.salidas()
    assert nuevo.svc.seguridad.activo and s.maquina is False and s.luz == "roja"
    assert nuevo.broker.ultimo(topicos.SEGURIDAD)["activo"] is True
    nuevo.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    assert nuevo.salidas().maquina is True


# ------------------------------------------------------------------ parar por orden (core / web)
def test_parar_por_el_core_detiene_sin_retener(e):
    e.avanzar(1)
    e.publicar(topicos.CMD_MAQUINA, {"accion": "parar", "origen": "core"})
    assert e.salidas().maquina is False and not e.svc.seguridad.activo and e.svc.parada_manual
    e.publicar(topicos.CMD_SENAL, {"luz": "roja", "zumbador": True})   # el core señaliza
    assert e.salidas().luz == "roja"
    e.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    assert e.salidas().maquina is True and not e.svc.parada_manual


def test_parar_con_origen_desconocido_se_ignora(e):
    e.publicar(topicos.CMD_MAQUINA, {"accion": "parar", "origen": "intruso"})
    assert e.salidas().maquina is True


def test_senales_del_core_cuando_no_hay_paro(e):
    e.publicar(topicos.CMD_SENAL, {"luz": "amarilla", "zumbador": True, "oled": ["Revisión", "manual"]})
    s = e.salidas()
    assert s.luz == "amarilla" and s.zumbador is True and s.oled == ("Revisión", "manual")
    assert e.broker.ultimo(topicos.SALIDAS)["luz"] == "amarilla"


@pytest.mark.parametrize("payload", [{"luz": "azul"}, {"zumbador": "si"}, {"oled": "no es lista"}, {}])
def test_senales_invalidas_se_ignoran(e, payload):
    antes = e.salidas()
    e.publicar(topicos.CMD_SENAL, payload)
    assert e.salidas() == antes


# ------------------------------------------------------------------ falla de sensor (D13)
def test_mpu_caido_detiene_tras_la_tolerancia(e):
    def falla():
        raise ErrorHardware("Remote I/O error")
    e.hal.leer_acel = falla
    e.avanzar(1.9)
    assert not e.svc.seguridad.activo
    espera = e.hasta_paro()
    seg = e.broker.ultimo(topicos.SEGURIDAD)
    assert seg["activo"] and seg["sensor"] == "mpu6050_fallo" and seg["umbral"] == 2.0
    assert e.salidas().maquina is False and e.salidas().luz == "roja"
    assert espera < 1.0


def test_ds18b20_caido_detiene(e):
    def falla():
        raise ErrorHardware("no hay DS18B20")
    e.hal.leer_temp = falla
    e.avanzar(3.5)
    assert e.broker.ultimo(topicos.SEGURIDAD)["sensor"] == "ds18b20_fallo"
    assert e.salidas().maquina is False


def test_sensor_colgado_tambien_se_detecta(e):
    e.avanzar(1)
    e.avanzar(3, temp=False)           # el hilo de temperatura dejó de responder
    assert e.svc.seguridad.activo and e.svc.seguridad.causa.sensor == "ds18b20_fallo"


def test_una_falla_breve_se_tolera(e):
    original = e.hal.leer_acel
    estado = {"mal": False}

    def intermitente():
        if estado["mal"]:
            raise ErrorHardware("glitch")
        return original()
    e.hal.leer_acel = intermitente
    e.avanzar(2)
    estado["mal"] = True
    e.avanzar(1.5)                     # menos que la tolerancia
    estado["mal"] = False
    e.avanzar(5)
    assert not e.svc.seguridad.activo and e.salidas().maquina is True


def test_sin_sensores_el_reinicio_vuelve_a_parar(e):
    def falla():
        raise ErrorHardware("x")
    e.hal.leer_acel = falla
    e.hasta_paro(maximo_s=5)
    e.publicar(topicos.CMD_MAQUINA, {"accion": "reiniciar", "origen": "web"})
    e.hasta_paro(maximo_s=5)
    assert e.svc.seguridad.activo


# ------------------------------------------------------------------ modo sim seguro (D11)
def test_sim_inyectar_se_ignora_fuera_del_modo_sim(tmp_path):
    e = Entorno(tmp_path, modo="rpi")
    e.avanzar(2)
    e.inyectar(vib_g=5.0, duracion_s=10)    # nadie está suscrito
    e.svc._on_inyectar(topicos.SIM_INYECTAR, {"vib_g": 5.0, "duracion_s": 10})   # ni siquiera a mano
    e.avanzar(3)
    assert not e.svc.seguridad.activo and e.salidas().maquina is True
    assert e.broker.ultimo(topicos.LECTURAS)["vib_rms_g"] < 0.5


@pytest.mark.parametrize("d", [
    {"vib_g": "mucho"}, {"vib_g": -1}, {"vib_g": True}, {"duracion_s": 0}, {"duracion_s": -3},
    {"vib_g": 2.0, "duracion_s": "5"}, {"temp_c": [1]}, {"vib_g": float("inf")},
])
def test_sim_inyectar_invalido_se_ignora(e, d):
    e.avanzar(2)
    e.inyectar(**d)
    e.avanzar(3)
    assert not e.svc.seguridad.activo


# ------------------------------------------------------------------ recarga de umbrales (CU-07)
def test_recargar_cambia_los_umbrales_sin_reiniciar(tmp_path):
    nueva = Config(umbrales=Umbrales(vib_rms_g=5.0, temp_c=60.0))
    e = Entorno(tmp_path, cargador=lambda: nueva)
    e.avanzar(2)
    e.publicar(topicos.CMD_RECARGAR, {})
    e.inyectar(vib_g=2.0, duracion_s=3)
    e.avanzar(4)
    assert not e.svc.seguridad.activo        # 2 g ya no supera el nuevo umbral de 5 g
    e.inyectar(vib_g=8.0, duracion_s=3)
    e.hasta_paro()
    assert e.svc.seguridad.causa.umbral == 5.0


def test_recarga_invalida_conserva_los_umbrales(tmp_path):
    def mala():
        raise ErrorConfig("archivo roto")
    e = Entorno(tmp_path, cargador=mala)
    e.publicar(topicos.CMD_RECARGAR, {})
    assert e.svc.seguridad.umbrales.vib_rms_g == 1.0


# ------------------------------------------------------------------ MQTT
def test_salidas_se_publica_en_cada_cambio(e):
    n = len(e.broker.de(topicos.SALIDAS))
    e.publicar(topicos.CMD_SENAL, {"luz": "amarilla"})
    assert len(e.broker.de(topicos.SALIDAS)) == n + 1
    ultimo = e.broker.ultimo(topicos.SALIDAS)
    assert set(ultimo) == {"ts", "maquina", "luz", "zumbador", "oled"}
    assert e.broker.retenidos[topicos.SALIDAS] == ultimo


def test_republica_los_retenidos_al_reconectar(e):
    e.broker.retenidos.clear()
    e.svc.mqtt.conectar()                    # simula la reconexión: dispara al_conectar
    assert topicos.SEGURIDAD in e.broker.retenidos and topicos.SALIDAS in e.broker.retenidos


def test_la_perdida_de_mqtt_no_impide_el_paro(e):
    e.svc.mqtt.publicar = lambda *a, **k: False      # broker caído
    e.avanzar(2)
    e.inyectar(vib_g=2.0, duracion_s=5)
    e.hasta_paro()
    assert e.salidas().maquina is False and e.salidas().luz == "roja"


def test_panel_ajusta_la_vibracion_y_dispara_el_paro(e):
    e.avanzar(1)
    e.broker.publicar(topicos.SIM_AJUSTAR, {"vib_g": 2.0})
    e.avanzar(2)
    assert e.svc.seguridad.causa.sensor == "vibracion"


def test_panel_sensor_desconectado_dispara_d13(e):
    e.avanzar(1)
    e.broker.publicar(topicos.SIM_AJUSTAR, {"ds18b20_ok": False})
    e.avanzar(4)
    assert e.svc.seguridad.causa.sensor == "ds18b20_fallo"


def test_panel_con_valor_invalido_se_ignora(e):
    e.avanzar(1)
    e.broker.publicar(topicos.SIM_AJUSTAR, {"vib_g": 99})
    e.avanzar(2)
    assert not e.svc.seguridad.activo


def test_panel_se_ignora_fuera_del_modo_sim(tmp_path):
    e = Entorno(tmp_path, modo="rpi")
    e.avanzar(2)
    e.broker.publicar(topicos.SIM_AJUSTAR, {"vib_g": 2.0})
    e.svc._on_ajustar(topicos.SIM_AJUSTAR, {"vib_g": 2.0})     # ni siquiera a mano
    e.avanzar(3)
    assert not e.svc.seguridad.activo
