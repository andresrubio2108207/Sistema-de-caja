from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class LineaNotaCredito(models.Model):
    """No lleva ``empresa`` propia: se resuelve vía ``nota_credito``."""

    nota_credito = models.ForeignKey(
        "ventas.NotaCredito", on_delete=models.CASCADE, related_name="lineas"
    )
    detalle_venta = models.ForeignKey(
        "ventas.DetalleVenta",
        on_delete=models.PROTECT,
        related_name="devoluciones",
        help_text="La línea original de la venta que se está devolviendo.",
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Cuánto de esa línea se devuelve (puede ser parcial).",
    )

    class Meta:
        verbose_name = "línea de nota crédito"
        verbose_name_plural = "líneas de nota crédito"

    def __str__(self):
        return f"{self.cantidad} de detalle {self.detalle_venta_id}"
