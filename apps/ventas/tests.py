from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.empresas.models import Empresa
from apps.inventario.models import MovimientoInventario, Producto

from .models import Venta


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


class VentasTests(APITestCase):
    def setUp(self):
        self.empresa, self.users = crear_empresa("900000001", "a")
        self.otra_empresa, self.otros = crear_empresa("900000002", "b")

        # precio_venta YA incluye IVA: 1190 = 1000 (base) + 190 (19%)
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

    def abrir_turno(self, usuario, caja=None):
        self.auth(usuario)
        self.client.post(
            reverse("turno-list"),
            {"caja": (caja or self.caja).pk, "saldo_inicial": "50000.00"},
            format="json",
        )

    def vender(self, usuario, cantidad="2", medio_pago="EFECTIVO", pagos=None, **extra):
        self.auth(usuario)
        if pagos is None:
            total = (Decimal(cantidad) * self.producto.precio_venta).quantize(Decimal("0.01"))
            pagos = [{"medio_pago": medio_pago, "monto": str(total)}]
        body = {
            "detalles": [{"producto": self.producto.pk, "cantidad": cantidad}],
            "pagos": pagos,
            **extra,
        }
        return self.client.post(reverse("venta-list"), body, format="json")

    # --- flujo feliz + IVA + stock ---
    def test_registra_venta_calcula_iva_y_descuenta_stock(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="2")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        self.assertEqual(resp.data["subtotal"], "2000.00")
        self.assertEqual(resp.data["total_iva"], "380.00")
        self.assertEqual(resp.data["total"], "2380.00")
        self.assertEqual(resp.data["medio_pago"], "EFECTIVO")
        self.assertEqual(resp.data["lineas"][0]["total_linea"], "2380.00")
        self.assertEqual(resp.data["cajero_username"], self.users[Usuario.Rol.CAJERO].username)

        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("8"))

        mov = MovimientoInventario.objects.get(venta_id=resp.data["id"])
        self.assertEqual(mov.tipo, MovimientoInventario.Tipo.VENTA)
        self.assertEqual(mov.cantidad, Decimal("-2"))
        self.assertEqual(mov.stock_resultante, Decimal("8"))

    def test_venta_suma_el_total_correctamente_en_varias_lineas(self):
        producto2 = Producto.objects.create(
            empresa=self.empresa,
            codigo="P2",
            nombre="Producto 2",
            precio_venta=Decimal("500.00"),
            porcentaje_iva=Decimal("0.00"),
            stock_actual=Decimal("10"),
        )
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.auth(self.users[Usuario.Rol.CAJERO])
        resp = self.client.post(
            reverse("venta-list"),
            {
                "detalles": [
                    {"producto": self.producto.pk, "cantidad": "1"},  # 1190 (1000+190)
                    {"producto": producto2.pk, "cantidad": "3"},  # 1500 (sin iva)
                ],
                "pagos": [{"medio_pago": "EFECTIVO", "monto": "2690.00"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["total"], "2690.00")
        self.assertEqual(resp.data["total_iva"], "190.00")
        self.assertEqual(resp.data["subtotal"], "2500.00")

    # --- pago mixto ---
    def test_pago_mixto_dos_medios_suma_el_total_y_marca_venta_mixto(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        # producto x 50 = 59500.00 -> 20000 efectivo + 39500 tarjeta
        resp = self.vender(
            self.users[Usuario.Rol.CAJERO],
            cantidad="50",
            pagos=[
                {"medio_pago": "EFECTIVO", "monto": "20000.00"},
                {"medio_pago": "TARJETA", "monto": "39500.00"},
            ],
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["total"], "59500.00")
        self.assertEqual(resp.data["medio_pago"], "MIXTO")
        montos = {p["medio_pago"]: p["monto"] for p in resp.data["pagos_registrados"]}
        self.assertEqual(montos, {"EFECTIVO": "20000.00", "TARJETA": "39500.00"})

    def test_pagos_que_no_cuadran_con_el_total_son_rechazados(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.vender(
            self.users[Usuario.Rol.CAJERO],
            cantidad="2",  # total real = 2380.00
            pagos=[{"medio_pago": "EFECTIVO", "monto": "2000.00"}],
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Venta.objects.count(), 0)
        # el stock NO debe haberse tocado: todo pasó en una sola transacción
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("10"))

    def test_sin_pagos_es_rechazado(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.vender(self.users[Usuario.Rol.CAJERO], pagos=[])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- reglas de negocio ---
    def test_no_vende_sin_turno_abierto(self):
        resp = self.vender(self.users[Usuario.Rol.CAJERO])
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_vende_producto_de_otra_empresa(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        ajeno = Producto.objects.create(
            empresa=self.otra_empresa,
            codigo="X",
            nombre="Ajeno",
            precio_venta=Decimal("100"),
        )
        self.auth(self.users[Usuario.Rol.CAJERO])
        resp = self.client.post(
            reverse("venta-list"),
            {
                "detalles": [{"producto": ajeno.pk, "cantidad": "1"}],
                "pagos": [{"medio_pago": "EFECTIVO", "monto": "100.00"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_vende_producto_inactivo(self):
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sobreventa_permitida(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        resp = self.vender(self.users[Usuario.Rol.CAJERO], cantidad="50")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("-40"))

    def test_venta_es_inmutable(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        pk = self.vender(self.users[Usuario.Rol.CAJERO]).data["id"]
        url = reverse("venta-detail", args=[pk])
        self.assertEqual(
            self.client.patch(url, {"es_de_contado": False}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_aislamiento_entre_empresas(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO])
        self.auth(self.otros[Usuario.Rol.DUENO])
        self.assertEqual(self.client.get(reverse("venta-list")).data["count"], 0)

    # --- "pequeña contabilidad" ---
    def test_resumen_agrega_por_medio_de_pago(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1", medio_pago="EFECTIVO")
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1", medio_pago="TARJETA")
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.get(reverse("venta-resumen"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["cantidad_ventas"], 2)
        self.assertEqual(Decimal(resp.data["total_ventas"]), Decimal("2380.00"))
        por_medio = {r["medio_pago"]: r for r in resp.data["por_medio_pago"]}
        self.assertEqual(Decimal(por_medio["EFECTIVO"]["total"]), Decimal("1190.00"))
        self.assertEqual(Decimal(por_medio["TARJETA"]["total"]), Decimal("1190.00"))

    def test_resumen_reparte_correctamente_una_venta_mixta(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        self.vender(
            self.users[Usuario.Rol.CAJERO],
            cantidad="50",  # total 59500
            pagos=[
                {"medio_pago": "EFECTIVO", "monto": "20000.00"},
                {"medio_pago": "TARJETA", "monto": "39500.00"},
            ],
        )
        self.auth(self.users[Usuario.Rol.DUENO])
        resp = self.client.get(reverse("venta-resumen"))
        por_medio = {r["medio_pago"]: Decimal(r["total"]) for r in resp.data["por_medio_pago"]}
        self.assertEqual(por_medio["EFECTIVO"], Decimal("20000.00"))
        self.assertEqual(por_medio["TARJETA"], Decimal("39500.00"))
        self.assertEqual(resp.data["cantidad_ventas"], 1)  # 1 venta, no 2

    def test_cierre_de_turno_calcula_saldo_con_ventas_en_efectivo(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        turno = TurnoCaja.objects.get(cajero=self.users[Usuario.Rol.CAJERO], estado="abierto")
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1", medio_pago="EFECTIVO")  # 1190
        self.vender(self.users[Usuario.Rol.CAJERO], cantidad="1", medio_pago="TARJETA")  # no cuenta

        self.auth(self.users[Usuario.Rol.CAJERO])
        resp = self.client.post(
            reverse("turno-cerrar", args=[turno.pk]),
            {"saldo_final_declarado": "51190.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        # saldo_inicial 50000 + 1190 en efectivo
        self.assertEqual(resp.data["saldo_final_calculado"], "51190.00")
        self.assertEqual(resp.data["diferencia_caja"], "0.00")
        self.assertEqual(resp.data["resumen_ventas"]["cantidad_ventas"], 2)

    def test_cierre_de_turno_solo_cuenta_la_parte_en_efectivo_de_una_venta_mixta(self):
        self.abrir_turno(self.users[Usuario.Rol.CAJERO])
        turno = TurnoCaja.objects.get(cajero=self.users[Usuario.Rol.CAJERO], estado="abierto")
        self.vender(
            self.users[Usuario.Rol.CAJERO],
            cantidad="50",  # total 59500
            pagos=[
                {"medio_pago": "EFECTIVO", "monto": "20000.00"},
                {"medio_pago": "TARJETA", "monto": "39500.00"},
            ],
        )
        self.auth(self.users[Usuario.Rol.CAJERO])
        resp = self.client.post(
            reverse("turno-cerrar", args=[turno.pk]),
            {"saldo_final_declarado": "70000.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        # saldo_inicial 50000 + SOLO los 20000 en efectivo (no los 39500 de tarjeta)
        self.assertEqual(resp.data["saldo_final_calculado"], "70000.00")
        self.assertEqual(resp.data["diferencia_caja"], "0.00")


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
