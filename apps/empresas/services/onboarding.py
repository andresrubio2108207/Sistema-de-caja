"""Alta de una empresa nueva (tenant) + su usuario dueño.

Extraído de ``OnboardingSerializer.create()`` (antes vivía ahí) al
reorganizar en capas — mismo comportamiento exacto, misma transacción.
"""
from django.db import transaction

from apps.cuentas.models import Usuario

from ..models import Empresa


@transaction.atomic
def crear_empresa_y_dueno(*, datos_empresa: dict, datos_usuario: dict) -> dict:
    """Crea la Empresa y su primer Usuario (rol=dueño), en una transacción.

    ``datos_empresa`` / ``datos_usuario`` son los ``validated_data`` de
    ``OnboardingEmpresaSerializer`` / ``OnboardingUsuarioSerializer``.
    """
    empresa = Empresa.objects.create(**datos_empresa)
    usuario = Usuario.objects.create_user(
        username=datos_usuario["username"],
        email=datos_usuario["email"],
        password=datos_usuario["password"],
        first_name=datos_usuario.get("first_name", ""),
        last_name=datos_usuario.get("last_name", ""),
        empresa=empresa,
        rol=Usuario.Rol.DUENO,
    )
    return {"empresa": empresa, "usuario": usuario}
