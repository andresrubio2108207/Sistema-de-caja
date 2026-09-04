"""Helper compartido por los tests de ventas (no matchea ``test*.py`` a
propósito, para que el discovery de Django no lo intente coleccionar)."""
from apps.cuentas.models import Usuario
from apps.empresas.models import Empresa


def crear_empresa(nit, prefijo):
    empresa = Empresa.objects.create(
        razon_social=f"Empresa {prefijo}",
        nit=nit,
        digito_verificacion="1",
        regimen_tributario=Empresa.Regimen.RESPONSABLE_IVA,
    )
    usuarios = {
        rol: Usuario.objects.create_user(
            username=f"{prefijo}_{rol}", password="Clave-Segura-123", empresa=empresa, rol=rol
        )
        for rol in (Usuario.Rol.DUENO, Usuario.Rol.SUPERVISOR, Usuario.Rol.CAJERO)
    }
    return empresa, usuarios
