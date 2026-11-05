# Usuario de sistema con el que corre Ollama.
# Lo comparten ollama-bin y ollama-model-tev1 para que los archivos
# del modelo queden a nombre del mismo usuario.
inherit useradd

USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system ollama"
USERADD_PARAM:${PN} = "--system --gid ollama --home-dir /var/lib/ollama \
                       --no-create-home --shell /sbin/nologin ollama"
