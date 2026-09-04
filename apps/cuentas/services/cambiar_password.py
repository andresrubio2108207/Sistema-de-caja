"""Cambio de contraseña propia. Extraído de ``CambiarPasswordView.post()``
(antes vivía ahí) al reorganizar en capas — mismo comportamiento exacto."""
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def cambiar_password(*, usuario, password_nueva: str) -> None:
    """Cambia la contraseña y revoca TODOS los refresh tokens vigentes del
    usuario (cierra sesión en cualquier otro terminal donde haya quedado
    logueado)."""
    usuario.set_password(password_nueva)
    usuario.save(update_fields=["password"])

    for token in OutstandingToken.objects.filter(user=usuario):
        BlacklistedToken.objects.get_or_create(token=token)
