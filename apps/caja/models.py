from django.conf import settings
from django.db import models


class Caja(models.Model):
    """Terminal / punto de cobro físico. Una empresa puede tener varias
    operando simultáneamente."""

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="cajas"
    )
    nombre = models.CharField(max_length=50)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "caja"
        verbose_name_plural = "cajas"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nombre"], name="uq_caja_empresa_nombre"
            ),
        ]

    def __str__(self):
        return self.nombre


class TurnoCaja(models.Model):
    """Apertura / cierre de caja con arqueo.

    ``empresa`` está denormalizada desde ``caja`` a propósito, para que
    "todos los turnos de esta empresa" sea un filtro indexado de una tabla.
    """

    class Estado(models.TextChoices):
        ABIERTO = "abierto", "Abierto"
        CERRADO = "cerrado", "Cerrado"

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="turnos"
    )
    caja = models.ForeignKey(
        "caja.Caja", on_delete=models.PROTECT, related_name="turnos"
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos"
    )
    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.ABIERTO
    )
    saldo_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_final_declarado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Lo que el cajero cuenta físicamente al cerrar.",
    )
    saldo_final_calculado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Lo que el sistema calcula a partir de las ventas del turno.",
    )
    abierto_en = models.DateTimeField(auto_now_add=True)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "turno de caja"
        verbose_name_plural = "turnos de caja"
        ordering = ["-abierto_en"]
        indexes = [
            models.Index(
                fields=["empresa", "estado"], name="ix_turno_empresa_estado"
            ),
        ]

    def __str__(self):
        return f"Turno {self.caja} — {self.get_estado_display()}"
