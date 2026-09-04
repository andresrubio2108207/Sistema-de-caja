from rest_framework import serializers

from ..models import MovimientoInventario, Producto
from ..services import aplicar_movimiento


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.none())

    class Meta:
        model = MovimientoInventario
        fields = [
            "id",
            "producto",
            "tipo",
            "cantidad",
            "stock_resultante",
            "costo_unitario",
            "motivo",
            "venta",
            "usuario",
            "creado_en",
        ]
        read_only_fields = ["stock_resultante", "venta", "usuario", "creado_en"]

    # Reglas de signo por tipo. `venta` no se admite por API.
    _SIGNO = {
        MovimientoInventario.Tipo.ENTRADA: "positivo",
        MovimientoInventario.Tipo.DEVOLUCION: "positivo",
        MovimientoInventario.Tipo.SALIDA: "negativo",
        MovimientoInventario.Tipo.AJUSTE: "cualquiera",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "empresa_id", None):
            self.fields["producto"].queryset = Producto.objects.filter(
                empresa=request.user.empresa
            )

    def validate_tipo(self, value):
        if value == MovimientoInventario.Tipo.VENTA:
            raise serializers.ValidationError(
                "Los movimientos de venta los genera el flujo de ventas, no la API."
            )
        return value

    def validate(self, attrs):
        producto = attrs["producto"]
        if not producto.controla_stock:
            raise serializers.ValidationError(
                {"producto": "Este producto no controla stock."}
            )
        tipo = attrs["tipo"]
        cantidad = attrs["cantidad"]
        signo = self._SIGNO.get(tipo)
        if cantidad == 0:
            raise serializers.ValidationError({"cantidad": "No puede ser cero."})
        if signo == "positivo" and cantidad < 0:
            raise serializers.ValidationError(
                {"cantidad": f"Un movimiento '{tipo}' debe ser positivo."}
            )
        if signo == "negativo" and cantidad > 0:
            raise serializers.ValidationError(
                {"cantidad": f"Un movimiento '{tipo}' debe ser negativo."}
            )
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        return aplicar_movimiento(
            producto=validated_data["producto"],
            tipo=validated_data["tipo"],
            cantidad=validated_data["cantidad"],
            costo_unitario=validated_data.get("costo_unitario"),
            motivo=validated_data.get("motivo", ""),
            usuario=getattr(request, "user", None),
        )
