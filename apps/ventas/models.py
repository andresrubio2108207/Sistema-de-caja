from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class MedioPago(models.TextChoices):
    """Instrumentos de pago reales (lo que puede tener una línea de
    ``PagoVenta``). Para agregar uno nuevo (QR, crédito, bono, ...) se agrega
    aquí Y como valor espejo en ``Venta.MedioPago`` (que además tiene
    ``MIXTO``, sintético, para el resumen de la venta)."""

    EFECTIVO = "EFECTIVO", "Efectivo"
    TARJETA = "TARJETA", "Tarjeta"
    TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"


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
    class Estado(models.TextChoices):
        COMPLETADA = "completada", "Completada"
        ANULADA = "anulada", "Anulada"

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

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.cantidad} x {self.producto_id} (venta {self.venta_id})"


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
