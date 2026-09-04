from decimal import Decimal

from rest_framework import serializers

from ..models import Categoria, MovimientoInventario, Producto
from ..services import aplicar_movimiento, registrar_cambio_precio


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

    def update(self, instance, validated_data):
        precio_anterior = instance.precio_venta
        producto = super().update(instance, validated_data)
        request = self.context.get("request")
        registrar_cambio_precio(
            producto=producto,
            precio_anterior=precio_anterior,
            usuario=getattr(request, "user", None),
        )
        return producto
