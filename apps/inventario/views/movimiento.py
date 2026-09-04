from rest_framework import filters, mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import MovimientoInventario
from ..permissions import GestionInventario
from ..serializers import MovimientoInventarioSerializer


class MovimientoInventarioViewSet(
    EmpresaQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Kardex de inventario. Solo alta y consulta — los movimientos son
    inmutables (sin PUT/PATCH/DELETE).

    Alta: dueño y supervisor. Tipos por API: ``entrada``, ``ajuste``,
    ``devolucion``, ``salida`` (``venta`` la genera el flujo de ventas).
    Filtros: ``?producto=<id>``, ``?tipo=<tipo>``,
    ``?ordering=creado_en|cantidad``.
    """

    queryset = MovimientoInventario.objects.select_related("producto").all()
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionInventario]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["creado_en", "cantidad"]
    ordering = ["-creado_en", "-id"]

    def get_queryset(self):
        qs = super().get_queryset()
        producto = self.request.query_params.get("producto")
        if producto:
            qs = qs.filter(producto_id=producto)
        tipo = self.request.query_params.get("tipo")
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs
