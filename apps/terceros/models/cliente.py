from django.db import models


class Cliente(models.Model):
    class TipoDocumento(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        NIT = "NIT", "NIT"
        CE = "CE", "Cédula de extranjería"
        PAS = "PAS", "Pasaporte"

    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="clientes"
    )
    tipo_documento = models.CharField(max_length=5, choices=TipoDocumento.choices)
    numero_documento = models.CharField(max_length=20)
    nombre_completo = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=50, blank=True)
    direccion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre_completo"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "numero_documento"],
                name="uq_cliente_empresa_documento",
            ),
        ]

    def __str__(self):
        return f"{self.nombre_completo} ({self.tipo_documento} {self.numero_documento})"
