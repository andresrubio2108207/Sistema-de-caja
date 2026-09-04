from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import Usuario
from ..permissions import GestionUsuarios, TieneEmpresaActiva
from ..serializers import UsuarioSerializer


class UsuarioViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """Gestión del personal de la empresa. Solo el dueño.

    El queryset queda acotado a la empresa del usuario por
    ``EmpresaQuerysetMixin``; nunca aparecen usuarios de otro tenant ni el
    superusuario de plataforma (empresa nula).
    """

    queryset = Usuario.objects.all().order_by("id")
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionUsuarios]

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise ValidationError("No puedes eliminar tu propio usuario.")
        super().perform_destroy(instance)
