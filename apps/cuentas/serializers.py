from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer as BaseTokenObtainPairSerializer,
)

from .models import Usuario


class EmpresaResumenSerializer(serializers.Serializer):
    """Datos mínimos de la empresa que el front necesita tras el login."""

    id = serializers.IntegerField()
    razon_social = serializers.CharField()
    nombre_comercial = serializers.CharField()
    nit = serializers.CharField()
    activa = serializers.BooleanField()


class MeSerializer(serializers.ModelSerializer):
    empresa = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "is_superuser",
            "empresa",
        ]

    @extend_schema_field(EmpresaResumenSerializer(allow_null=True))
    def get_empresa(self, obj):
        if obj.empresa_id is None:
            return None
        return EmpresaResumenSerializer(obj.empresa).data


class CustomTokenObtainPairSerializer(BaseTokenObtainPairSerializer):
    """Añade rol y empresa al token, bloquea empresas inactivas y devuelve el
    usuario en el cuerpo de la respuesta del login."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = user.rol
        token["empresa_id"] = user.empresa_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.empresa_id and not self.user.empresa.activa:
            raise serializers.ValidationError(
                "La empresa asociada a este usuario está inactiva."
            )
        data["usuario"] = MeSerializer(self.user).data
        return data


class CambiarPasswordSerializer(serializers.Serializer):
    """Para que un usuario cambie SU PROPIA contraseña (no la de otro)."""

    password_actual = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_nueva = serializers.CharField(
        write_only=True, validators=[validate_password], style={"input_type": "password"}
    )

    def validate_password_actual(self, value):
        usuario = self.context["request"].user
        if not usuario.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value


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
