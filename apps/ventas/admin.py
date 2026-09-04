from django.contrib import admin

from .models import DetalleVenta, PagoVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0


class PagoVentaInline(admin.TabularInline):
    model = PagoVenta
    extra = 0


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "empresa",
        "turno",
        "cajero",
        "cliente",
        "medio_pago",
        "total",
        "creada_en",
    )
    list_filter = ("empresa", "medio_pago", "es_de_contado")
    date_hierarchy = "creada_en"
    inlines = [DetalleVentaInline, PagoVentaInline]
