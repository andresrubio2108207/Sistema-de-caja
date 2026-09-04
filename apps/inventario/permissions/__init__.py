from apps.cuentas.permissions import DUENO, SUPERVISOR, RolRequerido


class GestionCatalogo(RolRequerido):
    """Productos y categorías. Escriben dueño y supervisor; los tres leen."""

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR)


class GestionInventario(RolRequerido):
    """Movimientos de inventario (entrada/ajuste/devolución/salida).

    Los escriben dueño y supervisor; los tres roles leen el kardex.
    El movimiento de tipo ``venta`` no se crea por API: lo genera el flujo
    de ventas.
    """

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR)


__all__ = ["GestionCatalogo", "GestionInventario"]
