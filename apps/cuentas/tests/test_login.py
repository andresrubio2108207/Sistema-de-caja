from django.urls import reverse
from rest_framework import status

from apps.empresas.models import Empresa

from ..models import Usuario
from .base import BaseAPITestCase, payload_onboarding


class LoginTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.client.post(reverse("onboarding"), payload_onboarding(), format="json")

    def test_login_devuelve_usuario_y_tokens(self):
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "duena", "password": "Clave-Segura-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertEqual(resp.data["usuario"]["rol"], Usuario.Rol.DUENO)

    def test_login_empresa_inactiva_rechazado(self):
        Empresa.objects.filter(nit="900111222").update(activa=False)
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "duena", "password": "Clave-Segura-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_requiere_token(self):
        self.assertEqual(
            self.client.get(reverse("me")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
