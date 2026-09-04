"""Registro de una venta: crea Venta + DetalleVenta + PagoVenta, calcula
totales y descuenta stock vía el kardex — todo en una sola transacción.

Convención de precios: ``Producto.precio_venta`` YA INCLUYE IVA (es lo que
paga el cliente). La base gravable se calcula hacia atrás por línea:
``base = total_linea / (1 + %iva/100)``, ``iva = total_linea - base``. El
precio de cada línea es siempre el del catálogo al momento de la venta
(snapshot); no se admite un precio distinto desde la caja. El %IVA es el de
CADA producto (``producto.porcentaje_iva``), nunca uno fijo global — así
conviven gravados a distintas tarifas con exentos/excluidos (0%).

Pagos: una venta admite uno o más ``PagoVenta`` (ej. $20.000 efectivo +
$30.000 tarjeta). La suma de los pagos debe ser exactamente igual al total
de la venta. ``Venta.medio_pago`` lo calcula el servidor: el único medio si
hay un solo pago, o ``MIXTO`` si hay dos o más.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.caja.models import TurnoCaja
from apps.inventario.models import MovimientoInventario, Producto
from apps.inventario.services import aplicar_movimiento

from .models import DetalleVenta, PagoVenta, Venta

DOS_DECIMALES = Decimal("0.01")


class TurnoNoAbierto(Exception):
    """El cajero no tiene un turno abierto: no se puede vender."""


class ProductoInvalido(Exception):
    """Un producto de la venta no es vendible tal cual viene (inactivo, de
    otra empresa, etc.)."""


class PagoInvalido(Exception):
    """Los pagos no cuadran con el total de la venta."""


class VentaYaAnulada(Exception):
    pass


class AnulacionNoPermitida(Exception):
    """El turno de la venta ya cerró: anular a esta altura descuadraría un
    arqueo ya hecho. Eso se resuelve con nota crédito cuando exista
    facturación, no con esta anulación simple."""


def _dividir_iva(total_linea: Decimal, porcentaje_iva: Decimal) -> tuple[Decimal, Decimal]:
    """``total_linea`` ya incluye IVA. Devuelve ``(base, iva)`` en 2
    decimales, garantizando ``base + iva == total_linea`` exactamente."""
    base = (total_linea / (Decimal("1") + porcentaje_iva / Decimal("100"))).quantize(
        DOS_DECIMALES, rounding=ROUND_HALF_UP
    )
    iva = total_linea - base
    return base, iva


@transaction.atomic
def registrar_venta(*, empresa, cajero, cliente, es_de_contado, lineas, pagos):
    if not lineas:
        raise ProductoInvalido("La venta debe tener al menos una línea.")
    if not pagos:
        raise PagoInvalido("La venta debe tener al menos un pago.")

    turno = (
        TurnoCaja.objects.select_for_update()
        .filter(empresa=empresa, cajero=cajero, estado=TurnoCaja.Estado.ABIERTO)
        .first()
    )
    if turno is None:
        raise TurnoNoAbierto("Debes abrir un turno de caja antes de registrar ventas.")

    # Se bloquean TODOS los productos involucrados de una vez, en un orden
    # determinístico (por pk). Evita interbloqueos entre dos checkouts
    # concurrentes que comparten productos pero los procesan en orden distinto.
    ids_producto = sorted({linea["producto"].pk for linea in lineas})
    productos = {
        p.pk: p
        for p in Producto.objects.select_for_update().filter(pk__in=ids_producto).order_by("pk")
    }
    for pk in ids_producto:
        if pk not in productos or productos[pk].empresa_id != empresa.id:
            raise ProductoInvalido(f"El producto {pk} no pertenece a tu empresa.")
        if not productos[pk].activo:
            raise ProductoInvalido(f"El producto {productos[pk].codigo} está inactivo.")

    venta = Venta.objects.create(
        empresa=empresa,
        turno=turno,
        cajero=cajero,
        cliente=cliente,
        medio_pago=Venta.MedioPago.EFECTIVO,  # placeholder; se fija abajo con los pagos reales
        es_de_contado=es_de_contado,
    )

    subtotal = Decimal("0")
    total_iva = Decimal("0")
    total = Decimal("0")

    for linea in lineas:
        producto = productos[linea["producto"].pk]
        cantidad = linea["cantidad"]

        precio_unitario = producto.precio_venta  # foto del catálogo, IVA incluido
        total_linea = (cantidad * precio_unitario).quantize(
            DOS_DECIMALES, rounding=ROUND_HALF_UP
        )
        base_linea, iva_linea = _dividir_iva(total_linea, producto.porcentaje_iva)

        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
        )

        if producto.controla_stock:
            aplicar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.Tipo.VENTA,
                cantidad=-cantidad,
                venta=venta,
                usuario=cajero,
                motivo=f"Venta #{venta.pk}",
            )

        subtotal += base_linea
        total_iva += iva_linea
        total += total_linea

    total_pagado = sum((p["monto"] for p in pagos), Decimal("0"))
    if total_pagado != total:
        raise PagoInvalido(
            f"Los pagos suman {total_pagado} pero la venta es {total}."
        )

    for pago in pagos:
        PagoVenta.objects.create(
            venta=venta, medio_pago=pago["medio_pago"], monto=pago["monto"]
        )

    venta.subtotal = subtotal
    venta.total_iva = total_iva
    venta.total = total
    venta.medio_pago = (
        pagos[0]["medio_pago"] if len(pagos) == 1 else Venta.MedioPago.MIXTO
    )
    venta.save(update_fields=["subtotal", "total_iva", "total", "medio_pago"])
    return venta


@transaction.atomic
def anular_venta(*, venta, usuario, motivo=""):
    """Anula una venta completa: devuelve TODO su stock (movimientos
    ``devolucion`` en el kardex) y la marca ``anulada``. Nunca se borra — es
    historial. Solo se permite mientras el turno de la venta sigue abierto:
    si ya cerró, el arqueo de ese turno ya se hizo con esa venta adentro, y
    corregirlo a esta altura es tema de nota crédito (facturación), no de
    esta anulación simple."""
    venta = Venta.objects.select_for_update().get(pk=venta.pk)
    if venta.estado == Venta.Estado.ANULADA:
        raise VentaYaAnulada("Esta venta ya está anulada.")

    turno = TurnoCaja.objects.select_for_update().get(pk=venta.turno_id)
    if turno.estado != TurnoCaja.Estado.ABIERTO:
        raise AnulacionNoPermitida(
            "El turno de esta venta ya cerró; no se puede anular así."
        )

    for detalle in venta.detalles.select_related("producto"):
        if detalle.producto.controla_stock:
            aplicar_movimiento(
                producto=detalle.producto,
                tipo=MovimientoInventario.Tipo.DEVOLUCION,
                cantidad=detalle.cantidad,
                venta=venta,
                usuario=usuario,
                motivo=f"Anulación venta #{venta.pk}" + (f": {motivo}" if motivo else ""),
            )

    venta.estado = Venta.Estado.ANULADA
    venta.motivo_anulacion = motivo
    venta.anulada_en = timezone.now()
    venta.save(update_fields=["estado", "motivo_anulacion", "anulada_en"])
    return venta


def resumen_de_ventas(ventas_qs):
    """Pequeño reporte contable sobre un queryset de ``Venta``: total,
    cantidad y desglose por medio de pago. El desglose sale de
    ``PagoVenta`` (no de ``Venta.medio_pago``) para que una venta MIXTO
    reparta correctamente entre efectivo/tarjeta/etc. Las ventas anuladas
    NUNCA cuentan en un reporte de dinero."""
    ventas_qs = ventas_qs.exclude(estado=Venta.Estado.ANULADA)
    totales = ventas_qs.aggregate(total=Sum("total"), cantidad=Count("id"))
    por_medio_pago = list(
        PagoVenta.objects.filter(venta__in=ventas_qs)
        .values("medio_pago")
        .annotate(total=Sum("monto"), cantidad=Count("id"))
        .order_by("medio_pago")
    )
    return {
        "cantidad_ventas": totales["cantidad"] or 0,
        "total_ventas": totales["total"] or Decimal("0"),
        "por_medio_pago": por_medio_pago,
    }


def productos_mas_vendidos(ventas_qs, limite=10):
    """Ranking de productos por cantidad vendida, dentro del rango de
    ``ventas_qs``. Las ventas anuladas no cuentan."""
    ventas_qs = ventas_qs.exclude(estado=Venta.Estado.ANULADA)
    filas = (
        DetalleVenta.objects.filter(venta__in=ventas_qs)
        .values("producto_id", "producto__codigo", "producto__nombre")
        .annotate(
            cantidad_vendida=Sum("cantidad"),
            total_vendido=Sum(F("cantidad") * F("precio_unitario")),
            veces_vendido=Count("id"),
        )
        .order_by("-cantidad_vendida")[:limite]
    )
    return [
        {
            "producto_id": f["producto_id"],
            "codigo": f["producto__codigo"],
            "nombre": f["producto__nombre"],
            "cantidad_vendida": f["cantidad_vendida"],
            "total_vendido": f["total_vendido"],
            "veces_vendido": f["veces_vendido"],
        }
        for f in filas
    ]


def ventas_por_cajero(ventas_qs):
    """Desempeño de ventas por cajero, dentro del rango de ``ventas_qs``.
    Las ventas anuladas no cuentan."""
    ventas_qs = ventas_qs.exclude(estado=Venta.Estado.ANULADA)
    filas = (
        ventas_qs.values("cajero_id", "cajero__username")
        .annotate(cantidad_ventas=Count("id"), total_vendido=Sum("total"))
        .order_by("-total_vendido")
    )
    return [
        {
            "cajero_id": f["cajero_id"],
            "cajero_username": f["cajero__username"],
            "cantidad_ventas": f["cantidad_ventas"],
            "total_vendido": f["total_vendido"],
        }
        for f in filas
    ]
