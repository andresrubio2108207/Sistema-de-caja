from rest_framework import serializers

from ..models import HistoricoPrecio


class HistoricoPrecioSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True, default=None)

    class Meta:
        model = HistoricoPrecio
        fields = [
            "id",
            "producto",
            "precio_anterior",
            "precio_nuevo",
            "usuario",
            "usuario_username",
            "creado_en",
        ]
        read_only_fields = fields
