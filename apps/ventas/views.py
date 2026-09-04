from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cuentas.models import Usuario
from apps.cuentas.permissions import (
    GestionNotasCredito,
    OperacionCaja,
    TieneEmpresaActiva,
    VerReportes,
)
from apps.empresas.mixins import EmpresaQuerysetMixin

from .models import NotaCredito, Venta
from .serializers import (
    AnularVentaSerializer,
    NotaCreditoSerializer,
    TicketSerializer,
    VentaSerializer,
)
from .services import (
    AnulacionNoPermitida,
    NotaCreditoInvalida,
    PagoInvalido,
    ProductoInvalido,
    TurnoNoAbierto,
    VentaYaAnulada,
    anular_venta,
    emitir_nota_credito,
    productos_mas_vendidos,
    registrar_venta,
    reporte_iva,
    resumen_de_ventas,
    ventas_por_cajero,
    ventas_por_dia,
)


class VentaViewSet(
    EmpresaQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Registro de ventas. Una venta ya creada no se edita ni se borra
    (sin PUT/PATCH/DELETE) — la única forma de revertirla es
    ``POST /{id}/anular/``, que devuelve el stock y la marca ``anulada``
    sin borrar el registro (queda como historial).

    Filtros: ``?turno=<id>``, ``?medio_pago=``, ``?cliente=<id>``,
    ``?estado=completada|anulada``, ``?desde=YYYY-MM-DD``, ``?hasta=YYYY-MM-DD``.
    """

    queryset = Venta.objects.select_related("cliente", "turno", "cajero").prefetch_related(
        "detalles__producto"
    )
    serializer_class = VentaSerializer
    permission_classes = [IsAuthenticated, TieneEmpresaActiva, OperacionCaja]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-creada_en"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if turno := params.get("turno"):
            qs = qs.filter(turno_id=turno)
        if medio_pago := params.get("medio_pago"):
            qs = qs.filter(medio_pago=medio_pago)
        if cliente := params.get("cliente"):
            qs = qs.filter(cliente_id=cliente)
        if estado := params.get("estado"):
            qs = qs.filter(estado=estado)
        if desde := params.get("desde"):
            qs = qs.filter(creada_en__date__gte=desde)
        if hasta := params.get("hasta"):
            qs = qs.filter(creada_en__date__lte=hasta)
        return qs

    def perform_create(self, serializer):
        request = self.request
        data = serializer.validated_data
        try:
            venta = registrar_venta(
                empresa=request.user.empresa,
                cajero=request.user,
                cliente=data.get("cliente"),
                es_de_contado=data.get("es_de_contado", True),
                lineas=data["detalles"],
                pagos=data["pagos"],
            )
        except (TurnoNoAbierto, ProductoInvalido, PagoInvalido) as exc:
            raise ValidationError(str(exc))
        serializer.instance = venta

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula la venta completa: devuelve el stock y la marca anulada.
        Solo mientras el turno de la venta siga abierto. Un cajero solo
        puede anular ventas de SU turno; dueño/supervisor, cualquiera."""
        venta = self.get_object()
        es_cajero = getattr(request.user, "rol", None) == Usuario.Rol.CAJERO
        if es_cajero and venta.cajero_id != request.user.id:
            raise PermissionDenied("Solo puedes anular ventas de tu propio turno.")

        entrada = AnularVentaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            venta = anular_venta(
                venta=venta,
                usuario=request.user,
                motivo=entrada.validated_data.get("motivo", ""),
            )
        except (VentaYaAnulada, AnulacionNoPermitida) as exc:
            raise ValidationError(str(exc))

        salida = self.get_serializer(venta)
        return Response(salida.data)

    @action(detail=True, methods=["get"])
    def ticket(self, request, pk=None):
        """Contenido completo del comprobante, listo para que el POS lo
        formatee e imprima (58/80mm, PDF, lo que sea del lado del cliente).
        No genera bytes de impresora: eso es integración específica de cada
        terminal/impresora, fuera del alcance de este backend."""
        venta = self.get_object()
        return Response(TicketSerializer(venta).data)

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        """Pequeño reporte contable: total vendido y desglose por medio de
        pago (a partir de los pagos reales, no de Venta.medio_pago, para que
        una venta MIXTO reparta bien), en el rango
        ``?desde=``/``?hasta=`` (por defecto, todo). Las ventas anuladas
        nunca cuentan aquí."""
        qs = self.filter_queryset(self.get_queryset())
        resumen = resumen_de_ventas(qs)
        return Response(
            {
                "desde": request.query_params.get("desde"),
                "hasta": request.query_params.get("hasta"),
                **resumen,
            }
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="productos-mas-vendidos",
        url_name="productos-mas-vendidos",
        permission_classes=[IsAuthenticated, TieneEmpresaActiva, VerReportes],
    )
    def productos_mas_vendidos_view(self, request):
        """Ranking de productos por cantidad vendida. ``?desde=``/``?hasta=``
        filtran el rango; ``?limite=`` (default 10) recorta el ranking."""
        qs = self.filter_queryset(self.get_queryset())
        try:
            limite = int(request.query_params.get("limite", 10))
        except ValueError:
            limite = 10
        return Response(
            {
                "desde": request.query_params.get("desde"),
                "hasta": request.query_params.get("hasta"),
                "productos": productos_mas_vendidos(qs, limite=limite),
            }
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="por-cajero",
        permission_classes=[IsAuthenticated, TieneEmpresaActiva, VerReportes],
    )
    def por_cajero(self, request):
        """Desempeño de ventas por cajero. ``?desde=``/``?hasta=`` filtran
        el rango."""
        qs = self.filter_queryset(self.get_queryset())
        return Response(
            {
                "desde": request.query_params.get("desde"),
                "hasta": request.query_params.get("hasta"),
                "cajeros": ventas_por_cajero(qs),
            }
        )

    @action(detail=False, methods=["get"], url_path="por-dia")
    def por_dia(self, request):
        """Serie diaria de ventas. ``?desde=``/``?hasta=`` filtran el rango."""
        qs = self.filter_queryset(self.get_queryset())
        return Response(
            {
                "desde": request.query_params.get("desde"),
                "hasta": request.query_params.get("hasta"),
                "dias": ventas_por_dia(qs),
            }
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="reporte-iva",
        url_name="reporte-iva",
        permission_classes=[IsAuthenticated, TieneEmpresaActiva, VerReportes],
    )
    def reporte_iva_view(self, request):
        """IVA bruto vendido, lo devuelto por notas crédito y el neto del
        periodo, desglosado por tarifa. ``?desde=``/``?hasta=`` filtran el
        rango (por fecha de cada documento, no de la venta original)."""
        reporte = reporte_iva(
            empresa=request.user.empresa,
            desde=request.query_params.get("desde"),
            hasta=request.query_params.get("hasta"),
        )
        return Response(
            {
                "desde": request.query_params.get("desde"),
                "hasta": request.query_params.get("hasta"),
                **reporte,
            }
        )


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
