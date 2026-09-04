from decimal import Decimal

from rest_framework import serializers

from ..models import Caja, TurnoCaja
from ..services import resumen_ventas


class TurnoCajaSerializer(serializers.ModelSerializer):
    """Representa un turno. La creación (POST) ES la apertura del turno;
    el cierre va por la acción ``/turnos/{id}/cerrar/``."""

    caja_nombre = serializers.CharField(source="caja.nombre", read_only=True)
    cajero_username = serializers.CharField(source="cajero.username", read_only=True)
    resumen_ventas = serializers.SerializerMethodField()
    diferencia_caja = serializers.SerializerMethodField()

    class Meta:
        model = TurnoCaja
        fields = [
            "id",
            "caja",
            "caja_nombre",
            "cajero",
            "cajero_username",
            "estado",
            "saldo_inicial",
            "saldo_final_declarado",
            "saldo_final_calculado",
            "diferencia_caja",
            "abierto_en",
            "cerrado_en",
            "resumen_ventas",
        ]
        read_only_fields = [
            "cajero",
            "estado",
            "saldo_final_declarado",
            "saldo_final_calculado",
            "abierto_en",
            "cerrado_en",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and getattr(request.user, "empresa_id", None):
            self.fields["caja"].queryset = Caja.objects.filter(
                empresa=request.user.empresa, activa=True
            )

    def get_resumen_ventas(self, obj) -> dict:
        resumen = resumen_ventas(obj)
        return {
            "cantidad_ventas": resumen["cantidad_ventas"],
            "total_ventas": str(resumen["total_ventas"]),
            "por_medio_pago": [
                {**fila, "total": str(fila["total"])} for fila in resumen["por_medio_pago"]
            ],
        }

    def get_diferencia_caja(self, obj) -> str | None:
        if obj.saldo_final_declarado is None or obj.saldo_final_calculado is None:
            return None
        return str(obj.saldo_final_declarado - obj.saldo_final_calculado)


class CerrarTurnoSerializer(serializers.Serializer):
    saldo_final_declarado = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0")
    )
