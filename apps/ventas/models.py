from decimal import Decimal

from django.conf import settings
from django.db import models


class Venta(models.Model):
    """Venta cerrada en caja. Se registra de inmediato; la factura electrónica
    se emite después en background vía Celery (ver app ``facturacion``).

    Relaciones financieras en ``PROTECT``: nunca se borra en cascada algo con
    historial.
    """

    class MedioPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
        MIXTO = "MIXTO", "Mixto"

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="ventas"
    )
    turno = models.ForeignKey(
        "caja.TurnoCaja", on_delete=models.PROTECT, related_name="ventas"
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ventas"
    )
    cliente = models.ForeignKey(
        "terceros.Cliente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ventas",
        help_text="NULL = consumidor final.",
    )
    medio_pago = models.CharField(max_length=20, choices=MedioPago.choices)
    es_de_contado = models.BooleanField(default=True)
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    total_iva = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-creada_en"]
        indexes = [
            models.Index(
                fields=["empresa", "creada_en"], name="ix_venta_empresa_creada"
            ),
        ]

    def __str__(self):
        return f"Venta #{self.pk} — {self.total}"


class DetalleVenta(models.Model):
    """No lleva ``empresa`` propia: se resuelve siempre vía ``venta``."""

    venta = models.ForeignKey(
        "ventas.Venta", on_delete=models.CASCADE, related_name="detalles"
    )
    producto = models.ForeignKey(
        "inventario.Producto", on_delete=models.PROTECT, related_name="detalles_venta"
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.cantidad} x {self.producto_id} (venta {self.venta_id})"
