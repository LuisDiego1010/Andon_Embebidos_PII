SUMMARY = "Ollama: servidor local de modelos (binario oficial arm64)"
DESCRIPTION = "Empaqueta el binario oficial de Ollama para Linux arm64 en vez de \
compilarlo desde Go. Solo se instala el backend de CPU; se descartan las \
bibliotecas CUDA (unos 2,2 GB) porque la Raspberry Pi no las usa."
HOMEPAGE = "https://ollama.com"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# Solo existe binario para arm64
COMPATIBLE_HOST = "aarch64.*-linux"

SRC_URI = " \
    https://github.com/ollama/ollama/releases/download/v${PV}/ollama-linux-arm64.tar.zst;subdir=ollama-${PV};downloadfilename=ollama-linux-arm64-${PV}.tar.zst \
    file://ollama.service \
"
SRC_URI[sha256sum] = "913d9a28da6da86d551ce4ca531457767bb14d511cbc1d5ca93e9b3b8b9a8666"

S = "${WORKDIR}/ollama-${PV}"

require ollama-user.inc
inherit systemd

SYSTEMD_SERVICE:${PN} = "ollama.service"
SYSTEMD_AUTO_ENABLE = "enable"

# No hay nada que compilar: es un binario precompilado
do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    # El binario busca sus bibliotecas en ../lib/ollama
    install -d ${D}${bindir}
    install -m 0755 ${S}/bin/ollama ${D}${bindir}/ollama

    # Solo el backend de CPU: archivos del primer nivel de lib/ollama.
    # Se omiten las carpetas cuda_v12 y cuda_v13.
    install -d ${D}${prefix}/lib/ollama
    for f in ${S}/lib/ollama/*; do
        [ -d "$f" ] && continue
        cp -P "$f" ${D}${prefix}/lib/ollama/
    done

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/ollama.service ${D}${systemd_system_unitdir}/ollama.service

    # Carpeta de datos del servicio
    install -d -m 0755 ${D}/var/lib/ollama
    chown -R ollama:ollama ${D}/var/lib/ollama
}

FILES:${PN} += " \
    ${prefix}/lib/ollama \
    ${systemd_system_unitdir}/ollama.service \
    /var/lib/ollama \
"

# Ajustes para un binario precompilado de terceros:
# - ya viene "stripped" y enlazado con sus propias opciones
# - trae sus propias bibliotecas privadas (libgomp, libomp, libggml...)
#   que no deben registrarse como bibliotecas del sistema
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INHIBIT_SYSROOT_STRIP = "1"
EXCLUDE_FROM_SHLIBS = "1"
INSANE_SKIP:${PN} += "already-stripped ldflags dev-so file-rdeps"

RDEPENDS:${PN} += "libstdc++ libgcc"
