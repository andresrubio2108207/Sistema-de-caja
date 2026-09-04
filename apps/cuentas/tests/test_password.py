from django.urls import reverse
from rest_framework import status

from ..models import Usuario
from .base import BaseAPITestCase, payload_onboarding


class CambiarPasswordTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        r = self.client.post(reverse("onboarding"), payload_onboarding(), format="json")
        self.access = r.data["access"]
        self.refresh = r.data["refresh"]

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_cambia_password_con_la_actual_correcta(self):
        self.auth(self.access)
        resp = self.client.post(
            reverse("cambiar-password"),
            {"password_actual": "Clave-Segura-123", "password_nueva": "Otra-Clave-Segura-456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        dueno = Usuario.objects.get(username="duena")
        self.assertTrue(dueno.check_password("Otra-Clave-Segura-456"))
        # login con la nueva funciona
        login = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "duena", "password": "Otra-Clave-Segura-456"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_rechaza_si_la_actual_esta_mal(self):
        self.auth(self.access)
        resp = self.client.post(
            reverse("cambiar-password"),
            {"password_actual": "no-es-esta", "password_nueva": "Otra-Clave-Segura-456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Usuario.objects.get(username="duena").check_password("Clave-Segura-123"))

    def test_rechaza_password_nueva_debil(self):
        self.auth(self.access)
        resp = self.client.post(
            reverse("cambiar-password"),
            {"password_actual": "Clave-Segura-123", "password_nueva": "123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requiere_autenticacion(self):
        resp = self.client.post(
            reverse("cambiar-password"),
            {"password_actual": "Clave-Segura-123", "password_nueva": "Otra-Clave-Segura-456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revoca_refresh_tokens_existentes(self):
        self.auth(self.access)
        self.client.post(
            reverse("cambiar-password"),
            {"password_actual": "Clave-Segura-123", "password_nueva": "Otra-Clave-Segura-456"},
            format="json",
        )
        resp = self.client.post(
            reverse("token_refresh"), {"refresh": self.refresh}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
