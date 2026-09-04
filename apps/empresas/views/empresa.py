from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva

from ..permissions import ConfiguracionEmpresa
from ..serializers import MiEmpresaSerializer


class MiEmpresaView(RetrieveUpdateAPIView):
    """Consulta y edición de la configuración de la empresa propia. Solo dueño."""

    serializer_class = MiEmpresaSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, ConfiguracionEmpresa]

    def get_object(self):
        return self.request.user.empresa
