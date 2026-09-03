from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuario del sistema. Extiende el ``AbstractUser`` de Django.

    Hoy se asume **1 usuario = 1 empresa**. Si en el futuro un mismo usuario
    debe pertenecer a varias empresas, esto pasa a una tabla intermedia
    ``Membresia(usuario, empresa, rol)`` (ver pendientes del prompt maestro).
    """

    class Rol(models.TextChoices):
        DUENO = "dueno", "Dueño"
        SUPERVISOR = "supervisor", "Supervisor"
        CAJERO = "cajero", "Cajero"

    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="usuarios",
        help_text="NULL solo para superusuario de plataforma/soporte.",
    )
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CAJERO)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_username()
