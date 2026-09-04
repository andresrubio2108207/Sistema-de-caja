"""Helpers compartidos por los tests de cuentas (no es un módulo de tests en
sí — no matchea el patrón ``test*.py`` a propósito, para que el discovery de
Django no intente coleccionarlo aparte)."""
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.empresas.models import Empresa


class BaseAPITestCase(APITestCase):
    """Limpia el cache de throttling entre tests: onboarding/login tienen
    límite de tasa (ver settings) y el cache no se resetea solo entre tests."""

    def setUp(self):
        cache.clear()


def payload_onboarding(nit="900111222", username="duena", email="duena@acme.co"):
    return {
        "empresa": {
            "razon_social": "ACME SAS",
            "nit": nit,
            "digito_verificacion": "3",
            "regimen_tributario": Empresa.Regimen.RESPONSABLE_IVA,
        },
        "usuario": {
            "username": username,
            "email": email,
            "password": "Clave-Segura-123",
        },
    }
