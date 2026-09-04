from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cuentas.models import Usuario
from apps.empresas.models import Empresa

from ..models import Caja, TurnoCaja


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


class CajaYTurnoTests(APITestCase):
    def setUp(self):
        self.empresa, self.users = crear_empresa("900000001", "a")
        self.caja = Caja.objects.create(empresa=self.empresa, nombre="Caja 1")

    def auth(self, usuario):
        token = self.client.post(
            reverse("token_obtain_pair"),
            {"username": usuario.username, "password": "Clave-Segura-123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def abrir(self, usuario, caja=None, saldo="50000.00"):
        self.auth(usuario)
        return self.client.post(
            reverse("turno-list"),
            {"caja": (caja or self.caja).pk, "saldo_inicial": saldo},
            format="json",
        )

    # --- cajas ---
    def test_solo_dueno_crea_caja(self):
        self.auth(self.users[Usuario.Rol.DUENO])
        self.assertEqual(
            self.client.post(reverse("caja-list"), {"nombre": "Caja 2"}, format="json").status_code,
            status.HTTP_201_CREATED,
        )
        self.auth(self.users[Usuario.Rol.SUPERVISOR])
        self.assertEqual(
            self.client.post(reverse("caja-list"), {"nombre": "Caja 3"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get(reverse("caja-list")).status_code, status.HTTP_200_OK
        )

    def test_no_elimina_caja_con_turnos(self):
        self.abrir(self.users[Usuario.Rol.CAJERO])
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.delete(reverse("caja-detail", args=[self.caja.pk]))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    # --- apertura de turno ---
    def test_cajero_abre_turno(self):
        resp = self.abrir(self.users[Usuario.Rol.CAJERO])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        turno = TurnoCaja.objects.get(pk=resp.data["id"])
        self.assertEqual(turno.cajero, self.users[Usuario.Rol.CAJERO])
        self.assertEqual(turno.estado, TurnoCaja.Estado.ABIERTO)

    def test_no_puede_tener_dos_turnos_abiertos(self):
        otra_caja = Caja.objects.create(empresa=self.empresa, nombre="Caja 2")
        self.abrir(self.users[Usuario.Rol.CAJERO])
        resp = self.abrir(self.users[Usuario.Rol.CAJERO], caja=otra_caja)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_caja_ocupada_no_admite_dos_turnos(self):
        self.abrir(self.users[Usuario.Rol.CAJERO])
        resp = self.abrir(self.users[Usuario.Rol.SUPERVISOR])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- cierre de turno ---
    def test_cajero_cierra_su_turno(self):
        pk = self.abrir(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.auth(self.users[Usuario.Rol.CAJERO])
        resp = self.client.post(
            reverse("turno-cerrar", args=[pk]),
            {"saldo_final_declarado": "50000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["estado"], TurnoCaja.Estado.CERRADO)
        self.assertEqual(resp.data["saldo_final_calculado"], "50000.00")
        self.assertEqual(resp.data["diferencia_caja"], "0.00")

    def test_otro_cajero_no_cierra_turno_ajeno(self):
        pk = self.abrir(self.users[Usuario.Rol.CAJERO]).data["id"]
        otro = Usuario.objects.create_user(
            username="a_cajero2",
            password="Clave-Segura-123",
            empresa=self.empresa,
            rol=Usuario.Rol.CAJERO,
        )
        self.auth(otro)
        resp = self.client.post(
            reverse("turno-cerrar", args=[pk]), {"saldo_final_declarado": "0"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_dueno_puede_cerrar_turno_ajeno(self):
        pk = self.abrir(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.post(
            reverse("turno-cerrar", args=[pk]),
            {"saldo_final_declarado": "50000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_no_se_puede_cerrar_dos_veces(self):
        pk = self.abrir(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.auth(self.users[Usuario.Rol.CAJERO])
        self.client.post(
            reverse("turno-cerrar", args=[pk]), {"saldo_final_declarado": "50000.00"}, format="json"
        )
        resp = self.client.post(
            reverse("turno-cerrar", args=[pk]), {"saldo_final_declarado": "50000.00"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
