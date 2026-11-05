SUMMARY = "Modelo de decisión tev1:0.8b precargado para Ollama"
DESCRIPTION = "Copia el modelo tev1:0.8b dentro de la imagen para que la \
estación funcione sin Internet desde el primer arranque (REQ-N03). \
El archivo se genera en la máquina de desarrollo con scripts/empacar-modelo.sh."
LICENSE = "CLOSED"

# Generado por scripts/empacar-modelo.sh (no se sube a git: pesa ~1 GB)
SRC_URI = "file://tev1-0.8b-models.tar.gz;subdir=modelo"

S = "${WORKDIR}/modelo"

require ollama-user.inc

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}/var/lib/ollama/models
    cp -R --no-preserve=ownership ${S}/models/. ${D}/var/lib/ollama/models/
    chown -R ollama:ollama ${D}/var/lib/ollama
}

FILES:${PN} = "/var/lib/ollama"
RDEPENDS:${PN} = "ollama-bin"

# Son datos (pesos del modelo), no código para una arquitectura
inherit allarch
