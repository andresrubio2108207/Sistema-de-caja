from django.contrib import admin

from .models import Factura


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "empresa",
        "venta",
        "estado",
        "numero_factura",
        "cufe",
        "creada_en",
        "actualizada_en",
    )
    list_filter = ("empresa", "estado", "proveedor_usado")
    search_fields = ("numero_factura", "cufe")
    readonly_fields = ("creada_en", "actualizada_en")
