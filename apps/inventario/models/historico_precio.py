from django.conf import settings
from django.db import models


class HistoricoPrecio(models.Model):
    """Registro append-only de cada cambio de ``Producto.precio_venta``.

    No lo escribe la API directamente: lo genera ``ProductoSerializer`` cada
    vez que un PATCH/PUT cambia el precio. Ventas pasadas no se ven
    afectadas (``DetalleVenta.precio_unitario`` ya es una foto propia); esto
    es solo para poder responder "¿cuándo y quién cambió el precio y a
    cuánto?"."""

    producto = models.ForeignKey(
        "inventario.Producto",
        on_delete=models.CASCADE,
        related_name="historico_precios",
    )
    precio_anterior = models.DecimalField(max_digits=12, decimal_places=2)
    precio_nuevo = models.DecimalField(max_digits=12, decimal_places=2)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cambios_precio",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "histórico de precio"
        verbose_name_plural = "histórico de precios"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(
                fields=["producto", "creado_en"], name="ix_histprecio_producto_creado"
            ),
        ]

    def __str__(self):
        return f"{self.producto_id}: {self.precio_anterior} -> {self.precio_nuevo}"
