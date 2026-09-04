from django.db.models import ProtectedError
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.exceptions import RecursoProtegido
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import Cliente
from ..permissions import GestionClientes
from ..serializers import ClienteSerializer


class ClienteViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """CRUD de clientes, acotado a la empresa del usuario.

    Alta/edición: dueño y supervisor. El cajero solo consulta (selecciona un
    cliente existente al vender, o deja la venta como consumidor final).
    """

    queryset = Cliente.objects.all().order_by("nombre_completo")
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionClientes]
    filter_backends = [filters.SearchFilter]
    search_fields = ["numero_documento", "nombre_completo", "email"]

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise RecursoProtegido(
                "No se puede eliminar el cliente porque tiene ventas asociadas."
            )
