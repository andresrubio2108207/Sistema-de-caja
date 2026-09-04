from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cuentas.models import Usuario
from apps.cuentas.permissions import OperacionCaja, TieneEmpresaActiva
from apps.empresas.mixins import EmpresaQuerysetMixin

from ..models import TurnoCaja
from ..serializers import CerrarTurnoSerializer, TurnoCajaSerializer
from ..services import CajaOcupada, TurnoYaAbierto, TurnoYaCerrado, abrir_turno, cerrar_turno


class TurnoCajaViewSet(
    EmpresaQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Apertura/cierre de turno con arqueo.

    ``POST /turnos/`` abre un turno (el cajero siempre es quien hace la
    petición, no un campo del body). ``POST /turnos/{id}/cerrar/`` lo cierra
    y calcula el saldo esperado en efectivo. Filtros: ``?estado=`` ,
    ``?caja=<id>``.
    """

    queryset = TurnoCaja.objects.select_related("caja", "cajero").all()
    serializer_class = TurnoCajaSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, OperacionCaja]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-abierto_en"]

    def get_queryset(self):
        qs = super().get_queryset()
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        caja = self.request.query_params.get("caja")
        if caja:
            qs = qs.filter(caja_id=caja)
        return qs

    def perform_create(self, serializer):
        request = self.request
        try:
            turno = abrir_turno(
                empresa=request.user.empresa,
                caja=serializer.validated_data["caja"],
                cajero=request.user,
                saldo_inicial=serializer.validated_data["saldo_inicial"],
            )
        except (CajaOcupada, TurnoYaAbierto) as exc:
            raise ValidationError(str(exc))
        serializer.instance = turno

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        turno = self.get_object()
        es_cajero = getattr(request.user, "rol", None) == Usuario.Rol.CAJERO
        if es_cajero and turno.cajero_id != request.user.id:
            raise PermissionDenied("Solo el cajero dueño del turno puede cerrarlo.")

        entrada = CerrarTurnoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            turno = cerrar_turno(turno, entrada.validated_data["saldo_final_declarado"])
        except TurnoYaCerrado as exc:
            raise ValidationError(str(exc))

        salida = self.get_serializer(turno)
        return Response(salida.data)
