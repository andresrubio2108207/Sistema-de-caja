from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class DetalleVenta(models.Model):
    """No lleva ``empresa`` propia: se resuelve siempre vía ``venta``."""

    venta = models.ForeignKey(
        "ventas.Venta", on_delete=models.CASCADE, related_name="detalles"
    )
    producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="detalles_venta"
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    porcentaje_iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("19.00"),
        help_text=(
            "Foto del %IVA del producto al momento de la venta. Necesaria "
            "para reportes de IVA correctos: si el IVA del producto cambia "
            "después, esta línea no debe verse afectada."
        ),
    )

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.cantidad} x {self.producto_id} (venta {self.venta_id})"
