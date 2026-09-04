from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from .choices import MedioPago


class PagoVenta(models.Model):
    """Una línea de pago de una venta. Una venta con un solo pago es
    ``EFECTIVO``/``TARJETA``/``TRANSFERENCIA``; con dos o más, la venta queda
    marcada ``MIXTO`` (ej.: $50.000 = $20.000 efectivo + $30.000 tarjeta).

    No lleva ``empresa`` propia: se resuelve vía ``venta``. La suma de los
    pagos de una venta siempre es igual a ``Venta.total`` (se valida al
    registrar la venta, en ``services.registrar_venta``)."""

    venta = models.ForeignKey(
        "ventas.Venta", on_delete=models.CASCADE, related_name="pagos"
    )
    medio_pago = models.CharField(max_length=20, choices=MedioPago.choices)
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        verbose_name = "pago de venta"
        verbose_name_plural = "pagos de venta"

    def __str__(self):
        return f"{self.medio_pago} {self.monto} (venta {self.venta_id})"
