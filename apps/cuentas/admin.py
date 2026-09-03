from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Empresa y rol", {"fields": ("empresa", "rol")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Empresa y rol", {"fields": ("empresa", "rol")}),
    )
    list_display = ("username", "email", "empresa", "rol", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff", "empresa")
    search_fields = ("username", "email", "first_name", "last_name")
