from .base import DUENO, RolRequerido


class GestionUsuarios(RolRequerido):
    """Alta/baja de personal de la empresa. Solo el dueño."""

    roles_lectura = (DUENO,)
    roles_escritura = (DUENO,)
