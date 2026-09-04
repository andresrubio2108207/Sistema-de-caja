"""Base de permisos por rol (dueño / supervisor / cajero) — compartida por
TODOS los dominios. Los permisos propios de cada dominio (ej. catálogo,
inventario, caja, ventas) viven en el ``permissions/`` de su propia app y
heredan de ``RolRequerido`` definida aquí.

Uso en un ViewSet::

    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionCatalogo]
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from ..models import Usuario

DUENO = Usuario.Rol.DUENO
SUPERVISOR = Usuario.Rol.SUPERVISOR
CAJERO = Usuario.Rol.CAJERO


class TieneEmpresaActiva(BasePermission):
    """El usuario debe pertenecer a una empresa y esa empresa estar activa.

    El superusuario de plataforma (sin empresa) siempre pasa.
    """

    message = "Tu usuario no está asociado a una empresa activa."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser and user.empresa_id is None:
            return True
        return bool(user.empresa_id and user.empresa.activa)


class RolRequerido(BasePermission):
    """Base: define ``roles_lectura`` y ``roles_escritura`` en las subclases.

    ``roles_lectura = None`` => cualquier rol autenticado puede leer.
    """

    roles_lectura = None
    roles_escritura = ()
    message = "Tu rol no tiene permiso para esta acción."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        rol = getattr(user, "rol", None)
        if request.method in SAFE_METHODS:
            return self.roles_lectura is None or rol in self.roles_lectura
        return rol in self.roles_escritura


class OperacionCaja(RolRequerido):
    """Abrir/cerrar turnos (app caja) y registrar ventas (app ventas). Los
    tres roles operan — vive aquí, no en caja/ventas, porque lo usan las
    dos apps."""

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR, CAJERO)
