"""Permisos por rol (dueno / supervisor / cajero).

La lectura del catálogo queda abierta a los tres roles; la escritura se
restringe según la tabla de la sección 7 del prompt maestro.

Uso en un ViewSet::

    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionCatalogo]
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario

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


class ConfiguracionEmpresa(RolRequerido):
    """Datos de la empresa: resolución DIAN, credenciales Siigo. Solo el dueño."""

    roles_lectura = (DUENO,)
    roles_escritura = (DUENO,)


class GestionUsuarios(RolRequerido):
    """Alta/baja de personal de la empresa. Solo el dueño."""

    roles_lectura = (DUENO,)
    roles_escritura = (DUENO,)


class GestionCajas(RolRequerido):
    """Cajas físicas (terminales). Crea/edita el dueño; supervisor y cajero leen."""

    roles_lectura = None
    roles_escritura = (DUENO,)


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


class GestionClientes(RolRequerido):
    """Terceros. Alta la hacen dueño y supervisor; el cajero solo consulta."""

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR)


class OperacionCaja(RolRequerido):
    """Abrir/cerrar turnos y registrar ventas. Los tres roles operan."""

    roles_lectura = None
    roles_escritura = (DUENO, SUPERVISOR, CAJERO)


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
