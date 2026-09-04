from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.empresas.models import Empresa
from apps.terceros.models import Cliente
from apps.ventas.models import Venta


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


class ClienteTests(APITestCase):
    def setUp(self):
        self.empresa_a, self.users_a = crear_empresa("900000001", "a")
        self.empresa_b, self.users_b = crear_empresa("900000002", "b")

    def auth(self, usuario):
        token = self.client.post(
            reverse("token_obtain_pair"),
            {"username": usuario.username, "password": "Clave-Segura-123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def crear_cliente(self, usuario, **extra):
        self.auth(usuario)
        body = {
            "tipo_documento": "CC",
            "numero_documento": "123",
            "nombre_completo": "Juan Pérez",
            **extra,
        }
        return self.client.post(reverse("cliente-list"), body, format="json")

    def test_dueno_y_supervisor_crean_cliente(self):
        for usuario in (self.users_a[Usuario.Rol.DUENO], self.users_a[Usuario.Rol.SUPERVISOR]):
            resp = self.crear_cliente(usuario, numero_documento=f"D{usuario.pk}")
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_cajero_lee_pero_no_crea(self):
        self.crear_cliente(self.users_a[Usuario.Rol.DUENO])
        self.auth(self.users_a[Usuario.Rol.CAJERO])
        self.assertEqual(
            self.client.get(reverse("cliente-list")).status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self.crear_cliente(self.users_a[Usuario.Rol.CAJERO]).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_documento_unico_por_empresa_no_global(self):
        self.crear_cliente(self.users_a[Usuario.Rol.DUENO])
        dup = self.crear_cliente(self.users_a[Usuario.Rol.DUENO])
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.crear_cliente(self.users_b[Usuario.Rol.DUENO])
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)

    def test_aislamiento_entre_empresas(self):
        self.crear_cliente(self.users_a[Usuario.Rol.DUENO])
        self.auth(self.users_b[Usuario.Rol.DUENO])
        self.assertEqual(self.client.get(reverse("cliente-list")).data["count"], 0)

    def test_no_elimina_cliente_con_ventas(self):
        cliente = Cliente.objects.create(
            empresa=self.empresa_a,
            tipo_documento="CC",
            numero_documento="1",
            nombre_completo="Ana",
        )
        caja = Caja.objects.create(empresa=self.empresa_a, nombre="Caja 1")
        turno = TurnoCaja.objects.create(
            empresa=self.empresa_a,
            caja=caja,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            saldo_inicial=Decimal("0"),
        )
        Venta.objects.create(
            empresa=self.empresa_a,
            turno=turno,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            cliente=cliente,
            medio_pago=Venta.MedioPago.EFECTIVO,
        )
        self.auth(self.users_a[Usuario.Rol.DUENO])
        resp = self.client.delete(reverse("cliente-detail", args=[cliente.pk]))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
