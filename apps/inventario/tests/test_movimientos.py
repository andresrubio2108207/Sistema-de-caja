from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cuentas.models import Usuario
from apps.inventario.models import Producto

from .test_catalogo import crear_empresa


class MovimientosInventarioTests(APITestCase):
    def setUp(self):
        self.empresa_a, self.users_a = crear_empresa("900000001", "a")
        self.empresa_b, self.users_b = crear_empresa("900000002", "b")
        self.prod_a = Producto.objects.create(
            empresa=self.empresa_a,
            codigo="P1",
            nombre="Producto A",
            precio_venta=Decimal("1000"),
            stock_actual=Decimal("50"),
        )
        self.prod_b = Producto.objects.create(
            empresa=self.empresa_b,
            codigo="P1",
            nombre="Producto B",
            precio_venta=Decimal("1000"),
        )

    def auth(self, usuario):
        token = self.client.post(
            reverse("token_obtain_pair"),
            {"username": usuario.username, "password": "Clave-Segura-123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def mover(self, usuario, **body):
        self.auth(usuario)
        return self.client.post(
            reverse("movimiento-inventario-list"),
            {"producto": self.prod_a.pk, **body},
            format="json",
        )

    def test_entrada_suma_y_registra_stock_resultante(self):
        resp = self.mover(
            self.users_a[Usuario.Rol.SUPERVISOR], tipo="entrada", cantidad="12"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["stock_resultante"], "62.00")
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_actual, Decimal("62"))

    def test_salida_resta(self):
        resp = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="salida", cantidad="-8", motivo="Merma"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_actual, Decimal("42"))

    def test_ajuste_acepta_ambos_signos(self):
        self.assertEqual(
            self.mover(
                self.users_a[Usuario.Rol.DUENO], tipo="ajuste", cantidad="-3"
            ).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            self.mover(
                self.users_a[Usuario.Rol.DUENO], tipo="ajuste", cantidad="5"
            ).status_code,
            status.HTTP_201_CREATED,
        )
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_actual, Decimal("52"))

    def test_signo_incoherente_rechazado(self):
        resp = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="-5"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cantidad", resp.data)

    def test_tipo_venta_no_permitido_por_api(self):
        resp = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="venta", cantidad="-1"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipo", resp.data)

    def test_sobreventa_permitida_stock_negativo(self):
        resp = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="salida", cantidad="-70"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.prod_a.refresh_from_db()
        self.assertEqual(self.prod_a.stock_actual, Decimal("-20"))

    def test_producto_sin_control_de_stock_rechaza_movimiento(self):
        self.prod_a.controla_stock = False
        self.prod_a.save(update_fields=["controla_stock"])
        resp = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="1"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cajero_no_crea_pero_lee_kardex(self):
        self.mover(self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="1")
        resp = self.mover(self.users_a[Usuario.Rol.CAJERO], tipo="entrada", cantidad="1")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.auth(self.users_a[Usuario.Rol.CAJERO])
        lista = self.client.get(reverse("movimiento-inventario-list"))
        self.assertEqual(lista.status_code, status.HTTP_200_OK)
        self.assertEqual(lista.data["count"], 1)

    def test_movimiento_inmutable(self):
        pk = self.mover(
            self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="1"
        ).data["id"]
        url = reverse("movimiento-inventario-detail", args=[pk])
        self.assertEqual(
            self.client.patch(url, {"cantidad": "9"}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_aislamiento_entre_empresas(self):
        self.mover(self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="1")
        # empresa B no ve el kardex de A
        self.auth(self.users_b[Usuario.Rol.DUENO])
        self.assertEqual(
            self.client.get(reverse("movimiento-inventario-list")).data["count"], 0
        )
        # empresa B no puede mover un producto de A
        resp = self.client.post(
            reverse("movimiento-inventario-list"),
            {"producto": self.prod_a.pk, "tipo": "entrada", "cantidad": "1"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_producto_con_movimientos_no_se_borra(self):
        self.mover(self.users_a[Usuario.Rol.DUENO], tipo="entrada", cantidad="1")
        self.auth(self.users_a[Usuario.Rol.DUENO])
        resp = self.client.delete(
            reverse("producto-detail", args=[self.prod_a.pk])
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
