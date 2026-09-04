from decimal import Decimal

from django.conf import settings
from django.db import models


class NotaCredito(models.Model):
    """Devolución total o parcial de una venta YA COMPLETADA, en cualquier
    momento (no depende de que el turno siga abierto — para eso está
    ``Venta.anular``, que revierte TODO y solo funciona en el mismo turno).

    Devuelve stock (kardex ``devolucion``) por las cantidades indicadas en
    sus líneas y registra el ajuste monetario. **No** genera ningún
    documento DIAN — eso es responsabilidad del módulo de facturación
    (diferido); esto es la contabilidad interna del POS.
    """

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.PROTECT, related_name="notas_credito"
    )
    venta = models.ForeignKey(
        "ventas.Venta", on_delete=models.PROTECT, related_name="notas_credito"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notas_credito",
    )
    motivo = models.CharField(max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_iva = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "nota crédito"
        verbose_name_plural = "notas crédito"
        ordering = ["-creada_en"]
        indexes = [
            models.Index(
                fields=["empresa", "creada_en"], name="ix_notacred_empresa_creada"
            ),
        ]

    def __str__(self):
        return f"NC venta #{self.venta_id} — {self.total}"
