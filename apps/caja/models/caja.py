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
