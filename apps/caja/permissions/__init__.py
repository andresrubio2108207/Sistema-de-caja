from apps.cuentas.permissions import DUENO, RolRequerido


class GestionCajas(RolRequerido):
    """Cajas físicas (terminales). Crea/edita el dueño; supervisor y cajero leen."""

    roles_lectura = None
    roles_escritura = (DUENO,)


__all__ = ["GestionCajas"]
