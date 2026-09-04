from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.inventario.models import MovimientoInventario, Producto

from .base import crear_empresa


class AnulacionTicketReportesTests(APITestCase):
    def setUp(self):
        self.empresa, self.users = crear_empresa("900000001", "a")
        self.producto = Producto.objects.create(
            empresa=self.empresa,
            codigo="P1",
            nombre="Producto",
            precio_venta=Decimal("1190.00"),
            porcentaje_iva=Decimal("19.00"),
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

    def vender(self, usuario, cantidad="2", monto=None):
        self.auth(usuario)
        if monto is None:
            monto = str((Decimal(cantidad) * self.producto.precio_venta).quantize(Decimal("0.01")))
        return self.client.post(
            reverse("venta-list"),
            {
                "detalles": [{"producto": self.producto.pk, "cantidad": cantidad}],
                "pagos": [{"medio_pago": "EFECTIVO", "monto": monto}],
            },
            format="json",
        )

    # --- anulación ---
    def test_anular_devuelve_stock_y_marca_anulada(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="2").data["id"]
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("8"))

        resp = self.client.post(
            reverse("venta-anular", args=[pk]), {"motivo": "cobré mal"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["estado"], "anulada")
        self.assertEqual(resp.data["motivo_anulacion"], "cobré mal")
        self.assertIsNotNone(resp.data["anulada_en"])

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("10"))
        mov = MovimientoInventario.objects.filter(
            venta_id=pk, tipo=MovimientoInventario.Tipo.DEVOLUCION
        ).get()
        self.assertEqual(mov.cantidad, Decimal("2"))

    def test_no_se_puede_anular_dos_veces(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.client.post(reverse("venta-anular", args=[pk]), {}, format="json")
        resp = self.client.post(reverse("venta-anular", args=[pk]), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_puede_anular_con_turno_cerrado(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        turno = TurnoCaja.objects.get(cajero=self.users[Usuario.Rol.CAJERO], estado="abierto")
        pk = self.vender(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.client.post(
            reverse("turno-cerrar", args=[turno.pk]),
            {"saldo_final_declarado": "52380.00"},
            format="json",
        )
        resp = self.client.post(reverse("venta-anular", args=[pk]), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("8"))  # sigue descontado

    def test_cajero_no_anula_venta_de_otro_cajero(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO]).data["id"]
        otro = Usuario.objects.create_user(
            username="a_cajero2", password="Clave-Segura-123", empresa=self.empresa, rol=Usuario.Rol.CAJERO
        )
        self.auth(otro)
        resp = self.client.post(reverse("venta-anular", args=[pk]), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_dueno_puede_anular_venta_de_cualquier_cajero(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO]).data["id"]
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.post(reverse("venta-anular", args=[pk]), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_venta_anulada_no_cuenta_en_resumen_ni_en_arqueo(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        turno = TurnoCaja.objects.get(cajero=self.users[Usuario.Rol.CAJERO], estado="abierto")
        pk_anulada = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="2").data["id"]
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1")  # esta sí cuenta: 1190
        self.client.post(reverse("venta-anular", args=[pk_anulada]), {}, format="json")

        resp = self.client.get(reverse("venta-resumen"))
        self.assertEqual(resp.data["cantidad_ventas"], 1)
        self.assertEqual(Decimal(resp.data["total_ventas"]), Decimal("1190.00"))

        cierre = self.client.post(
            reverse("turno-cerrar", args=[turno.pk]),
            {"saldo_final_declarado": "51190.00"},
            format="json",
        )
        self.assertEqual(cierre.data["saldo_final_calculado"], "51190.00")

    # --- ticket ---
    def test_ticket_trae_todo_lo_necesario_para_imprimir(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="2").data["id"]
        resp = self.client.get(reverse("venta-ticket", args=[pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["empresa"]["razon_social"], "Empresa a")
        self.assertEqual(resp.data["caja_nombre"], "Caja 1")
        self.assertEqual(resp.data["cliente_nombre"], "Consumidor final")
        self.assertEqual(len(resp.data["detalles"]), 1)
        self.assertEqual(resp.data["detalles"][0]["total_linea"], "2380.00")
        self.assertEqual(len(resp.data["pagos"]), 1)

    # --- reportes ---
    def test_productos_mas_vendidos(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="3")
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.get(reverse("venta-productos-mas-vendidos"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["productos"][0]["codigo"], "P1")
        self.assertEqual(resp.data["productos"][0]["cantidad_vendida"], Decimal("3.00"))

    def test_ventas_por_cajero(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1")
        self.auth(self.users[Usuario.Rol.SUPERVISOR])
        resp = self.client.get(reverse("venta-por-cajero"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["cajeros"][0]["cajero_username"], "a_cajero")
        self.assertEqual(Decimal(resp.data["cajeros"][0]["total_vendido"]), Decimal("1190.00"))

    def test_cajero_no_ve_reportes_de_desempeno(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO])
        self.assertEqual(
            self.client.get(reverse("venta-productos-mas-vendidos")).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get(reverse("venta-por-cajero")).status_code,
            status.HTTP_403_FORBIDDEN,
        )
