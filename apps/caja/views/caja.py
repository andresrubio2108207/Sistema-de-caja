from django.db.models import ProtectedError
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.exceptions import RecursoProtegido
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import Caja
from ..permissions import GestionCajas
from ..serializers import CajaSerializer


class CajaViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """CRUD de cajas (terminales físicas). Crea/edita el dueño; los demás
    roles solo consultan cuáles existen."""

    queryset = Caja.objects.all().order_by("nombre")
    serializer_class = CajaSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionCajas]
    filter_backends = [filters.OrderingFilter]

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise RecursoProtegido(
                "No se puede eliminar la caja porque tiene turnos asociados. "
                "Desactívala (activa=false) en su lugar."
            )
