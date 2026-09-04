"""Única puerta de entrada para tocar el stock.

Cualquier cambio de ``Producto.stock_actual`` pasa por aquí: se registra el
movimiento en el kardex y se actualiza la foto de stock en la misma
transacción, con bloqueo de fila para soportar varias cajas vendiendo a la vez.
"""
from decimal import Decimal

from django.db import transaction

from ..models import MovimientoInventario, Producto


class StockNoControlado(Exception):
    """El producto tiene ``controla_stock = False``; no admite movimientos."""


@transaction.atomic
def aplicar_movimiento(
    *,
    producto: Producto,
    tipo: str,
    cantidad: Decimal,
    usuario=None,
    motivo: str = "",
    costo_unitario: Decimal | None = None,
    venta=None,
) -> MovimientoInventario:
    """Aplica un movimiento y devuelve el registro creado.

    ``cantidad`` va con signo (+ suma, - resta). Se permite que el stock
    quede negativo (sobreventa).
    """
    producto = Producto.objects.select_for_update().get(pk=producto.pk)

    if not producto.controla_stock:
        raise StockNoControlado(
            f"El producto {producto.codigo} no controla stock."
        )

    nuevo_stock = producto.stock_actual + cantidad
    movimiento = MovimientoInventario.objects.create(
        empresa_id=producto.empresa_id,
        producto=producto,
        tipo=tipo,
        cantidad=cantidad,
        stock_resultante=nuevo_stock,
        costo_unitario=costo_unitario,
        motivo=motivo,
        venta=venta,
        usuario=usuario,
    )
    producto.stock_actual = nuevo_stock
    producto.save(update_fields=["stock_actual"])
    return movimiento
