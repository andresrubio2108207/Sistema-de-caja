"""Permisos propios del dominio Empresa. La base compartida (``RolRequerido``,
``TieneEmpresaActiva``, los roles) vive en ``apps.cuentas.permissions`` — se
usa desde aquí, no se duplica."""
from apps.cuentas.permissions import DUENO, RolRequerido


class ConfiguracionEmpresa(RolRequerido):
    """Datos de la empresa: resolución DIAN, credenciales Siigo. Solo el dueño."""

    roles_lectura = (DUENO,)
    roles_escritura = (DUENO,)


__all__ = ["ConfiguracionEmpresa"]
