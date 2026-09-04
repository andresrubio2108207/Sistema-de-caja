"""Seguridad multiempresa: un usuario de la Empresa B jamás debe poder leer
ni modificar un recurso de la Empresa A cambiando un id en la URL — así
tenga el rol con más permisos posible (dueño) y conozca el id exacto.

Se prueba con el dueño de B (no con un cajero) a propósito: si se usara un
rol con permisos limitados, un 403 podría deberse solo al permiso por rol y
esconder que el aislamiento por empresa (EmpresaQuerysetMixin) esté roto.
Con el dueño, que pasa cualquier chequeo de rol, un 404 solo puede venir de
que el id no aparece en absoluto en el queryset de su empresa.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.caja.models import Caja, TurnoCaja
from apps.cuentas.models import Usuario
from apps.inventario.models import Categoria, MovimientoInventario, Producto
from apps.inventario.services import aplicar_movimiento
from apps.terceros.models import Cliente
from apps.ventas.models import DetalleVenta, Venta
from apps.ventas.services import emitir_nota_credito

from ..models import Empresa


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


class SeguridadMultiempresaTests(APITestCase):
    def setUp(self):
        self.empresa_a, self.users_a = crear_empresa("900000001", "a")
        self.empresa_b, self.users_b = crear_empresa("900000002", "b")

        # Un recurso de CADA tipo, sembrado en la empresa A.
        self.categoria = Categoria.objects.create(empresa=self.empresa_a, nombre="Bebidas")
        self.producto = Producto.objects.create(
            empresa=self.empresa_a,
            categoria=self.categoria,
            codigo="P1",
            nombre="Producto A",
            precio_venta=Decimal("1000"),
            stock_actual=Decimal("10"),
        )
        self.movimiento = aplicar_movimiento(
            producto=self.producto,
            tipo=MovimientoInventario.Tipo.ENTRADA,
            cantidad=Decimal("5"),
            motivo="Carga inicial",
        )
        self.cliente = Cliente.objects.create(
            empresa=self.empresa_a,
            tipo_documento="CC",
            numero_documento="123",
            nombre_completo="Cliente A",
        )
        self.caja = Caja.objects.create(empresa=self.empresa_a, nombre="Caja 1")
        self.turno = TurnoCaja.objects.create(
            empresa=self.empresa_a,
            caja=self.caja,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            saldo_inicial=Decimal("0"),
        )
        self.venta = Venta.objects.create(
            empresa=self.empresa_a,
            turno=self.turno,
            cajero=self.users_a[Usuario.Rol.CAJERO],
            medio_pago=Venta.MedioPago.EFECTIVO,
        )
        self.detalle_venta = DetalleVenta.objects.create(
            venta=self.venta,
            producto=self.producto,
            cantidad=Decimal("2"),
            precio_unitario=Decimal("1000"),
            porcentaje_iva=Decimal("0"),
        )
        self.nota_credito = emitir_nota_credito(
            venta=self.venta,
            usuario=self.users_a[Usuario.Rol.DUENO],
            motivo="prueba",
            lineas=[{"detalle_venta": self.detalle_venta, "cantidad": Decimal("1")}],
        )
        self.usuario_objetivo = self.users_a[Usuario.Rol.CAJERO]

    def auth(self, usuario):
        token = self.client.post(
            reverse("token_obtain_pair"),
            {"username": usuario.username, "password": "Clave-Segura-123"},
            format="json",
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_dueno_de_b_no_accede_a_recursos_de_a_por_id(self):
        # dueño: pasa CUALQUIER permiso por rol, así que un 404 aquí solo
        # puede venir del aislamiento por empresa, no de falta de permiso.
        self.auth(self.users_b[Usuario.Rol.DUENO])

        casos = [
            ("categoria-detail", self.categoria.pk, True, True),
            ("producto-detail", self.producto.pk, True, True),
            ("movimiento-inventario-detail", self.movimiento.pk, False, False),
            ("cliente-detail", self.cliente.pk, True, True),
            ("caja-detail", self.caja.pk, True, True),
            ("turno-detail", self.turno.pk, False, False),
            ("venta-detail", self.venta.pk, False, False),
            ("nota-credito-detail", self.nota_credito.pk, False, False),
            ("usuario-detail", self.usuario_objetivo.pk, True, True),
        ]
        for nombre_url, pk, admite_patch, admite_delete in casos:
            url = reverse(nombre_url, args=[pk])
            with self.subTest(recurso=nombre_url):
                resp = self.client.get(url)
                self.assertEqual(
                    resp.status_code,
                    status.HTTP_404_NOT_FOUND,
                    f"GET {url} devolvió {resp.status_code} en vez de 404 (fuga de datos)",
                )
                if admite_patch:
                    resp = self.client.patch(url, {}, format="json")
                    self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
                if admite_delete:
                    resp = self.client.delete(url)
                    self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_puede_cerrar_turno_ajeno_por_id(self):
        self.auth(self.users_b[Usuario.Rol.DUENO])
        resp = self.client.post(
            reverse("turno-cerrar", args=[self.turno.pk]),
            {"saldo_final_declarado": "0"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_puede_reasignar_categoria_ajena_a_producto_propio_por_patch(self):
        """No solo al crear: tampoco se puede, al EDITAR un producto propio,
        engancharlo a una categoría de otra empresa."""
        self.auth(self.users_a[Usuario.Rol.DUENO])
        propio = Producto.objects.create(
            empresa=self.empresa_a, codigo="P2", nombre="Propio", precio_venta=Decimal("1")
        )
        categoria_b = Categoria.objects.create(empresa=self.empresa_b, nombre="Ajena")
        resp = self.client.patch(
            reverse("producto-detail", args=[propio.pk]),
            {"categoria": categoria_b.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_listas_no_incluyen_nada_de_otra_empresa(self):
        """Barrido de listados: el id de un recurso de A nunca debe
        aparecer en el listado de B, así B tenga recursos propios del mismo
        tipo (ej. usuario-list: B ve sus 3 usuarios, nunca los de A)."""
        self.auth(self.users_b[Usuario.Rol.DUENO])
        casos = [
            ("categoria-list", self.categoria.pk),
            ("producto-list", self.producto.pk),
            ("movimiento-inventario-list", self.movimiento.pk),
            ("cliente-list", self.cliente.pk),
            ("caja-list", self.caja.pk),
            ("turno-list", self.turno.pk),
            ("venta-list", self.venta.pk),
            ("nota-credito-list", self.nota_credito.pk),
            ("usuario-list", self.usuario_objetivo.pk),
        ]
        for nombre_url, id_de_a in casos:
            with self.subTest(recurso=nombre_url):
                resp = self.client.get(reverse(nombre_url))
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                ids = {fila["id"] for fila in resp.data["results"]}
                self.assertNotIn(id_de_a, ids, f"{nombre_url} filtró mal por empresa")
