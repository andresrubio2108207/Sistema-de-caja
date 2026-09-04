from rest_framework import serializers

from ..models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            "id",
            "tipo_documento",
            "numero_documento",
            "nombre_completo",
            "email",
            "telefono",
            "direccion",
        ]

    def validate(self, attrs):
        empresa = self.context["request"].user.empresa
        numero = attrs.get(
            "numero_documento", getattr(self.instance, "numero_documento", None)
        )
        qs = Cliente.objects.filter(empresa=empresa, numero_documento=numero)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"numero_documento": "Ya existe un cliente con ese documento en tu empresa."}
            )
        return attrs
