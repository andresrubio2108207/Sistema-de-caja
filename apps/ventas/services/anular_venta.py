from django.db import transaction
from django.utils import timezone

from apps.caja.models import TurnoCaja
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import aplicar_movimiento

from ..models import Venta
from .excepciones import AnulacionNoPermitida, VentaYaAnulada


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
