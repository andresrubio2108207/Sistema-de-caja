from django.db.models import ProtectedError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import (
    GestionCatalogo,
    GestionInventario,
    TieneEmpresaActiva,
)
from apps.empresas.mixins import EmpresaQuerysetMixin

from .models import Categoria, MovimientoInventario, Producto
from .serializers import (
    CategoriaSerializer,
    MovimientoInventarioSerializer,
    ProductoSerializer,
)

CATALOGO_PERMISSIONS = [IsAuthenticated, TieneEmpresaActiva, GestionCatalogo]


class RecursoProtegido(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El recurso tiene registros dependientes y no se puede eliminar."
    default_code = "protegido"


class CategoriaViewSet(EmpresaQuerysetMixin, viewsets.ModelViewSet):
    """CRUD de categorías, acotado a la empresa del usuario.

    Al eliminar una categoría, sus productos quedan sin categoría
    (``Producto.categoria`` es ``ON DELETE SET NULL``).
    """

    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaSerializer
    permission_classes = CATALOGO_PERMISSIONS


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
    permission_classes = CATALOGO_PERMISSIONS
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
