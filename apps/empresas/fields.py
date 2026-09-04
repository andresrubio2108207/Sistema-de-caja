"""Cifrado de campos en reposo (credenciales de Siigo).

Se implementa a mano con ``cryptography`` (Fernet/AES) en vez de una
librería de terceros tipo django-cryptography: Django 6.0 es muy reciente y
no queríamos apostar la compatibilidad de un campo crítico a que un paquete
externo ya la soporte. Es poco código y queda bajo nuestro control.

La clave sale de ``FIELD_ENCRYPTION_KEY`` (.env) — nunca del código.
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY)


class EncryptedTextField(models.TextField):
    """Se guarda cifrado en la base de datos; se lee/escribe como texto
    plano en Python — transparente para el resto del código.

    ``TextField`` (no ``CharField``) a propósito: el texto cifrado es más
    largo que el original (~1.3x + relleno fijo de Fernet), así que un
    ``max_length`` corto se desbordaría. Si se necesita acotar el texto
    plano, se hace con un ``validators=[MaxLengthValidator(...)]`` explícito
    en el campo del modelo (valida ANTES de cifrar).
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Dato de antes de activar el cifrado (o clave distinta): se
            # devuelve tal cual en vez de reventar la vista.
            return value
