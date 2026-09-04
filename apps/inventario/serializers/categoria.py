from rest_framework import serializers

from ..models import Categoria


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
