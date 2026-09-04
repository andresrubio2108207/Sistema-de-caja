from django.db import models


class MedioPago(models.TextChoices):
    """Instrumentos de pago reales (lo que puede tener una línea de
    ``PagoVenta``). Para agregar uno nuevo (QR, crédito, bono, ...) se agrega
    aquí Y como valor espejo en ``Venta.MedioPago`` (que además tiene
    ``MIXTO``, sintético, para el resumen de la venta)."""

    EFECTIVO = "EFECTIVO", "Efectivo"
    TARJETA = "TARJETA", "Tarjeta"
    TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
