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
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.caja.models import TurnoCaja
from apps.inventario.models import MovimientoInventario, Producto
from apps.inventario.services import aplicar_movimiento

from .models import DetalleVenta, LineaNotaCredito, NotaCredito, PagoVenta, Venta

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
    arqueo ya hecho. Para eso está la nota crédito (parcial o total, sin
    importar si el turno sigue abierto)."""


class NotaCreditoInvalida(Exception):
    """La nota crédito no se puede emitir tal cual viene (venta anulada,
    línea ajena, cantidad mayor a la disponible, etc.)."""


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
            porcentaje_iva=producto.porcentaje_iva,
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


@transaction.atomic
def emitir_nota_credito(*, venta, usuario, motivo, lineas):
    """``lineas``: [{"detalle_venta": DetalleVenta, "cantidad": Decimal}, ...]

    Devuelve stock por las cantidades indicadas (nunca más de lo que
    quedaba disponible en esa línea, contando notas crédito previas) y dos
    o más notas crédito parciales de la misma venta se van acumulando
    correctamente."""
    if not lineas:
        raise NotaCreditoInvalida("La nota crédito debe tener al menos una línea.")

    venta = Venta.objects.select_for_update().get(pk=venta.pk)
    if venta.estado == Venta.Estado.ANULADA:
        raise NotaCreditoInvalida("No se puede hacer nota crédito de una venta anulada.")

    for linea in lineas:
        if linea["detalle_venta"].venta_id != venta.pk:
            raise NotaCreditoInvalida(
                f"La línea {linea['detalle_venta'].pk} no pertenece a esta venta."
            )

    # Mismo orden determinístico que registrar_venta: evita interbloqueos
    # con otras operaciones que también tocan estos productos.
    ids_producto = sorted({l["detalle_venta"].producto_id for l in lineas})
    productos = {
        p.pk: p
        for p in Producto.objects.select_for_update().filter(pk__in=ids_producto).order_by("pk")
    }

    nota = NotaCredito.objects.create(
        empresa=venta.empresa, venta=venta, usuario=usuario, motivo=motivo
    )

    subtotal = Decimal("0")
    total_iva = Decimal("0")
    total = Decimal("0")

    for linea in lineas:
        detalle = linea["detalle_venta"]
        cantidad = linea["cantidad"]

        ya_devuelta = (
            LineaNotaCredito.objects.filter(detalle_venta=detalle).aggregate(t=Sum("cantidad"))["t"]
            or Decimal("0")
        )
        disponible = detalle.cantidad - ya_devuelta
        if cantidad > disponible:
            raise NotaCreditoInvalida(
                f"La línea {detalle.pk} solo tiene {disponible} disponible para "
                f"devolver (de {detalle.cantidad}, ya devuelto {ya_devuelta})."
            )

        LineaNotaCredito.objects.create(
            nota_credito=nota, detalle_venta=detalle, cantidad=cantidad
        )

        total_linea = (cantidad * detalle.precio_unitario).quantize(
            DOS_DECIMALES, rounding=ROUND_HALF_UP
        )
        base_linea, iva_linea = _dividir_iva(total_linea, detalle.porcentaje_iva)

        producto = productos[detalle.producto_id]
        if producto.controla_stock:
            aplicar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.Tipo.DEVOLUCION,
                cantidad=cantidad,
                venta=venta,
                usuario=usuario,
                motivo=f"Nota crédito venta #{venta.pk}" + (f": {motivo}" if motivo else ""),
            )

        subtotal += base_linea
        total_iva += iva_linea
        total += total_linea

    nota.subtotal = subtotal
    nota.total_iva = total_iva
    nota.total = total
    nota.save(update_fields=["subtotal", "total_iva", "total"])
    return nota


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


def ventas_por_dia(ventas_qs):
    """Serie diaria de ventas dentro del rango de ``ventas_qs``. Las ventas
    anuladas no cuentan."""
    ventas_qs = ventas_qs.exclude(estado=Venta.Estado.ANULADA)
    filas = (
        ventas_qs.annotate(dia=TruncDate("creada_en"))
        .values("dia")
        .annotate(cantidad_ventas=Count("id"), total_vendido=Sum("total"))
        .order_by("dia")
    )
    return [
        {
            "dia": f["dia"],
            "cantidad_ventas": f["cantidad_ventas"],
            "total_vendido": f["total_vendido"],
        }
        for f in filas
    ]


def reporte_iva(*, empresa, desde=None, hasta=None):
    """Reporte de IVA del periodo: bruto (lo vendido), lo devuelto por notas
    crédito y el neto — desglosado por tarifa (el %IVA que tenía cada línea
    AL MOMENTO de venderse, no el actual del producto).

    Las notas crédito se filtran por SU PROPIA fecha, no por la de la venta
    original: una devolución de una venta de marzo hecha en abril baja el
    IVA de abril, no reabre el reporte de marzo.

    Nota: el desglose "por_tarifa" se recalcula línea a línea a partir de
    cantidad/precio_unitario/porcentaje_iva (no hay base/iva guardados por
    línea), así que puede diferir en centavos del ``total_iva`` ya
    redondeado y guardado en cada ``Venta`` — diferencia de redondeo
    normal e inevitable en un agregado, no un error de los totales.
    """
    ventas_qs = Venta.objects.filter(empresa=empresa).exclude(estado=Venta.Estado.ANULADA)
    notas_qs = NotaCredito.objects.filter(empresa=empresa)
    if desde:
        ventas_qs = ventas_qs.filter(creada_en__date__gte=desde)
        notas_qs = notas_qs.filter(creada_en__date__gte=desde)
    if hasta:
        ventas_qs = ventas_qs.filter(creada_en__date__lte=hasta)
        notas_qs = notas_qs.filter(creada_en__date__lte=hasta)

    decimal_field = DecimalField(max_digits=14, decimal_places=4)
    total_linea_expr = ExpressionWrapper(
        F("cantidad") * F("precio_unitario"), output_field=decimal_field
    )
    base_expr = ExpressionWrapper(
        total_linea_expr / (Decimal("1") + F("porcentaje_iva") / Decimal("100")),
        output_field=decimal_field,
    )

    por_tarifa = []
    bruto_subtotal = Decimal("0")
    bruto_total = Decimal("0")
    filas = (
        DetalleVenta.objects.filter(venta__in=ventas_qs)
        .values("porcentaje_iva")
        .annotate(base=Sum(base_expr), total=Sum(total_linea_expr))
        .order_by("porcentaje_iva")
    )
    for f in filas:
        base = (f["base"] or Decimal("0")).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
        total_tarifa = (f["total"] or Decimal("0")).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
        por_tarifa.append(
            {
                "porcentaje_iva": f["porcentaje_iva"],
                "base": base,
                "iva": total_tarifa - base,
                "total": total_tarifa,
            }
        )
        bruto_subtotal += base
        bruto_total += total_tarifa

    nc = notas_qs.aggregate(
        subtotal=Sum("subtotal"), total_iva=Sum("total_iva"), total=Sum("total")
    )
    nc_subtotal = nc["subtotal"] or Decimal("0")
    nc_iva = nc["total_iva"] or Decimal("0")
    nc_total = nc["total"] or Decimal("0")

    bruto_iva = bruto_total - bruto_subtotal
    return {
        "bruto": {"subtotal": bruto_subtotal, "total_iva": bruto_iva, "total": bruto_total},
        "notas_credito": {"subtotal": nc_subtotal, "total_iva": nc_iva, "total": nc_total},
        "neto": {
            "subtotal": bruto_subtotal - nc_subtotal,
            "total_iva": bruto_iva - nc_iva,
            "total": bruto_total - nc_total,
        },
        "por_tarifa": por_tarifa,
    }
