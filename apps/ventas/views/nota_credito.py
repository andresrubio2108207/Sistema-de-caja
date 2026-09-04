from rest_framework import filters, mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.cuentas.permissions import TieneEmpresaActiva
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import NotaCredito
from ..permissions import GestionNotasCredito
from ..serializers import NotaCreditoSerializer
from ..services import NotaCreditoInvalida, emitir_nota_credito


class NotaCreditoViewSet(
    EmpresaQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Devoluciones (nota crédito), totales o parciales, de una venta
    completada — funciona con el turno abierto o cerrado (a diferencia de
    ``Venta.anular``, que solo funciona en el mismo turno). Solo alta y
    consulta: inmutable. Dueño y supervisor únicamente.

    Filtros: ``?venta=<id>``.
    """

    queryset = NotaCredito.objects.select_related("venta", "usuario").prefetch_related(
        "lineas__detalle_venta__producto"
    )
    serializer_class = NotaCreditoSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, GestionNotasCredito]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-creada_en"]

    def get_queryset(self):
        qs = super().get_queryset()
        if venta := self.request.query_params.get("venta"):
            qs = qs.filter(venta_id=venta)
        return qs

    def perform_create(self, serializer):
        data = serializer.validated_data
        try:
            nota = emitir_nota_credito(
                venta=data["venta"],
                usuario=self.request.user,
                motivo=data.get("motivo", ""),
                lineas=data["lineas"],
            )
        except NotaCreditoInvalida as exc:
            raise ValidationError(str(exc))
        serializer.instance = nota
