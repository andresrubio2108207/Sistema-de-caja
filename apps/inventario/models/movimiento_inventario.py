from django.conf import settings
from django.db import models


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
