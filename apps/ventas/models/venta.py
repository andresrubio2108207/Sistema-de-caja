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
        """Espejo de ``ventas.models.MedioPago`` + ``MIXTO``. Este campo es
        de solo lectura por API: lo calcula el servidor a partir de
        ``PagoVenta`` (un solo pago => ese medio; dos o más => MIXTO)."""

        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
        MIXTO = "MIXTO", "Mixto (dos o más medios)"

    class Estado(models.TextChoices):
        COMPLETADA = "completada", "Completada"
        ANULADA = "anulada", "Anulada"

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
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.COMPLETADA
    )
    motivo_anulacion = models.CharField(max_length=255, blank=True)
    anulada_en = models.DateTimeField(null=True, blank=True)
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
