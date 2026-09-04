from django.db import models


class Categoria(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="categorias"
    )
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nombre"], name="uq_categoria_empresa_nombre"
            ),
        ]

    def __str__(self):
        return self.nombre
