from decimal import Decimal

from rest_framework import serializers

from .models import Categoria, MovimientoInventario, Producto
from .services import aplicar_movimiento


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre"]

    def _empresa(self):
        return self.context["request"].user.empresa

    def validate_nombre(self, value):
        qs = Categoria.objects.filter(empresa=self._empresa(), nombre=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una categoría con ese nombre en tu empresa."
            )
        return value


class ProductoSerializer(serializers.ModelSerializer):
    categoria = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.none(), required=False, allow_null=True
    )
    categoria_nombre = serializers.CharField(
        source="categoria.nombre", read_only=True, default=None
    )
    # stock_actual es de solo lectura: se mueve vía movimientos de inventario.
    # stock_inicial (opcional, solo al crear) dispara un movimiento `entrada`.
    stock_inicial = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Producto
        fields = [
            "id",
            "codigo",
            "nombre",
            "categoria",
            "categoria_nombre",
            "precio_venta",
            "porcentaje_iva",
            "stock_actual",
            "stock_inicial",
            "controla_stock",
            "activo",
            "creado_en",
        ]
        read_only_fields = ["stock_actual", "creado_en"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "empresa_id", None):
            # La categoría solo puede ser una de la MISMA empresa.
            self.fields["categoria"].queryset = Categoria.objects.filter(
                empresa=request.user.empresa
            )

    def validate_codigo(self, value):
        empresa = self.context["request"].user.empresa
        qs = Producto.objects.filter(empresa=empresa, codigo=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe un producto con ese código en tu empresa."
            )
        return value

    def validate(self, attrs):
        if attrs.get("stock_inicial") and attrs.get("controla_stock") is False:
            raise serializers.ValidationError(
                {"stock_inicial": "Un producto que no controla stock no lleva stock inicial."}
            )
        return attrs

    def create(self, validated_data):
        stock_inicial = validated_data.pop("stock_inicial", None)
        producto = super().create(validated_data)
        if stock_inicial and producto.controla_stock:
            request = self.context.get("request")
            aplicar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.Tipo.ENTRADA,
                cantidad=stock_inicial,
                motivo="Stock inicial",
                usuario=getattr(request, "user", None),
            )
            producto.refresh_from_db()
        return producto


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
