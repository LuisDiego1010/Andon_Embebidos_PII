# Entorno de desarrollo (F0)

Revisión de la PC de desarrollo contra la lista de la fase F0 de `docs/plan.md`.
La revisión se hizo en modo lectura (sin `sudo`); lo que falta se instala con los
comandos de la sección [Instalación pendiente](#instalación-pendiente).

- **Fecha de revisión:** 2026-11-04
- **Equipo:** HP EliteBook 735 G6
- **Estado general:** ✅ completo — todos los elementos verificados el 2026-11-04,
  después de la instalación (ver [Verificación posterior](#verificación-posterior)).

Leyenda: ✅ cumple · ❌ falta o no cumple · ⚠️ cumple con observaciones · ⏳ por verificar

## Sistema

| Elemento | Requerido | Encontrado | Estado |
|---|---|---|---|
| Sistema operativo | Ubuntu | Ubuntu 26.04 LTS (resolute), núcleo 7.0.0-38-generic | ✅ |
| Arquitectura | x86_64 | x86_64 | ✅ |
| CPU / núcleos | — | AMD Ryzen 7 PRO 3700U, 8 hilos, AMD-V | ✅ |
| KVM | — (no se usa para aarch64) | `/dev/kvm` accesible por ACL para `etencio` | ✅ |
| RAM | — | 12 GiB + 4 GiB swap (≈ 4,3 GiB disponibles al revisar) | ⚠️ ver obs. 1 |
| Espacio libre | ≥ 20 GB | 158 GB libres en `/` (incluye `/var/lib/docker`) | ✅ |
| Python del anfitrión | — (la app corre en Docker con 3.12) | Python 3.14.4 | ⚠️ ver obs. 2 |

## Herramientas

| Componente | Requerido | Encontrado | Estado |
|---|---|---|---|
| git | cualquiera reciente | 2.53.0 | ✅ |
| Docker Engine | ≥ 24 | 29.8.0 (docker-ce, servicio activo) | ✅ |
| Docker Compose | plugin v2 (`docker compose`) | 5.5.1 (`docker-compose-plugin`, arquitectura V2) | ✅ |
| Buildx | instalado | 0.37.0 | ✅ |
| Usuario en grupo `docker` | sí | sí (`973(docker)`) | ✅ |
| Emulación arm64 (binfmt) | `docker run --platform linux/arm64 alpine uname -m` → `aarch64` | `qemu-user-binfmt` 10.2.1, banderas `POF`; devuelve `aarch64` | ✅ |
| `qemu-system-aarch64` | ≥ 8.2 | 10.2.1 (`qemu-system-arm`) | ✅ |
| `qemu-utils` | instalado | 10.2.1 | ✅ |
| `qemu-efi-aarch64` | instalado | 2025.11 | ✅ |
| `cloud-image-utils` | instalado (`cloud-localds`) | 0.33 | ✅ |
| `mosquitto-clients` | instalado | 2.0.22 | ✅ |
| curl | instalado | 8.18.0 | ✅ |
| make | instalado | 4.4.1 | ✅ |
| Cliente SSH | instalado | OpenSSH 10.2p1 | ✅ |
| Grabación de SD | `rpi-imager` o `bmaptool` | `bmaptool` 3.9.0 y `rpi-imager` 1.8.5 | ✅ |

## Imágenes base de Docker

| Imagen | Uso | Encontrado | Estado |
|---|---|---|---|
| `python:3.12-slim` | contenedor `dev` (niveles 1 y 2) | amd64 y arm64 (Python 3.12.16) | ✅ |
| `ollama/ollama` | modelo `tev1:0.8b` (nivel 1) | `latest`, 8,47 GB | ✅ |
| `eclipse-mosquitto:2` | broker MQTT local | 41,8 MB | ✅ |
| `alpine` (arm64) | prueba de binfmt | `latest` | ✅ |

## Observaciones

1. **Memoria.** Al revisar había 8,5 GiB en uso, en parte por los contenedores de
   Jenkins (`jenkins-validador`, `buildx_buildkit_embedded-builder0`). Con Ollama,
   el contenedor `dev`, Mosquitto y una VM de QEMU (2 GiB) se puede quedar corto.
   Conviene detener Jenkins al trabajar en los niveles 1 y 3:
   `docker stop jenkins-validador`.
2. **Python 3.14 en el anfitrión.** La plataforma objetivo es Python 3.12 y las
   pruebas corren en `python:3.12-slim`, así que no se instala nada. Regla: no usar
   funciones de Python posteriores a 3.12 en `app/`.
3. **Puerto 8080 ocupado** por Jenkins. `andon-web` no debe publicar en 8080 en la
   PC de desarrollo; se usa 5000 (Flask por defecto). Libres al revisar: 1883 y 11434.
4. **QEMU sin aceleración.** KVM solo acelera huéspedes x86; la VM arm64 corre en
   emulación (TCG) y será lenta. Basta para validar systemd e instalador (nivel 3),
   no para medir latencias (eso es nivel 4, en la placa).
5. **`qemu-user-static` ya no existe** en Ubuntu 26.04: lo reemplaza
   `qemu-user-binfmt`, que registra los intérpretes en `binfmt_misc` al arrancar.
   Para que funcione dentro de Docker, el registro debe tener la bandera `F`
   (se verifica abajo).
6. **`qemu-system-aarch64`** no es un paquete aparte: lo trae `qemu-system-arm`.
7. **`rpi-imager`** de Ubuntu (1.8.5) es antiguo pero sirve para preconfigurar
   Raspberry Pi OS (usuario, SSH, Wi-Fi). `bmaptool` es suficiente para grabar
   imágenes `.wic` de Yocto. Se instalan ambos.
8. **Builder de Buildx en contenedor sin DNS (2026-11-04).** `embedded-builder` (driver
   `docker-container`) usa el DNS 172.21.16.7, que no responde, y `docker compose build`
   falla al resolver `registry-1.docker.io`. Solución: usar el builder `default`, que toma
   la imagen local: `BUILDX_BUILDER=default docker compose -f docker/compose.yaml up -d --build`.
   No se cambió la configuración del builder.

## Instalación realizada

Comandos ejecutados por el usuario (requieren `sudo`):

```bash
sudo apt update
sudo apt install -y qemu-system-arm qemu-efi-aarch64 qemu-user-binfmt \
    cloud-image-utils mosquitto-clients bmap-tools rpi-imager
```

Sin `sudo` (descarga de imágenes, ≈ 4–5 GB):

```bash
docker pull python:3.12-slim
docker pull ollama/ollama
docker pull eclipse-mosquitto:2
```

Si después de instalar `qemu-user-binfmt` la prueba de arm64 falla (registro sin la
bandera `F`), alternativa sin `sudo`, no persiste al reiniciar:

```bash
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

## Verificación posterior

Ejecutada el 2026-11-04 después de la instalación.

| Comprobación | Esperado | Resultado | Estado |
|---|---|---|---|
| `qemu-system-aarch64 --version` | ≥ 8.2 | 10.2.1 | ✅ |
| `ls /usr/share/qemu-efi-aarch64/QEMU_EFI.fd` | existe | existe | ✅ |
| `cat /proc/sys/fs/binfmt_misc/qemu-aarch64` | `enabled`, banderas con `F` | `enabled`, `POF` | ✅ |
| `docker run --rm --platform linux/arm64 alpine uname -m` | `aarch64` | `aarch64` | ✅ |
| `docker buildx ls` | incluye `linux/arm64` | sí | ✅ |
| `cloud-localds --help` | disponible | `/usr/bin/cloud-localds` | ✅ |
| `mosquitto_pub --help` | versión 2.x | 2.0.22 | ✅ |
| `bmaptool --version` | disponible | 3.9.0 | ✅ |
| `rpi-imager --version` | disponible | 1.8.5 | ✅ |
| `docker images` | `python:3.12-slim`, `ollama/ollama`, `eclipse-mosquitto:2` | las tres presentes | ✅ |
| `docker run --rm --platform linux/arm64 python:3.12-slim python -V` | `Python 3.12.x` en aarch64 | Python 3.12.16, aarch64 | ✅ |
