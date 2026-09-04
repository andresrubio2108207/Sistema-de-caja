from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from ..models import Usuario


class UsuarioSerializer(serializers.ModelSerializer):
    """CRUD de personal de la empresa (lo usa el dueño).

    La empresa NO se acepta del cliente: la asigna ``EmpresaQuerysetMixin``.
    """

    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password], style={"input_type": "password"}
    )

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "is_active",
            "password",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError(
                {"password": "Es obligatorio al crear un usuario."}
            )
        usuario = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        return usuario

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
