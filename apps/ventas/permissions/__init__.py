from apps.cuentas.permissions import DUENO, SUPERVISOR, RolRequerido


class GestionNotasCredito(RolRequerido):
    """Devoluciones (nota crédito) — ajuste de dinero e inventario, back
    office. Dueño y supervisor; el cajero no las emite ni las consulta."""

    roles_lectura = (DUENO, SUPERVISOR)
    roles_escritura = (DUENO, SUPERVISOR)


class VerReportes(RolRequerido):
    """Reportes que exponen desempeño por persona (ventas por cajero) o
    consolidados de negocio (productos más vendidos). Dueño y supervisor;
    el cajero no ve el detalle de sus compañeros."""

    roles_lectura = (DUENO, SUPERVISOR)
    roles_escritura = ()


__all__ = ["GestionNotasCredito", "VerReportes"]
