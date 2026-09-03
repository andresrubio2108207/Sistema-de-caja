from decimal import Decimal

from django.conf import settings
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


class MovimientoInventario(models.Model):
    """Libro (kardex) de inventario. Append-only: una corrección es un
    movimiento nuevo, nunca un UPDATE/DELETE.

    Convención de signo de ``cantidad``: positivo suma al stock, negativo
    resta. ``entrada``/``devolucion`` van en positivo, ``venta``/``salida``
    en negativo, ``ajuste`` en cualquiera de los dos.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada de mercancía"
        VENTA = "venta", "Salida por venta"
        AJUSTE = "ajuste", "Ajuste de inventario"
        DEVOLUCION = "devolucion", "Devolución de cliente"
        SALIDA = "salida", "Salida (merma / daño / otro)"

    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.CASCADE,
        related_name="movimientos_inventario",
    )
    producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.PROTECT,
        related_name="movimientos",
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Con signo: + suma al stock, - resta. Ej.: venta de 2 => -2.",
    )
    stock_resultante = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Stock del producto justo después de aplicar este movimiento.",
    )
    costo_unitario = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    motivo = models.CharField(max_length=255, blank=True)
    venta = models.ForeignKey(
        "ventas.Venta",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_inventario",
        help_text="Origen del movimiento cuando nace de una venta.",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos_inventario",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(
                fields=["empresa", "creado_en"], name="ix_movinv_empresa_creado"
            ),
            models.Index(
                fields=["producto", "creado_en"], name="ix_movinv_producto_creado"
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad:+} ({self.producto_id})"
