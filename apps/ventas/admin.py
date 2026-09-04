from django.contrib import admin

from .models import DetalleVenta, LineaNotaCredito, NotaCredito, PagoVenta, Venta


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
        "estado",
        "total",
        "creada_en",
    )
    list_filter = ("empresa", "medio_pago", "estado", "es_de_contado")
    date_hierarchy = "creada_en"
    inlines = [DetalleVentaInline, PagoVentaInline]


class LineaNotaCreditoInline(admin.TabularInline):
    model = LineaNotaCredito
    extra = 0


@admin.register(NotaCredito)
class NotaCreditoAdmin(admin.ModelAdmin):
    list_display = ("id", "empresa", "venta", "usuario", "total", "creada_en")
    list_filter = ("empresa",)
    date_hierarchy = "creada_en"
    inlines = [LineaNotaCreditoInline]
