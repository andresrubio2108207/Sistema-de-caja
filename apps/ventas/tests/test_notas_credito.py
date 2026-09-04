from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.inventario.models import MovimientoInventario, Producto

from .base import crear_empresa


class NotaCreditoYReportesTests(APITestCase):
    def setUp(self):
        self.empresa, self.users = crear_empresa("900000001", "a")
        # precio_venta YA incluye IVA: 1190 = 1000 (base) + 190 (19%)
        self.producto_a = Producto.objects.create(
            empresa=self.empresa,
            codigo="A",
            nombre="Gravado 19%",
            precio_venta=Decimal("1190.00"),
            porcentaje_iva=Decimal("19.00"),
            stock_actual=Decimal("10"),
        )
        self.producto_b = Producto.objects.create(
            empresa=self.empresa,
            codigo="B",
            nombre="Exento",
            precio_venta=Decimal("500.00"),
            porcentaje_iva=Decimal("0.00"),
            stock_actual=Decimal("10"),
        )
        self.caja = Caja.objects.create(empresa=self.empresa, nombre="Caja 1")

    def auth(self, usuario):
        token = self.client.post(
            reverse("token_obtain_pair"),
            {"username": usuario.username, "password": "Clave-Segura-123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def abrir_turno(self, usuario):
        self.auth(usuario)
        self.client.post(
            reverse("turno-list"),
            {"caja": self.caja.pk, "saldo_inicial": "50000.00"},
            format="json",
        )

    def vender(self, usuario, lineas):
        self.auth(usuario)
        total = sum(
            (Decimal(l["cantidad"]) * self._precio(l["producto"]) for l in lineas), Decimal("0")
        ).quantize(Decimal("0.01"))
        return self.client.post(
            reverse("venta-list"),
            {
                "detalles": lineas,
                "pagos": [{"medio_pago": "EFECTIVO", "monto": str(total)}],
            },
            format="json",
        )

    def _precio(self, producto_pk):
        return (
            self.producto_a.precio_venta
            if producto_pk == self.producto_a.pk
            else self.producto_b.precio_venta
        )

    def emitir_nc(self, venta_id, lineas, motivo=""):
        return self.client.post(
            reverse("nota-credito-list"),
            {"venta": venta_id, "motivo": motivo, "lineas": lineas},
            format="json",
        )

    # --- nota crédito: flujo feliz ---
    def test_nota_credito_parcial_devuelve_stock_y_calcula_iva(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "3"}],
        ).data
        self.producto_a.refresh_from_db()
        self.assertEqual(self.producto_a.stock_actual, Decimal("7"))

        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_id = venta["lineas"][0]["id"]
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "1"}], "dañado")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["subtotal"], "1000.00")
        self.assertEqual(resp.data["total_iva"], "190.00")
        self.assertEqual(resp.data["total"], "1190.00")
        self.assertEqual(resp.data["lineas_registradas"][0]["producto_codigo"], "A")

        self.producto_a.refresh_from_db()
        self.assertEqual(self.producto_a.stock_actual, Decimal("8"))
        mov = MovimientoInventario.objects.filter(
            producto=self.producto_a, tipo=MovimientoInventario.Tipo.DEVOLUCION
        ).latest("id")
        self.assertEqual(mov.cantidad, Decimal("1"))

    def test_no_se_puede_devolver_mas_de_lo_disponible(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "2"}],
        ).data
        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_id = venta["lineas"][0]["id"]
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "3"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_notas_credito_parciales_acumulan(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "5"}],
        ).data
        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_id = venta["lineas"][0]["id"]
        self.assertEqual(
            self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "2"}]).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "2"}]).status_code,
            status.HTTP_201_CREATED,
        )
        # ya se devolvieron 4 de 5: pedir 2 más debe fallar (solo queda 1)
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "2"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_nota_credito_de_venta_anulada(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "1"}],
        ).data
        self.client.post(reverse("venta-anular", args=[venta["id"]]), {}, format="json")
        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_id = venta["lineas"][0]["id"]
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "1"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nota_credito_funciona_con_turno_cerrado(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        turno = TurnoCaja.objects.get(cajero=self.users[Usuario.Rol.CAJERO], estado="abierto")
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "1"}],
        ).data
        self.client.post(
            reverse("turno-cerrar", args=[turno.pk]),
            {"saldo_final_declarado": "51190.00"},
            format="json",
        )
        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_id = venta["lineas"][0]["id"]
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "1"}])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_cajero_no_puede_emitir_ni_ver_notas_credito(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "1"}],
        ).data
        detalle_id = venta["lineas"][0]["id"]
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": detalle_id, "cantidad": "1"}])
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.client.get(reverse("nota-credito-list")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_aislamiento_entre_empresas(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [{"producto": self.producto_a.pk, "cantidad": "1"}],
        ).data
        otra_empresa, otros = crear_empresa("900000002", "b")
        self.auth(otros[Usuario.Rol.DUENO])
        # la venta de A ni siquiera existe para el dueño de B
        resp = self.emitir_nc(venta["id"], [{"detalle_venta": venta["lineas"][0]["id"], "cantidad": "1"}])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- reportes ---
    def test_reporte_iva_desglosa_por_tarifa_y_resta_notas_credito(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        venta = self.vender(
            self.users[Usuario.Rol.CAJERO],
            [
                {"producto": self.producto_a.pk, "cantidad": "2"},  # 2380 (2000+380)
                {"producto": self.producto_b.pk, "cantidad": "2"},  # 1000 (sin iva)
            ],
        ).data
        self.auth(self.users[Usuario.Rol.DUENO])
        detalle_a_id = next(l["id"] for l in venta["lineas"] if l["producto_codigo"] == "A")
        self.emitir_nc(venta["id"], [{"detalle_venta": detalle_a_id, "cantidad": "1"}])

        resp = self.client.get(reverse("venta-reporte-iva"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["bruto"]["subtotal"], Decimal("3000.00"))
        self.assertEqual(resp.data["bruto"]["total_iva"], Decimal("380.00"))
        self.assertEqual(resp.data["bruto"]["total"], Decimal("3380.00"))
        self.assertEqual(resp.data["notas_credito"]["total"], Decimal("1190.00"))
        self.assertEqual(resp.data["neto"]["subtotal"], Decimal("2000.00"))
        self.assertEqual(resp.data["neto"]["total_iva"], Decimal("190.00"))
        self.assertEqual(resp.data["neto"]["total"], Decimal("2190.00"))

        por_tarifa = {f["porcentaje_iva"]: f for f in resp.data["por_tarifa"]}
        self.assertEqual(por_tarifa[Decimal("19.00")]["total"], Decimal("2380.00"))
        self.assertEqual(por_tarifa[Decimal("0.00")]["total"], Decimal("1000.00"))

    def test_cajero_no_ve_reporte_iva(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.client.get(reverse("venta-reporte-iva"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_ventas_por_dia(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO], [{"producto": self.producto_a.pk, "cantidad": "1"}])
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.get(reverse("venta-por-dia"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["dias"]), 1)
        self.assertEqual(resp.data["dias"][0]["total_vendido"], Decimal("1190.00"))
