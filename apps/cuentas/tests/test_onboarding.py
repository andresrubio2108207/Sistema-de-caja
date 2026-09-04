from django.urls import reverse
from rest_framework import status

from apps.empresas.models import Empresa

from ..models import Usuario
from .base import BaseAPITestCase, payload_onboarding


class OnboardingTests(BaseAPITestCase):
    def test_crea_empresa_dueno_y_devuelve_tokens(self):
        resp = self.client.post(
            reverse("onboarding"), payload_onboarding(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["usuario"]["rol"], Usuario.Rol.DUENO)
        self.assertEqual(resp.data["usuario"]["empresa"]["nit"], "900111222")

        empresa = Empresa.objects.get(nit="900111222")
        dueno = Usuario.objects.get(username="duena")
        self.assertEqual(dueno.empresa, empresa)
        self.assertEqual(dueno.rol, Usuario.Rol.DUENO)
        self.assertTrue(dueno.check_password("Clave-Segura-123"))

    def test_nit_duplicado_rechazado(self):
        self.client.post(reverse("onboarding"), payload_onboarding(), format="json")
        resp = self.client.post(
            reverse("onboarding"),
            payload_onboarding(username="otra", email="otra@acme.co"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Empresa.objects.count(), 1)
        self.assertEqual(Usuario.objects.filter(username="otra").count(), 0)

    def test_password_debil_rechazado(self):
        data = payload_onboarding()
        data["usuario"]["password"] = "123"
        resp = self.client.post(reverse("onboarding"), data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Empresa.objects.count(), 0)
