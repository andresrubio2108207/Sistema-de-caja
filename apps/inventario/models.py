from decimal import Decimal

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


class Producto(models.Model):
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="productos"
    )
    categoria = models.ForeignKey(
        "inventario.Categoria",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos",
    )
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=200)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2)
    porcentaje_iva = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("19.00")
    )
    stock_actual = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "codigo"], name="uq_producto_empresa_codigo"
            ),
        ]
        indexes = [
            models.Index(
                fields=["empresa", "activo"], name="ix_producto_empresa_activo"
            ),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"
