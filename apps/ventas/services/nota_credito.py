from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from apps.inventario.models import MovimientoInventario, Producto
from apps.inventario.services import aplicar_movimiento

from ..models import LineaNotaCredito, NotaCredito, Venta
from .comun import DOS_DECIMALES, _dividir_iva
from .excepciones import NotaCreditoInvalida


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
