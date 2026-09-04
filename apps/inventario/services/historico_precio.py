"""Registro del histórico de cambios de precio. Extraído de
``ProductoSerializer.update()`` (antes vivía ahí) al reorganizar en capas —
mismo comportamiento exacto: solo deja constancia si el precio en verdad
cambió."""
from ..models import HistoricoPrecio, Producto


def registrar_cambio_precio(*, producto: Producto, precio_anterior, usuario=None):
    if producto.precio_venta == precio_anterior:
        return None
    return HistoricoPrecio.objects.create(
        producto=producto,
        precio_anterior=precio_anterior,
        precio_nuevo=producto.precio_venta,
        usuario=usuario,
    )
