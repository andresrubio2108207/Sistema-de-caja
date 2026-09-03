from django.contrib import admin

from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "nit", "regimen_tributario", "activa", "creada_en")
    list_filter = ("activa", "regimen_tributario")
    search_fields = ("razon_social", "nombre_comercial", "nit")
