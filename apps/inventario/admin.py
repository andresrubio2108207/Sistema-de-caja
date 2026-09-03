from django.contrib import admin

from .models import Categoria, MovimientoInventario, Producto


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
    list_filter = ("empresa", "activo", "controla_stock", "categoria")
    search_fields = ("codigo", "nombre")


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = (
        "creado_en",
        "empresa",
        "producto",
        "tipo",
        "cantidad",
        "stock_resultante",
        "usuario",
    )
    list_filter = ("empresa", "tipo")
    search_fields = ("producto__codigo", "producto__nombre", "motivo")
    date_hierarchy = "creado_en"
    readonly_fields = [f.name for f in MovimientoInventario._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
