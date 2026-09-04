from django.db.models import ProtectedError
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.exceptions import RecursoProtegido
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import Producto
from ..permissions import GestionCatalogo
from ..serializers import HistoricoPrecioSerializer, ProductoSerializer


class ProductoViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """CRUD de productos, acotado a la empresa del usuario.

    Filtros: ``?activo=true|false``, ``?categoria=<id>``, ``?search=<texto>``
    (código o nombre), ``?ordering=nombre|codigo|precio_venta|...``.

    ``stock_actual`` es de solo lectura: se mueve con
    ``/api/movimientos-inventario/``. Eliminar un producto con ventas o
    movimientos asociados devuelve 409: en ese caso se desactiva
    (``activo=false``), no se borra.
    """

    queryset = Producto.objects.select_related("categoria").all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionCatalogo]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["codigo", "nombre"]
    ordering_fields = ["nombre", "codigo", "precio_venta", "stock_actual", "creado_en"]
    ordering = ["nombre"]

    _VERDADERO = {"1", "true", "t", "si", "sí", "yes"}
    _FALSO = {"0", "false", "f", "no"}

    def get_queryset(self):
        qs = super().get_queryset()
        activo = self.request.query_params.get("activo")
        if activo is not None:
            valor = activo.strip().lower()
            if valor in self._VERDADERO:
                qs = qs.filter(activo=True)
            elif valor in self._FALSO:
                qs = qs.filter(activo=False)
        categoria = self.request.query_params.get("categoria")
        if categoria:
            qs = qs.filter(categoria_id=categoria)
        return qs

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise RecursoProtegido(
                "No se puede eliminar el producto porque tiene ventas o "
                "movimientos de inventario asociados. Desactívalo "
                "(activo=false) en su lugar."
            )

    @action(detail=True, methods=["get"], url_path="historico-precios")
    def historico_precios(self, request, pk=None):
        """Cada cambio de ``precio_venta`` de este producto: quién, cuándo,
        de cuánto a cuánto. Se genera solo (ver ProductoSerializer.update)."""
        producto = self.get_object()
        historico = producto.historico_precios.select_related("usuario").all()
        return Response(HistoricoPrecioSerializer(historico, many=True).data)
