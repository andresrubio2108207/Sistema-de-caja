from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import Categoria
from ..permissions import GestionCatalogo
from ..serializers import CategoriaSerializer


class CategoriaViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """CRUD de categorías, acotado a la empresa del usuario.

    Al eliminar una categoría, sus productos quedan sin categoría
    (``Producto.categoria`` es ``ON DELETE SET NULL``).
    """

    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionCatalogo]
