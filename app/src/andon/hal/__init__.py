from andon.hal.base import HAL, ErrorHardware, Salidas  # noqa: F401


def crear_hal(cfg):
    """HAL según `cfg.modo`. `rpi` se importa aparte: gpiod y smbus2 solo existen en la placa."""
    if cfg.modo == "sim":
        from andon.hal.sim import HalSim
        return HalSim()
    if cfg.modo == "hibrido":
        from andon.hal.hibrido import HalHibrido
        return HalHibrido(cfg)
    from andon.hal.rpi import HalRpi
    return HalRpi(cfg)
