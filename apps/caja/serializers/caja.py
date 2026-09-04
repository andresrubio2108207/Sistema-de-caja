from rest_framework import serializers

from ..models import Caja


class CajaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Caja
        fields = ["id", "nombre", "activa"]

    def validate_nombre(self, value):
        empresa = self.context["request"].user.empresa
        qs = Caja.objects.filter(empresa=empresa, nombre=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una caja con ese nombre en tu empresa."
            )
        return value
