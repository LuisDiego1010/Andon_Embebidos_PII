from pathlib import Path

import pytest

from andon.common import config, topicos
from andon.common.config import ErrorConfig, cargar

CONF_PLACA = Path(__file__).resolve().parents[2] / "config" / "andon.conf"


def escribir(tmp_path, texto):
    p = tmp_path / "andon.conf"
    p.write_text(texto, encoding="utf-8")
    return str(p)


def test_archivo_ausente_usa_valores_por_defecto(tmp_path):
    c = cargar(str(tmp_path / "no_existe.conf"), entorno={})
    assert c == config.Config()
    assert c.ollama.timeout_s == 45.0 and c.web.puerto == 5000


def test_conf_de_la_placa_es_valido():
    c = cargar(str(CONF_PLACA), entorno={})
    assert c.modo == "rpi"
    assert (c.gpio.maquina, c.gpio.verde, c.gpio.amarilla, c.gpio.roja, c.gpio.zumbador) == (17, 22, 27, 23, 24)
    assert c.i2c.mpu == 0x68 and (c.i2c.pantalla, c.i2c.oled) == ("lcd1602", 0x27)   # D18
    assert c.ollama.umbral_confianza == 0.92 and c.ollama.calentar is True


def test_valores_del_archivo(tmp_path):
    r = escribir(tmp_path, "[general]\nmodo = sim\n[umbrales]\nvib_rms_g = 2.5\n"
                           "[i2c]\nmpu = 0x69\n[ollama]\ncalentar = no\n")
    c = cargar(r, entorno={})
    assert c.modo == "sim" and c.umbrales.vib_rms_g == 2.5
    assert c.umbrales.temp_c == 60.0  # lo no indicado conserva el valor por defecto
    assert c.i2c.mpu == 0x69 and c.ollama.calentar is False


def test_entorno_tiene_prioridad(tmp_path):
    r = escribir(tmp_path, "[general]\nmodo = rpi\n[mqtt]\nhost = a\n")
    c = cargar(r, entorno={"ANDON_MODO": "sim", "ANDON_MQTT_HOST": "mosquitto",
                           "ANDON_OLLAMA_URL": "http://ollama:11434"})
    assert c.modo == "sim" and c.mqtt.host == "mosquitto" and c.mqtt.puerto == 1883
    assert c.ollama.url == "http://ollama:11434"


def test_ruta_desde_andon_conf(tmp_path):
    r = escribir(tmp_path, "[general]\nmodo = sim\n")
    assert cargar(entorno={"ANDON_CONF": r}).modo == "sim"


@pytest.mark.parametrize("texto", [
    "[general]\nmodo = otro\n",
    "[ollama]\numbral_confianza = 1.5\n",
    "[ollama]\ntimeout_s = 0\n",
    "[umbrales]\ntemp_c = -1\n",
    "[gpio]\nverde = 17\n",          # repite el pin de la máquina
    "[gpio]\nroja = 40\n",           # fuera de 0..27
    "[mqtt]\npuerto = 99999\n",
    "[sensores]\ntolerancia_fallo_s = 0\n",
    "[umbrales]\nvib_rms_g = mucho\n",  # no numérico
    "[ollama]\ncalentar = quizás\n",
    "esto no es ini",
])
def test_valores_invalidos(tmp_path, texto):
    with pytest.raises(ErrorConfig):
        cargar(escribir(tmp_path, texto), entorno={})


def test_puerto_mqtt_de_entorno_invalido(tmp_path):
    with pytest.raises(ErrorConfig):
        cargar(str(tmp_path / "x"), entorno={"ANDON_MQTT_PUERTO": "abc"})


def test_topicos_con_prefijo():
    assert topicos.LECTURAS == "andon/e1/lecturas"
    assert topicos.CMD_MAQUINA == "andon/e1/cmd/maquina"
    assert topicos.SIM_INYECTAR == "andon/e1/sim/inyectar"
    assert topicos.SIM_AJUSTAR == "andon/e1/sim/ajustar"
    assert topicos.SALIDAS == "andon/e1/salidas"
    assert topicos.RETENIDOS == {topicos.SEGURIDAD, topicos.ESTADO, topicos.SALIDAS}
    todos = [v for k, v in vars(topicos).items() if isinstance(v, str) and v.startswith(topicos.PREFIJO) and k != "PREFIJO"]
    assert len(todos) == len(set(todos)) == 11


def test_sensores_y_ruta_del_paro(tmp_path):
    r = escribir(tmp_path, "[general]\nparo_ruta = /tmp/p.json\n[sensores]\ntolerancia_fallo_s = 3.5\n")
    c = cargar(r, entorno={})
    assert c.sensores.tolerancia_fallo_s == 3.5 and c.paro_ruta == "/tmp/p.json"
    assert cargar(r, entorno={"ANDON_PARO_RUTA": "/x/y.json"}).paro_ruta == "/x/y.json"
    assert cargar(r, entorno={"ANDON_DB_RUTA": "/x/a.db"}).db_ruta == "/x/a.db"
    assert config.Config().sensores.tolerancia_fallo_s == 2.0
