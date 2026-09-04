from decimal import Decimal

from rest_framework import serializers

from apps.inventario.models import Producto
from apps.terceros.models import Cliente

from .models import DetalleVenta, MedioPago, PagoVenta, Venta


class LineaVentaEntradaSerializer(serializers.Serializer):
    """Lo único que manda el cajero por línea: qué producto y cuánto. El
    precio SIEMPRE lo pone el servidor desde el catálogo (ver services.py)."""

    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    cantidad = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class PagoVentaEntradaSerializer(serializers.Serializer):
    """Una línea de pago. Varias líneas => venta MIXTO. La suma debe dar
    exactamente el total de la venta (se valida en services.py, una vez se
    conoce el total real calculado de las líneas)."""

    medio_pago = serializers.ChoiceField(choices=MedioPago.choices)
    monto = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class DetalleVentaSalidaSerializer(serializers.ModelSerializer):
    producto_codigo = serializers.CharField(source="producto.codigo", read_only=True)
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    total_linea = serializers.SerializerMethodField()

    class Meta:
        model = DetalleVenta
        fields = [
            "id",
            "producto",
            "producto_codigo",
            "producto_nombre",
            "cantidad",
            "precio_unitario",
            "total_linea",
        ]
        read_only_fields = fields

    def get_total_linea(self, obj) -> str:
        return str((obj.cantidad * obj.precio_unitario).quantize(Decimal("0.01")))


class PagoVentaSalidaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoVenta
        fields = ["id", "medio_pago", "monto"]
        read_only_fields = fields


class AnularVentaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255, required=False, allow_blank=True)


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


class VentaSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.none(), required=False, allow_null=True
    )
    cliente_nombre = serializers.CharField(
        source="cliente.nombre_completo", read_only=True, default=None
    )
    cajero_username = serializers.CharField(source="cajero.username", read_only=True)
    detalles = LineaVentaEntradaSerializer(many=True, write_only=True)
    lineas = DetalleVentaSalidaSerializer(many=True, read_only=True, source="detalles")
    pagos = PagoVentaEntradaSerializer(many=True, write_only=True)
    pagos_registrados = PagoVentaSalidaSerializer(many=True, read_only=True, source="pagos")

    class Meta:
        model = Venta
        fields = [
            "id",
            "turno",
            "cajero",
            "cajero_username",
            "cliente",
            "cliente_nombre",
            "medio_pago",
            "es_de_contado",
            "estado",
            "motivo_anulacion",
            "anulada_en",
            "subtotal",
            "total_iva",
            "total",
            "creada_en",
            "detalles",
            "lineas",
            "pagos",
            "pagos_registrados",
        ]
        read_only_fields = [
            "turno",
            "cajero",
            "medio_pago",
            "estado",
            "motivo_anulacion",
            "anulada_en",
            "subtotal",
            "total_iva",
            "total",
            "creada_en",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "empresa_id", None):
            self.fields["cliente"].queryset = Cliente.objects.filter(
                empresa=request.user.empresa
            )

    def validate_detalles(self, value):
        if not value:
            raise serializers.ValidationError("Debe incluir al menos un producto.")
        return value

    def validate_pagos(self, value):
        if not value:
            raise serializers.ValidationError("Debe incluir al menos un pago.")
        return value

    def validate(self, attrs):
        empresa = self.context["request"].user.empresa
        for linea in attrs.get("detalles", []):
            if linea["producto"].empresa_id != empresa.id:
                raise serializers.ValidationError(
                    {"detalles": "Hay un producto que no pertenece a tu empresa."}
                )
        return attrs
