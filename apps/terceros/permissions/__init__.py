from apps.cuentas.permissions import DUENO, SUPERVISOR, RolRequerido


class GestionClientes(RolRequerido):
    """Terceros. Alta la hacen dueño y supervisor; el cajero solo consulta."""

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR)


__all__ = ["GestionClientes"]
