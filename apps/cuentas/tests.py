from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.empresas.models import Empresa

from .models import Usuario


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


class PermisosPorRolTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
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

        # de verdad está cifrado en la base, no solo oculto en la respuesta
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT siigo_api_access_key FROM empresas_empresa WHERE id=%s",
                [self.empresa.pk],
            )
            crudo = cursor.fetchone()[0]
        self.assertNotEqual(crudo, "secreto-siigo")
        self.assertNotIn("secreto-siigo", crudo)

    def test_alerta_resolucion_por_vencer(self):
        from datetime import date, timedelta

        self.auth(self.token_dueno)
        self.empresa.resolucion_vigencia_hasta = date.today() + timedelta(days=10)
        self.empresa.save(update_fields=["resolucion_vigencia_hasta"])
        resp = self.client.get(reverse("mi-empresa"))
        self.assertTrue(resp.data["resolucion_por_vencer"])
        self.assertEqual(resp.data["dias_para_vencer_resolucion"], 10)

        self.empresa.resolucion_vigencia_hasta = date.today() + timedelta(days=90)
        self.empresa.save(update_fields=["resolucion_vigencia_hasta"])
        resp = self.client.get(reverse("mi-empresa"))
        self.assertFalse(resp.data["resolucion_por_vencer"])

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
