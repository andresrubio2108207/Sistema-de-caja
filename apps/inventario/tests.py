from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.empresas.models import Empresa
from apps.inventario.models import Categoria, MovimientoInventario, Producto
from apps.ventas.models import DetalleVenta, Venta


def crear_empresa(nit, prefijo):
    empresa = Empresa.objects.create(
        razon_social=f"Empresa {prefijo}",
        nit=nit,
        digito_verificacion="1",
        regimen_tributario=Empresa.Regimen.RESPONSABLE_IVA,
    )
    usuarios = {
        rol: Usuario.objects.create_user(
            username=f"{prefijo}_{rol}",
            password="Clave-Segura-123",
            empresa=empresa,
            rol=rol,
        )
        for rol in (Usuario.Rol.DUENO, Usuario.Rol.SUPERVISOR, Usuario.Rol.CAJERO)
    }
    return empresa, usuarios


class CatalogoTests(APITestCase):
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

    def crear_producto(self, usuario, **extra):
        self.auth(usuario)
        body = {
            "codigo": "P001",
            "nombre": "Coca-Cola 350ml",
            "precio_venta": "3500.00",
            "porcentaje_iva": "19.00",
            **extra,
        }
        return self.client.post(reverse("producto-list"), body, format="json")

    # --- creación / propiedad por empresa ---
    def test_dueno_crea_categoria_y_producto(self):
        self.auth(self.users_a[Usuario.Rol.DUENO])
        cat = self.client.post(
            reverse("categoria-list"), {"nombre": "Bebidas"}, format="json"
        )
        self.assertEqual(cat.status_code, status.HTTP_201_CREATED, cat.data)
        resp = self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], categoria=cat.data["id"]
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        prod = Producto.objects.get(pk=resp.data["id"])
        self.assertEqual(prod.empresa, self.empresa_a)
        self.assertEqual(resp.data["categoria_nombre"], "Bebidas")

    def test_supervisor_crea_y_edita_producto(self):
        resp = self.crear_producto(self.users_a[Usuario.Rol.SUPERVISOR])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        pk = resp.data["id"]
        patch = self.client.patch(
            reverse("producto-detail", args=[pk]),
            {"precio_venta": "4000.00"},
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(Producto.objects.get(pk=pk).precio_venta, Decimal("4000.00"))

    def test_cajero_lee_pero_no_escribe(self):
        self.crear_producto(self.users_a[Usuario.Rol.DUENO])
        self.auth(self.users_a[Usuario.Rol.CAJERO])
        self.assertEqual(
            self.client.get(reverse("producto-list")).status_code, status.HTTP_200_OK
        )
        creado = self.crear_producto(self.users_a[Usuario.Rol.CAJERO], codigo="P999")
        self.assertEqual(creado.status_code, status.HTTP_403_FORBIDDEN)

    # --- aislamiento multi-tenant ---
    def test_no_ve_productos_de_otra_empresa(self):
        self.crear_producto(self.users_a[Usuario.Rol.DUENO])
        self.auth(self.users_b[Usuario.Rol.DUENO])
        resp = self.client.get(reverse("producto-list"))
        self.assertEqual(resp.data["count"], 0)

    def test_no_puede_usar_categoria_de_otra_empresa(self):
        self.auth(self.users_b[Usuario.Rol.DUENO])
        cat_b = self.client.post(
            reverse("categoria-list"), {"nombre": "Ajena"}, format="json"
        ).data["id"]
        resp = self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], categoria=cat_b
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("categoria", resp.data)

    def test_codigo_unico_por_empresa_no_global(self):
        self.crear_producto(self.users_a[Usuario.Rol.DUENO])
        # mismo código en la empresa A -> rechazado
        dup = self.crear_producto(self.users_a[Usuario.Rol.DUENO])
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo", dup.data)
        # mismo código en la empresa B -> permitido
        ok = self.crear_producto(self.users_b[Usuario.Rol.DUENO])
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)

    # --- eliminación ---
    def test_elimina_producto_sin_ventas(self):
        pk = self.crear_producto(self.users_a[Usuario.Rol.DUENO]).data["id"]
        resp = self.client.delete(reverse("producto-detail", args=[pk]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Producto.objects.filter(pk=pk).exists())

    def test_no_elimina_producto_con_ventas_devuelve_409(self):
        pk = self.crear_producto(self.users_a[Usuario.Rol.DUENO]).data["id"]
        producto = Producto.objects.get(pk=pk)
        caja = Caja.objects.create(empresa=self.empresa_a, nombre="Caja 1")
        turno = TurnoCaja.objects.create(
            empresa=self.empresa_a,
            caja=caja,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            saldo_inicial=Decimal("0"),
        )
        venta = Venta.objects.create(
            empresa=self.empresa_a,
            turno=turno,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            medio_pago=Venta.MedioPago.EFECTIVO,
        )
        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=Decimal("1"),
            precio_unitario=Decimal("3500.00"),
        )

        self.auth(self.users_a[Usuario.Rol.DUENO])
        resp = self.client.delete(reverse("producto-detail", args=[pk]))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Producto.objects.filter(pk=pk).exists())

        # la vía correcta es desactivarlo
        patch = self.client.patch(
            reverse("producto-detail", args=[pk]), {"activo": False}, format="json"
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertFalse(Producto.objects.get(pk=pk).activo)

    def test_eliminar_categoria_deja_productos_sin_categoria(self):
        self.auth(self.users_a[Usuario.Rol.DUENO])
        cat = self.client.post(
            reverse("categoria-list"), {"nombre": "Temporal"}, format="json"
        ).data["id"]
        pk = self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], categoria=cat
        ).data["id"]
        self.auth(self.users_a[Usuario.Rol.DUENO])
        resp = self.client.delete(reverse("categoria-detail", args=[cat]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNone(Producto.objects.get(pk=pk).categoria)

    # --- filtros ---
    def test_filtra_por_activo_y_busca(self):
        self.auth(self.users_a[Usuario.Rol.DUENO])
        self.crear_producto(self.users_a[Usuario.Rol.DUENO], codigo="A1", nombre="Agua")
        self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], codigo="A2", nombre="Gaseosa", activo=False
        )
        self.auth(self.users_a[Usuario.Rol.DUENO])
        activos = self.client.get(reverse("producto-list"), {"activo": "true"})
        self.assertEqual({p["codigo"] for p in activos.data["results"]}, {"A1"})
        busca = self.client.get(reverse("producto-list"), {"search": "gase"})
        self.assertEqual({p["codigo"] for p in busca.data["results"]}, {"A2"})

    # --- stock de solo lectura vía API ---
    def test_stock_actual_no_editable_por_api(self):
        pk = self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], stock_inicial="10"
        ).data["id"]
        resp = self.client.patch(
            reverse("producto-detail", args=[pk]),
            {"stock_actual": "999"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Producto.objects.get(pk=pk).stock_actual, Decimal("10.00"))

    def test_stock_inicial_genera_movimiento_entrada(self):
        resp = self.crear_producto(
            self.users_a[Usuario.Rol.DUENO], stock_inicial="25"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        producto = Producto.objects.get(pk=resp.data["id"])
        self.assertEqual(producto.stock_actual, Decimal("25.00"))
        mov = MovimientoInventario.objects.get(producto=producto)
        self.assertEqual(mov.tipo, MovimientoInventario.Tipo.ENTRADA)
        self.assertEqual(mov.cantidad, Decimal("25.00"))
        self.assertEqual(mov.stock_resultante, Decimal("25.00"))
        self.assertEqual(mov.motivo, "Stock inicial")


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
