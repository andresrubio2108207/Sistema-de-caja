from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate

from ..models import DetalleVenta, NotaCredito, PagoVenta, Venta
from .comun import DOS_DECIMALES


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
