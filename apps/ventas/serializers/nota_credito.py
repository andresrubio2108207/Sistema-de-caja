from decimal import Decimal

from rest_framework import serializers

from ..models import DetalleVenta, LineaNotaCredito, NotaCredito, Venta


class LineaNotaCreditoEntradaSerializer(serializers.Serializer):
    """``detalle_venta`` es el id de la línea original de la venta (lo que
    trae ``VentaSerializer.lineas[].id``)."""

    detalle_venta = serializers.PrimaryKeyRelatedField(queryset=DetalleVenta.objects.all())
    cantidad = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class LineaNotaCreditoSalidaSerializer(serializers.ModelSerializer):
    producto_codigo = serializers.CharField(
        source="detalle_venta.producto.codigo", read_only=True
    )
    producto_nombre = serializers.CharField(
        source="detalle_venta.producto.nombre", read_only=True
    )

    class Meta:
        model = LineaNotaCredito
        fields = ["id", "detalle_venta", "producto_codigo", "producto_nombre", "cantidad"]
        read_only_fields = fields


class NotaCreditoSerializer(serializers.ModelSerializer):
    venta = serializers.PrimaryKeyRelatedField(queryset=Venta.objects.none())
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    lineas = LineaNotaCreditoEntradaSerializer(many=True, write_only=True)
    lineas_registradas = LineaNotaCreditoSalidaSerializer(
        many=True, read_only=True, source="lineas"
    )

    class Meta:
        model = NotaCredito
        fields = [
            "id",
            "venta",
            "usuario",
            "usuario_username",
            "motivo",
            "subtotal",
            "total_iva",
            "total",
            "creada_en",
            "lineas",
            "lineas_registradas",
        ]
        read_only_fields = ["usuario", "subtotal", "total_iva", "total", "creada_en"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "empresa_id", None):
            self.fields["venta"].queryset = Venta.objects.filter(
                empresa=request.user.empresa
            )

    def validate_lineas(self, value):
        if not value:
            raise serializers.ValidationError("Debe incluir al menos una línea.")
        return value

    def validate(self, attrs):
        venta = attrs["venta"]
        for linea in attrs["lineas"]:
            if linea["detalle_venta"].venta_id != venta.id:
                raise serializers.ValidationError(
                    {"lineas": "Hay una línea que no pertenece a la venta indicada."}
                )
        return attrs
