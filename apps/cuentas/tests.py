from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.empresas.models import Empresa

from .models import Usuario


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


class OnboardingTests(APITestCase):
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


class LoginTests(APITestCase):
    def setUp(self):
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


class PermisosPorRolTests(APITestCase):
    def setUp(self):
        r = self.client.post(
            reverse("onboarding"), payload_onboarding(), format="json"
        )
        self.empresa = Empresa.objects.get(nit="900111222")
        self.dueno = Usuario.objects.get(username="duena")
        self.token_dueno = r.data["access"]

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def login(self, username, password="Clave-Segura-123"):
        return self.client.post(
            reverse("token_obtain_pair"),
            {"username": username, "password": password},
            format="json",
        ).data["access"]

    def test_dueno_crea_supervisor_y_cajero(self):
        self.auth(self.token_dueno)
        for username, rol in [("sup", "supervisor"), ("caj", "cajero")]:
            resp = self.client.post(
                reverse("usuario-list"),
                {
                    "username": username,
                    "email": f"{username}@acme.co",
                    "password": "Clave-Segura-123",
                    "rol": rol,
                },
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
            self.assertEqual(Usuario.objects.get(username=username).empresa, self.empresa)

    def test_cajero_no_puede_crear_usuarios(self):
        self.auth(self.token_dueno)
        self.client.post(
            reverse("usuario-list"),
            {
                "username": "caj",
                "email": "caj@acme.co",
                "password": "Clave-Segura-123",
                "rol": "cajero",
            },
            format="json",
        )
        self.auth(self.login("caj"))
        resp = self.client.post(
            reverse("usuario-list"),
            {"username": "x", "email": "x@acme.co", "password": "Clave-Segura-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_no_accede_a_mi_empresa(self):
        self.auth(self.token_dueno)
        self.client.post(
            reverse("usuario-list"),
            {
                "username": "sup",
                "email": "sup@acme.co",
                "password": "Clave-Segura-123",
                "rol": "supervisor",
            },
            format="json",
        )
        self.auth(self.login("sup"))
        self.assertEqual(
            self.client.get(reverse("mi-empresa")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_dueno_carga_credenciales_siigo_y_no_se_devuelven(self):
        self.auth(self.token_dueno)
        resp = self.client.patch(
            reverse("mi-empresa"),
            {
                "siigo_api_username": "acme@siigo.com",
                "siigo_api_access_key": "secreto-siigo",
                "resolucion_prefijo": "SETP",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertNotIn("siigo_api_access_key", resp.data)
        self.assertTrue(resp.data["siigo_configurado"])
        self.empresa.refresh_from_db()
        self.assertEqual(self.empresa.siigo_api_access_key, "secreto-siigo")

    def test_aislamiento_usuarios_entre_empresas(self):
        # Segunda empresa
        self.client.credentials()
        r2 = self.client.post(
            reverse("onboarding"),
            payload_onboarding(nit="900999888", username="duenb", email="b@beta.co"),
            format="json",
        )
        self.auth(r2.data["access"])
        resp = self.client.get(reverse("usuario-list"))
        usernames = {u["username"] for u in resp.data["results"]}
        self.assertEqual(usernames, {"duenb"})
        self.assertNotIn("duena", usernames)
