from django.contrib import admin

from .models import Caja, TurnoCaja


@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "activa")
    list_filter = ("empresa", "activa")
    search_fields = ("nombre",)


@admin.register(TurnoCaja)
class TurnoCajaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "empresa",
        "caja",
        "cajero",
        "estado",
        "abierto_en",
        "cerrado_en",
    )
    list_filter = ("empresa", "estado")
    date_hierarchy = "abierto_en"
