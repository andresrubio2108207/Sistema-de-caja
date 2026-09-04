from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
    precio_venta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="YA incluye IVA (precio al público). No es la base gravable.",
    )
    porcentaje_iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("19.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="0 para productos exentos/excluidos. Tarifa real de ESTE producto.",
    )
    stock_actual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text=(
            "Foto del stock. Solo lo escribe el servicio de movimientos "
            "(apps.inventario.services.aplicar_movimiento), nunca la API."
        ),
    )
    controla_stock = models.BooleanField(
        default=True,
        help_text=(
            "Si es False (servicios, recargas) el producto no genera ni "
            "valida movimientos de inventario."
        ),
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
