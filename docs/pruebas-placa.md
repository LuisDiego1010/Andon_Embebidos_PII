# Pruebas en la Raspberry Pi 4 con la imagen Yocto

Guía para llevar la imagen a la placa y comprobar que cumple lo que la app necesita.
Cubre las pruebas de salida de **E1** (imagen base), **E2** (buses y GPIO) y **E3**
(Ollama y modelo), y prepara **E4** (la app sobre la imagen).

No hace falta hardware conectado: sin sensores, las comprobaciones de periféricos salen
como **[AVISO]**, no como fallo.

## 0. Requisitos

- La imagen compilada con los cambios de integración (paso 1).
- Una microSD de 16 GB o más y su lector.
- Un cable de red (Ethernet) para la placa.
- Fuente de 5 V / 3 A para la Pi 4.

## 1. Recompilar la imagen (solo si cambió `meta-andon/` o `andon.yml`)

```bash
cd ~/Documentos/Embebidos/Proyectos/Proyecto_II/Andon_Embebidos_PII
KAS_CONTAINER_ENGINE=podman kas-container build andon.yml 2>&1 | tee compilacion.log
```

Solo recompila lo que cambió: minutos, no horas. La imagen queda en
`build/tmp/deploy/images/raspberrypi4-64/andon-image-raspberrypi4-64.rootfs.wic.bz2`.

## 2. Grabar la microSD

```bash
lsblk                                   # identificar la tarjeta por su tamaño (NO nvme0n1)
sudo umount /dev/sdX*                   # sdX = la tarjeta
cd build/tmp/deploy/images/raspberrypi4-64/
sudo bmaptool copy andon-image-raspberrypi4-64.rootfs.wic.bz2 /dev/sdX
sync
```

## 3. Conectar la placa a la PC

**Opción A · router o switch del laboratorio:** conectar el cable y buscar la IP en el router.

**Opción B · cable directo a la laptop (sin router):**
1. En Ubuntu: Configuración → Red → Cableada → ⚙ → IPv4 → **"Compartida con otros equipos"**.
2. Conectar el cable entre la laptop y la Pi. La laptop le da IP por DHCP (red 10.42.0.x).

Encender la Pi y esperar ~1 minuto. Luego:

```bash
ssh root@raspberrypi4-64.local          # sin contraseña (debug-tweaks, solo desarrollo)
# si .local no resuelve, usar la IP:
ip neigh | grep -i "dc:a6\|e4:5f\|d8:3a\|2c:cf"   # prefijos MAC de Raspberry Pi
```

## 4. Copiar los scripts de prueba

Desde la PC, en la carpeta del repo:

```bash
scp scripts/verificar-imagen.sh scripts/medir-latencia.py scripts/probar-ollama.sh \
    root@raspberrypi4-64.local:/root/
```

## 5. Verificar la imagen (E1, E2, E3)

En la Pi:

```bash
sh verificar-imagen.sh
```

Todo debe salir **[OK]** salvo los periféricos sin conectar (**[AVISO]**). Al final:
`Resumen: N OK · 0 fallos`.

## 6. Medir latencia y exactitud del modelo (REQ-N05, D4)

En la Pi:

```bash
python3 medir-latencia.py --rondas 2
```

Usa el mismo cliente (`andon.core.ollama`) y los mismos 19 reportes que la prueba de
contrato de la PC, así que los números se comparan directamente con
`docs/decisiones/D4-contrato-systemone.md`.

- La primera consulta incluye **cargar el modelo** en memoria y es más lenta; el script
  la mide aparte.
- Deja un `latencia-<fecha>.csv`. Copiarlo a la PC para las evidencias:

```bash
scp root@raspberrypi4-64.local:/root/latencia-*.csv docs/evidencias/
```

## 7. Registrar resultados

Copiar estos datos a la bitácora y pasárselos a Eduardo (afectan el timeout y el umbral
de D4):

| Dato | Valor medido |
| --- | --- |
| Fecha | |
| `verificar-imagen.sh`: OK / fallos / avisos | |
| Carga del modelo + primera consulta (s) | |
| Latencia mediana (ms) | |
| Latencia p90 y máxima (ms) | |
| Exactitud en reportes claros | |
| Claros que irían a amarillo con umbral 0,92 | |
| Ambiguos que irían a amarillo con umbral 0,92 | |
| RAM disponible con el modelo cargado (`free -m`) | |

## 8. Probar la app a mano sobre la imagen (antes de la receta final)

La imagen ya trae el código de `app/src` en `/opt/andon` (receta `andon-app`). Para
probar un cambio sin recompilar, copiarlo encima:

```bash
scp -r app/src/andon root@raspberrypi4-64.local:/opt/andon/
ssh root@raspberrypi4-64.local 'chown -R andon:andon /opt/andon'
```

Correr un módulo como lo haría el servicio:

```bash
sudo -u andon env PYTHONPATH=/opt/andon python3 -m andon.core
```

Los servicios `andon-sensores`, `andon-core` y `andon-web` vienen **desactivados** hasta
que los módulos tengan su `__main__.py`. Para activarlos en la placa:

```bash
systemctl enable --now andon-sensores andon-core andon-web
journalctl -u andon-core -f            # ver qué hace
```

Cuando funcionen, cambiar `SYSTEMD_AUTO_ENABLE = "enable"` en
`meta-andon/recipes-andon/andon-app/andon-app.bb` y recompilar.

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
| --- | --- | --- |
| La Pi no aparece en la red | Sin DHCP o todavía arrancando | Esperar 1–2 min; probar la opción B; consola serial (GPIO 14/15, 115200) |
| `ollama list` vacío | El modelo no entró a la imagen | Revisar que existía `tev1-0.8b-models.tar.gz` al compilar |
| Latencia muy alta en todas | El modelo se descarga de memoria | `OLLAMA_KEEP_ALIVE=-1` en el servicio; revisar `free -m` |
| `[FALLO] no existe /dev/i2c-1` | Falta el módulo i2c-dev | `modprobe i2c-dev`; revisar `config.txt` |
