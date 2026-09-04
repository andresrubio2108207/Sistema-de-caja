from rest_framework import serializers

from ..models import Venta
from .venta import DetalleVentaSalidaSerializer, PagoVentaSalidaSerializer


class TicketEmpresaSerializer(serializers.Serializer):
    """Membrete: lo mínimo que un ticket impreso debe mostrar de la empresa."""

    razon_social = serializers.CharField()
    nombre_comercial = serializers.CharField()
    nit = serializers.CharField()
    digito_verificacion = serializers.CharField()
    direccion = serializers.CharField()
    ciudad = serializers.CharField()
    telefono = serializers.CharField()
    regimen_tributario = serializers.CharField(source="get_regimen_tributario_display")


class TicketSerializer(serializers.ModelSerializer):
    """Todo lo que hace falta para imprimir el comprobante de una venta —
    para que el cliente (terminal/POS) no tenga que combinar 3 endpoints.
    Es de solo lectura."""

    empresa = TicketEmpresaSerializer(read_only=True)
    caja_nombre = serializers.CharField(source="turno.caja.nombre", read_only=True)
    cajero_username = serializers.CharField(source="cajero.username", read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    detalles = DetalleVentaSalidaSerializer(many=True, read_only=True)
    pagos = PagoVentaSalidaSerializer(many=True, read_only=True)

    class Meta:
        model = Venta
        fields = [
            "id",
            "empresa",
            "caja_nombre",
            "cajero_username",
            "cliente_nombre",
            "medio_pago",
            "estado",
            "subtotal",
            "total_iva",
            "total",
            "creada_en",
            "detalles",
            "pagos",
        ]
        read_only_fields = fields

    def get_cliente_nombre(self, obj) -> str:
        return obj.cliente.nombre_completo if obj.cliente_id else "Consumidor final"
