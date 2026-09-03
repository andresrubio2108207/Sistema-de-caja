from django.contrib import admin

from .models import Categoria, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa")
    list_filter = ("empresa",)
    search_fields = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "nombre",
        "empresa",
        "precio_venta",
        "porcentaje_iva",
        "stock_actual",
        "activo",
    )
    list_filter = ("empresa", "activo", "categoria")
    search_fields = ("codigo", "nombre")
